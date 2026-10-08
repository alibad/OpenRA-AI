from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import balance_harness as bh

MAP_YAML = """MapFormat: 12
RequiresMod: ra
Title: Test Plains
Tileset: TEMPERAT
MapSize: 64,64
Visibility: Lobby
Players:
\tPlayerReference@Neutral:
\t\tName: Neutral
\t\tOwnsWorld: True
\t\tNonCombatant: True
\t\tFaction: allies
\tPlayerReference@Multi0:
\t\tName: Multi0
\t\tPlayable: True
\t\tFaction: Random
\tPlayerReference@Multi1:
\t\tName: Multi1
\t\tPlayable: True
\t\tFaction: Random
Actors:
\tActor0: mpspawn
\t\tLocation: 10,10
\t\tOwner: Neutral
\tActor1: mine
\t\tLocation: 20,20
\t\tOwner: Neutral
\tActor2: mpspawn
\t\tLocation: 50,50
\t\tOwner: Neutral
"""

CAMPAIGN = {
    "name": "test", "seed": 11,
    "experiences": {"wwiii": {"profile": "world-war-iii"}, "no-doctrine": {"components": ["ra2-china", "ra2-iran"]}},
    "suites": [{"id": "classic", "mod": "ra", "experience": "wwiii", "factions": ["china", "iran", "russia"],
                "bots": ["normal", "rush"], "replicates": 2, "tick_cap": 1000,
                "maps": [{"map": "a.oramap", "kind": "land"}, {"map": "b", "kind": "naval", "spawns": [2, 1]}]}],
}


def telemetry_lines(match_id: str, rows: list[str]) -> str:
    return "\n".join(f"BALANCE|{match_id}|{row}" for row in rows) + "\n"


def sample(tick, player, cash=0, kills=0, deaths=0, army=0, unit_spend=0, building_spend=0):
    return f"sample|{tick}|{player}|{cash}|0|{kills}|{deaths}|0|0|0|0|{army}|0|{unit_spend}|{building_spend}|5"


def result_for(match: bh.Match, rows: list[str], exit_code=0, status="complete", exceptions=()):
    telemetry = bh.parse_telemetry(telemetry_lines(match.id, rows), match.id)
    outcome = bh.decide_outcome(telemetry, exit_code, status, list(exceptions), [])
    return {"match": match.to_dict(), "status": outcome["status"], "outcome": outcome, "telemetry": telemetry,
            "wall_seconds": 10.0, "exceptions": list(exceptions), "lua_errors": []}


class PlanTests(unittest.TestCase):
    def test_plan_is_deterministic_complete_and_orientation_balanced(self):
        first = bh.plan(CAMPAIGN)
        self.assertEqual(first, bh.plan(CAMPAIGN))
        # 3 unordered pairs x 2 orientations x 2 maps x 2 bots x 2 replicates.
        self.assertEqual(len(first), 3 * 2 * 2 * 2 * 2)
        self.assertEqual(len({m.id for m in first}), len(first))
        for m in first:
            twin = next(o for o in first if o.id == m.id.replace(f"{m.factions[0]}-{m.factions[1]}",
                                                                   f"{m.factions[1]}-{m.factions[0]}"))
            self.assertEqual((twin.map, twin.bots, twin.replicate, twin.spawns), (m.map, m.bots, m.replicate, m.spawns))
        # Whole replicates complete before the next starts.
        self.assertEqual([m.replicate for m in first], sorted(m.replicate for m in first))
        self.assertNotEqual([m.id for m in first], [m.id for m in bh.plan(CAMPAIGN, seed=12)])
        self.assertEqual([m.order for m in first], list(range(len(first))))
        self.assertEqual(next(m for m in first if m.map == "b").spawns, (2, 1))

    def test_focus_and_mirrors(self):
        suite = dict(CAMPAIGN["suites"][0], focus=["china"], mirrors=True)
        self.assertEqual(bh.pairings(suite), [("china", "iran"), ("china", "russia"), ("china", "china")])

    def test_experience_settings(self):
        self.assertEqual(bh.experience_settings("ra", "wwiii", CAMPAIGN), "Experience@ra:\n\tProfile: world-war-iii\n")
        self.assertIn("EnabledComponents: ra2-china, ra2-iran", bh.experience_settings("ra2", "no-doctrine", CAMPAIGN))
        self.assertEqual(bh.experience_settings("ra", "default", CAMPAIGN), "")


