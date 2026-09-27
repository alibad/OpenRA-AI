"""Mode-aware, fog-safe faction/unit catalog answers from the shared catalog plus live engine rules."""
from __future__ import annotations

import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from openra_ai_companion import game_mcp
from openra_ai_companion.core import Companion
from openra_ai_companion.faction_catalog import (
    DIGEST_DIRECTORY_ENV,
    FactionKnowledge,
    catalog_candidates,
    locate_catalog,
)
from openra_ai_companion.models import GameSnapshot
from openra_ai_companion.router import AIRouter
from openra_ai_companion.server import create_server
from openra_ai_companion.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "catalog" / "factions.json"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def digest(mode: str) -> dict:
    """Trimmed output of the engine's `--check-faction-catalog --digest` for each mode."""
    return json.loads((FIXTURES / f"faction-digest-{mode}.json").read_text(encoding="utf-8"))


def knowledge(*modes: str) -> FactionKnowledge:
    result = FactionKnowledge(json.loads(CATALOG.read_text(encoding="utf-8")), CATALOG, digest_directory=None)
    result._share = lambda mode, value: None  # keep unit tests from touching the process environment
    for mode in modes:
        result.update_live(digest(mode))
    return result


class CatalogLocationTests(unittest.TestCase):
    def test_packaged_windows_and_macos_layouts_resolve_the_staged_catalog(self):
        with TemporaryDirectory() as temp:
            stage = Path(temp) / "OpenRA-AI-windows-x64"
            (stage / "catalog").mkdir(parents=True)
            (stage / "catalog/factions.json").write_text("{}")
            executable = stage / "bin" / "openra-ai-companion.exe"
            found = locate_catalog(env={}, executable=str(executable), frozen=True, module_file=str(Path(temp) / "x/a/b/c/d.py"))
            self.assertEqual(found, (stage / "catalog/factions.json").resolve())

            resources = Path(temp) / "OpenRA AI.app/Contents/Resources"
            (resources / "catalog").mkdir(parents=True)
            (resources / "catalog/factions.json").write_text("{}")
            found = locate_catalog(env={}, executable=str(resources / "bin/openra-ai-companion"), frozen=True,
                                   module_file=str(Path(temp) / "x/a/b/c/d.py"))
            self.assertEqual(found, (resources / "catalog/factions.json").resolve())

            # Launchers export the engine directory: macOS Resources, Windows <root>/engine/openra.
            self.assertEqual(locate_catalog(env={"OPENRA_AI_ENGINE_DIR": str(resources)}, frozen=False,
                                            module_file=str(Path(temp) / "x/a/b/c/d.py")),
                             (resources / "catalog/factions.json").resolve())
            self.assertEqual(locate_catalog(env={"OPENRA_AI_ENGINE_DIR": str(stage / "engine/openra")}, frozen=False,
                                            module_file=str(Path(temp) / "x/a/b/c/d.py")),
                             (stage / "catalog/factions.json").resolve())

    def test_explicit_override_wins_and_development_checkout_is_the_fallback(self):
        candidates = catalog_candidates(env={"OPENRA_AI_CATALOG": "override.json", "OPENRA_AI_ROOT": "root"}, frozen=False)
        self.assertEqual(candidates[0], Path("override.json").resolve())
        self.assertEqual(candidates[1], (Path("root") / "catalog/factions.json").resolve())
        self.assertEqual(candidates[-1], CATALOG.resolve())
        self.assertEqual(locate_catalog(env={}, frozen=False), CATALOG.resolve())


class LiveDigestTests(unittest.TestCase):
    def test_rejects_foreign_payloads(self):
        store = knowledge()
        for payload in ({}, {"schema": "other"}, {"schema": digest("ra")["schema"], "mode": "RA 2", "factions": []},
                        {"schema": digest("ra")["schema"], "mode": "ra"}):
            with self.assertRaises(ValueError):
                store.update_live(payload)

    def test_digest_is_shared_with_the_game_tool_process(self):
        with TemporaryDirectory() as temp, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(DIGEST_DIRECTORY_ENV, None)
            store = FactionKnowledge(json.loads(CATALOG.read_text(encoding="utf-8")), CATALOG,
                                     digest_directory=Path(temp))
            self.assertEqual(store.update_live(digest("ra2")), {"accepted": True, "mode": "ra2", "factions": 4})
            os.environ[DIGEST_DIRECTORY_ENV] = temp
            child = FactionKnowledge.load()
            self.assertEqual(child.last_mode, "ra2")
            self.assertIsNotNone(child.digest("ra2"))


class CatalogAnswerTests(unittest.TestCase):
    def test_what_does_the_qilin_counter_uses_rules_counters_and_catalog_advice(self):
        answer = knowledge("ra").answer("What does the Qilin counter?", "ra")
        self.assertIn("Qilin Main Battle Tank (China, Classic)", answer.text)
        self.assertIn("counter armor, building", answer.text)
        self.assertIn("attacks ground only", answer.text)
        self.assertIn("Screen against infantry ambushes", answer.text)
        self.assertEqual(answer.metadata["units"], ["cnqilin"])

        ra2 = knowledge("ra2").answer("What does the Qilin counter?", "ra2")
        self.assertIn("Qilin Battle Tank (China, Red Alert 2)", ra2.text)
        self.assertNotIn("Classic", ra2.text)

    def test_which_yemen_unit_is_anti_air_is_answered_from_live_weapons(self):
        answer = knowledge("ra").answer("Which Yemen unit is anti-air?", "ra")
        self.assertIn("SAM Site", answer.text)
        self.assertIn("None of its mobile units can target aircraft", answer.text)
        for ground_only in ("Armed Technical", "Samad", "Mountain Rifleman"):
            self.assertNotIn(ground_only, answer.text)
        self.assertEqual(answer.metadata["units"], ["sam"])

    def test_other_mode_factions_and_units_are_never_described_in_this_mode(self):
        store = knowledge("ra", "ra2")
        yemen = store.answer("Which Yemen unit is anti-air?", "ra2")
        self.assertIn("Yemen isn't available in Red Alert 2 mode", yemen.text)
        self.assertIn("available in Classic", yemen.text)
        self.assertNotIn("SAM", yemen.text)
        m1a2s = store.answer("What does the M1A2S counter?", "ra2")
        self.assertIn("belongs to Saudi Arabia, which isn't available in Red Alert 2", m1a2s.text)
        self.assertNotIn("HP", m1a2s.text)
        compare = store.answer("Tell me about Iran and Yemen", "ra2")
        self.assertIn("Iran", compare.text)
        self.assertIn("(Yemen is not available in Red Alert 2.)", compare.text)
        context = store.context("Compare the Karrar and the Samad", "ra2")
        self.assertEqual([u["name"] for u in context["units"]], ["Karrar Battle Tank"])
        self.assertIn("Yemen", context["not_in_this_mode"])

    def test_explicit_mode_in_the_question_is_respected(self):
        answer = knowledge("ra", "ra2").answer("What is the Qilin in Red Alert 2?", "ra")
        self.assertIn("Red Alert 2", answer.text)
        self.assertIn("R2QilinGun", answer.text)

    def test_catalog_only_answers_do_not_invent_statistics(self):
        answer = knowledge().answer("What does the Karrar counter?", "ra2")
        self.assertIn("Live rules aren't loaded yet", answer.text)
        self.assertNotIn("$", answer.text)

    def test_orders_advice_and_live_state_questions_go_to_the_planner(self):
        store = knowledge("ra")
        for text in ("Build a Qilin", "Can you train two Qilins?", "Where is the enemy Qilin?", "What should China build next?",
                     "How many Karrars do I have?", "What should we do next?", "Should I build Qilins?"):
            self.assertIsNone(store.answer(text, "ra"), text)

    def test_faction_questions_filter_units_that_only_share_a_word(self):
        answer = knowledge("ra").answer("Which China unit can transport?", "ra")
        self.assertNotIn("England", answer.text)