class FixtureTests(unittest.TestCase):
    def test_map_patch_locks_factions_spawns_and_adds_telemetry_rules(self):
        text = bh.patch_map_yaml(MAP_YAML, ("china", "russia"), (2, 1), "Balance x")
        self.assertIn("\tPlayerReference@Multi0:\n\t\tName: Multi0\n\t\tPlayable: True\n\t\tFaction: china\n"
                      "\t\tLockFaction: True\n\t\tLockSpawn: True\n\t\tSpawn: 2\n", text)
        self.assertIn("Faction: russia", text)
        self.assertIn("Rules: balance-rules.yaml\n", text)
        self.assertIn("Title: Balance x", text)
        self.assertEqual(bh.spawn_points(text), [(10, 10), (50, 50)])

    def test_map_patch_keeps_existing_rule_files_and_inline_rules(self):
        text = bh.patch_map_yaml(MAP_YAML + "Rules: rules.yaml\n\tWorld:\n\t\tCrateSpawner:\n",
                                 ("iran", "iran"), (1, 2), "t")
        self.assertIn("Rules: rules.yaml, balance-rules.yaml\n\tWorld:\n\t\tCrateSpawner:\n", text)

    def test_map_patch_rejects_scripted_or_invalid_maps(self):
        with self.assertRaises(ValueError):
            bh.patch_map_yaml(MAP_YAML + "Rules:\n\tWorld:\n\t\tLuaScript:\n", ("a", "b"), (1, 2), "t")
        with self.assertRaises(ValueError):
            bh.patch_map_yaml(MAP_YAML, ("a", "b"), (1, 3), "t")
        with self.assertRaises(ValueError):
            bh.patch_map_yaml(MAP_YAML.replace("Multi1", "Multi7"), ("a", "b"), (1, 2), "t")

    def test_write_fixture_from_oramap(self):
        match = bh.plan(CAMPAIGN)[0]
        with tempfile.TemporaryDirectory() as root:
            maps = Path(root) / "maps"
            maps.mkdir()
            if match.map.endswith(".oramap"):
                with zipfile.ZipFile(maps / match.map, "w") as archive:
                    archive.writestr("map.yaml", MAP_YAML)
                    archive.writestr("map.bin", b"\x02bin")
            else:
                (maps / "b").mkdir()
                (maps / "b" / "map.yaml").write_text(MAP_YAML)
                (maps / "b" / "map.bin").write_bytes(b"\x02bin")
            target = Path(root) / "fixture"
            bh.write_fixture(match, maps, target)
            self.assertEqual((target / "map.bin").read_bytes(), b"\x02bin")
            script = (target / "balance-telemetry.lua").read_text()
            self.assertIn(f'local MatchId = "{match.id}"', script)
            self.assertIn("local TickCap = 1000", script)
            self.assertNotIn("__", script.split("]]", 1)[1])
            self.assertIn("Scripts: balance-telemetry.lua", (target / "balance-rules.yaml").read_text())

    def test_manifest_speed_patch_changes_only_the_default_timestep(self):
        manifest = (ROOT / "engine/openra/mods/ra/mod.yaml")
        text = manifest.read_text(encoding="utf-8") if manifest.is_file() else (
            "Metadata:\n\tTitle: x\n\nGameSpeeds:\n\tDefaultSpeed: default\n\tSpeeds:\n\t\tslower:\n\t\t\tTimestep: 50\n"
            "\t\tdefault:\n\t\t\tName: options-game-speed.normal\n\t\t\tTimestep: 40\n\t\t\tOrderLatency: 3\n"
            "\t\tfastest:\n\t\t\tTimestep: 20\n")
        patched = bh.patch_manifest_speed(text, 1)
        diff = [(a, b) for a, b in zip(text.splitlines(), patched.splitlines()) if a != b]
        self.assertEqual(diff, [("\t\t\tTimestep: 40", "\t\t\tTimestep: 1")])
        with self.assertRaises(ValueError):
            bh.patch_manifest_speed("GameSpeeds:\n\tSpeeds:\n")