class CompanionIntegrationTests(unittest.TestCase):
    def companion(self) -> Companion:
        router = AIRouter(Settings(router_url="http://127.0.0.1:9", companion_enabled=True))
        companion = Companion(router)
        companion.faction_knowledge = knowledge("ra")
        return companion

    def test_catalog_questions_are_answered_without_a_match_or_model(self):
        companion = self.companion()
        with mock.patch.object(companion.router, "chat", side_effect=AssertionError("no model call")):
            response = companion.handle_player_input("Which Yemen unit is anti-air?")
        self.assertEqual(response.source, "faction-catalog")
        self.assertIn("SAM Site", response.text)
        self.assertEqual(response.metadata["catalog"]["mode"], "ra")

    def test_answers_ignore_match_state_so_fog_cannot_leak(self):
        companion = self.companion()
        without_match = companion.handle_player_input("What does the Qilin counter?")
        companion.latest_snapshot = GameSnapshot.from_dict({
            "tick": 900, "mod_id": "ra", "units": [], "buildings": [],
            "visible_enemies": [{"actor_id": 77, "type": "cnqilin", "owner": "Enemy", "cell_x": 12, "cell_y": 34, "hp_percent": 0.4}],
        })
        with_enemy = companion.handle_player_input("What does the Qilin counter?")
        self.assertEqual(with_enemy.source, "faction-catalog")
        self.assertEqual(with_enemy.text, without_match.text)
        self.assertEqual(with_enemy.metadata, without_match.metadata)
        self.assertNotIn("Enemy", json.dumps(with_enemy.metadata))

    def test_ask_prompt_gets_mode_filtered_catalog_context(self):
        companion = self.companion()
        companion.faction_knowledge.update_live(digest("ra2"))
        companion.latest_snapshot = GameSnapshot.from_dict({"tick": 1, "mod_id": "ra2", "units": [], "buildings": []})
        captured = {}

        def chat(messages):
            captured["payload"] = json.loads(messages[-1]["content"])
            raise __import__("openra_ai_companion.router", fromlist=["RouterError"]).RouterError("offline")

        with mock.patch.object(companion.router, "chat", side_effect=chat), \
                mock.patch.object(companion, "_vision_inputs", return_value=([], [])):
            companion.ask("Explain how the Raad and the Samad compare")
        catalog = captured["payload"]["faction_catalog"]
        self.assertEqual(catalog["mode"], "Red Alert 2")
        self.assertEqual([u["name"] for u in catalog["units"]], ["Raad Air Defense"])
        self.assertTrue(catalog["units"][0]["antiAir"])


class ServiceAndToolTests(unittest.TestCase):
    def test_game_posts_digest_and_console_can_query_it(self):
        companion = Companion(AIRouter(Settings(router_url="http://127.0.0.1:9")))
        companion.faction_knowledge = knowledge()
        server = create_server("127.0.0.1", 0, companion)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            body = json.dumps(digest("ra")).encode()
            request = urllib.request.Request(base + "/v1/factions/live", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual(json.load(response), {"accepted": True, "mode": "ra", "factions": 6})
            with urllib.request.urlopen(base + "/v1/factions?q=Which%20Yemen%20unit%20is%20anti-air%3F", timeout=5) as response:
                status = json.load(response)
            self.assertEqual(status["mode"], "ra")
            self.assertIn("SAM Site", status["lookup"]["answer"])
            bad = urllib.request.Request(base + "/v1/factions/live", data=b'{"schema":"x"}', headers={"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(bad, timeout=5)
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()

    def test_game_tool_reads_the_shared_digest_for_the_match_mode(self):
        with TemporaryDirectory() as temp, mock.patch.dict(os.environ, {DIGEST_DIRECTORY_ENV: temp}):
            Path(temp, "ra2.json").write_text(json.dumps(digest("ra2")), encoding="utf-8")
            previous = game_mcp.runtime
            game_mcp.runtime = mock.Mock(_snapshot=GameSnapshot.from_dict({"tick": 1, "mod_id": "ra2", "units": [], "buildings": []}))
            try:
                result = game_mcp.faction_catalog("Which Turkish units are anti-air?")
                overview = game_mcp.faction_catalog("")
            finally:
                game_mcp.runtime = previous
        self.assertTrue(result["live_rules"])
        self.assertIn("Gokkalkan", result["answer"])
        self.assertEqual(overview["mode"], "Red Alert 2")
        self.assertEqual({f["name"] for f in overview["factions"] if f["kind"] == "modern"}, {"China", "Iran", "Türkiye"})
        self.assertIn("Saudi Arabia", overview["not_in_this_mode"])


if __name__ == "__main__":
    unittest.main()