class ReplayTests(unittest.TestCase):
    def test_fixture_map_is_packed_for_playback(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "balance-x"
            folder.mkdir()
            (folder / "map.yaml").write_text(MAP_YAML)
            (folder / "balance-telemetry.lua").write_text("-- script")
            bh.pack_map(folder, Path(root) / "balance-x.oramap")
            with zipfile.ZipFile(Path(root) / "balance-x.oramap") as archive:
                self.assertEqual(sorted(archive.namelist()), ["balance-telemetry.lua", "map.yaml"])

    def test_replay_check_skips_matches_without_a_replay(self):
        match = bh.plan(CAMPAIGN)[0]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "result.json"
            path.write_text(json.dumps({"match": match.to_dict(), "replay": None}))
            report = bh.replay_check(path, engine=Path(root), mods=Path(root), content=Path(root))
            self.assertEqual(report["status"], "skipped")


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.match = bh.plan(CAMPAIGN)[0]

    def test_parse_and_conquest_outcome(self):
        rows = ["player|1|Multi0|china|1|true", "player|1|Multi1|russia|2|true",
                "starting|1|Multi0|mcv|2000", "produced|300|Multi0|e1|Infantry|100",
                "placed|200|Multi1|powr|300", "lost|900|Multi1|e1|Infantry|100|Multi0",
                sample(250, "Multi0", cash=500, kills=100), sample(250, "Multi1", deaths=100),
                "defeated|1200|Multi1", "won|1200|Multi0",
                "noise that is not telemetry"]
        telemetry = bh.parse_telemetry(telemetry_lines(self.match.id, rows) + "BALANCE|other|won|5|Multi1\n", self.match.id)
        self.assertEqual(telemetry["players"]["Multi0"], {"faction": "china", "spawn": 1, "bot": True})
        self.assertEqual(telemetry["produced"][0], [1, "Multi0", "mcv", "Starting", 2000])
        self.assertEqual(telemetry["samples"]["Multi0"][0][:4], [250, 500, 0, 100])
        self.assertEqual(telemetry["malformed_lines"], 1)
        outcome = bh.decide_outcome(telemetry, 0, "complete", [], [])
        self.assertEqual((outcome["result"], outcome["winner"], outcome["end_tick"]), ("win", "Multi0", 1200))

    def test_cap_crash_and_hang_outcomes(self):
        cap = bh.parse_telemetry(telemetry_lines(self.match.id, ["player|1|Multi0|china|1|true", "cap|1000|1000",
                                                                  "defeated|1000|Multi0"]), self.match.id)
        self.assertEqual(bh.decide_outcome(cap, 0, "complete", [], [])["result"], "draw")
        self.assertEqual(bh.decide_outcome(cap, 1, "complete", [], [])["status"], "crash")
        self.assertEqual(bh.decide_outcome(cap, 0, "complete", ["exception-1.log"], [])["reason"], "exception")
        self.assertEqual(bh.decide_outcome(cap, None, "hang", [], [])["status"], "hang")
        empty = bh.parse_telemetry("", self.match.id)
        self.assertEqual(bh.decide_outcome(empty, 0, "complete", [], [])["reason"], "no-telemetry")

    def test_stall_requires_continuous_unspent_money_without_production(self):
        rows = ["player|1|Multi0|china|1|true", "player|1|Multi1|russia|2|true", "produced|3500|Multi0|e1|Infantry|100"]
        rows += [sample(t, "Multi0", cash=5000) for t in range(250, 12001, 250)]
        # Multi1 is broke until 9000 and then rich without producing.
        rows += [sample(t, "Multi1", cash=0 if t < 9000 else 5000) for t in range(250, 12001, 250)]
        result = result_for(self.match, rows)
        stalls = bh.stall_windows(result)
        self.assertEqual(stalls["Multi0"]["longest_ticks"], 12000 - 3500)
        self.assertTrue(stalls["Multi0"]["stalled"])
        self.assertEqual(stalls["Multi1"]["longest_ticks"], 3000)
        self.assertFalse(stalls["Multi1"]["stalled"])

    def test_idle_army_detection(self):
        rows = ["player|1|Multi0|china|1|true"]
        rows += [sample(t, "Multi0", army=5000, kills=0) for t in range(250, 10001, 250)]
        self.assertTrue(bh.idle_army_windows(result_for(self.match, rows))["Multi0"]["idle"])
        rows = ["player|1|Multi0|china|1|true"] + [sample(t, "Multi0", army=5000, kills=t) for t in range(250, 10001, 250)]
        self.assertFalse(bh.idle_army_windows(result_for(self.match, rows))["Multi0"]["idle"])


class SummaryTests(unittest.TestCase):
    def test_wilson_interval(self):
        low, high = bh.wilson(8, 10)
        self.assertAlmostEqual(low, 0.490, places=2)
        self.assertAlmostEqual(high, 0.943, places=2)
        self.assertEqual(bh.wilson(0, 0), (0.0, 1.0))

    def test_summary_counts_both_orientations_and_errors(self):
        plan = [m for m in bh.plan(CAMPAIGN) if {"china", "iran"} == set(m.factions) and m.bots[0] == "normal"
                and m.map == "a.oramap" and m.replicate == 0]
        self.assertEqual(len(plan), 2)
        results = []
        for match in plan:
            china = f"Multi{match.factions.index('china')}"
            iran = f"Multi{match.factions.index('iran')}"
            rows = [f"player|1|{china}|china|1|true", f"player|1|{iran}|iran|2|true",
                    f"produced|100|{china}|cnqilin|Vehicle|1200",
                    f"lost|500|{iran}|irkarr|Vehicle|1000|{china}",
                    sample(9000, china, kills=3000, deaths=1000), sample(9000, iran, kills=1000, deaths=3000),
                    f"won|9000|{china}"]
            results.append(result_for(match, rows))
        crash_match = next(m for m in bh.plan(CAMPAIGN) if m.bots[0] == "rush")
        results.append(result_for(crash_match, [], exit_code=3))
        summary = bh.summarize(results)
        suite = summary["suites"]["classic"]
        self.assertEqual((summary["complete"], summary["errors"]), (2, 1))
        self.assertEqual(suite["factions"]["china"]["wins"], 2)
        self.assertEqual(suite["factions"]["china"]["cost_efficiency"], 3.0)
        self.assertEqual(suite["factions"]["china"]["produced"]["Vehicle"], {"count": 2, "value": 2400})
        self.assertEqual(suite["factions"]["iran"]["lost"]["Vehicle"]["count"], 2)
        pairing = suite["pairings"]["china vs iran"]
        self.assertEqual((pairing["games"], pairing["a_wins"], pairing["b_wins"]), (2, 2, 0))
        self.assertEqual(suite["by_map"]["a.oramap"]["first_slot_score"], 0.5)
        report = bh.render_report(summary, CAMPAIGN, 3, {"seed": 11})
        self.assertIn("| **china** vs iran | 2 | 2 | 0 | 0 |", report)
        self.assertIn("## Errors", report)
        json.dumps(summary)


if __name__ == "__main__":
    unittest.main()
