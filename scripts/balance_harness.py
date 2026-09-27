#!/usr/bin/env python3
"""Headless, seeded, parallel bot-vs-bot balance campaigns.

One command plans a campaign, runs every match as a private headless
(``Game.Platform=Null``) OpenRA process, keeps its replay and telemetry, and
writes ``summary.json`` plus a readable ``report.md``::

    python scripts/balance_harness.py run --campaign baseline-2026-09 \
        --engine engine/openra --content <OpenRA Support>/Content \
        --output artifacts/balance/baseline-2026-09 --parallel 4

``plan`` prints the deterministic schedule, ``report`` rebuilds the summary
from existing match results, and ``replay`` plays saved replays back headless
and checks they re-emit exactly the recorded telemetry. Nothing here edits
rules: the harness only changes disposable copies of maps (faction/spawn
locks, a telemetry script and the passive ``ScriptTriggers`` trait it needs)
and a disposable copy of the mod manifest. Matches that already have a
``result.json`` are skipped, so an interrupted campaign resumes where it
stopped; every match runs in its own support directory with no network port.

Simulation pacing. Bot-vs-bot matches have no human, so the harness runs the
simulation as fast as the host allows: its private manifest copy sets the
``default`` game speed's Timestep to 1 ms (OrderLatency unchanged). Every
simulated tick is identical to a normal-speed tick; local games use a
one-frame order latency regardless of speed, and the few wall-clock timers in
the engine only pace audio notifications. Replays keep the ``default`` speed
id, so they play back at normal speed in the unmodified game. Durations are
reported as normal-speed game time (25 ticks per second).

Determinism. The schedule, slot/spawn orientation and per-match seeds derive
from the campaign seed. The engine itself does not accept a seed: the local
server seeds its shared RNG from the clock and bots use an unseeded local RNG.
Each match's actual engine seed is read back from its replay, and replicate
seeds are independent samples, not bit-identical reruns. RA2 replays play
back exactly (``replay``). Classic replays currently go out of sync on the
first synced frame of playback even for stock maps without the telemetry
script, at normal speed and with unmodified manifests; that is an existing
engine/mod issue recorded in docs/balance-baseline-2026-09.md, not a harness
effect. A seeded engine (a launch seed for the server RNG and the bots' local
RNG) would make whole matches reproducible from the campaign seed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_fixture import absolute_path, link_directory, unlink_directory  # noqa: E402

CAMPAIGNS = ROOT / "scripts/balance_campaigns.json"
TELEMETRY = ROOT / "scripts/balance_telemetry.lua"
TICKS_PER_SECOND = 25  # Normal game speed (Timestep 40 ms).
HARNESS_TIMESTEP = 1
SCHEMA = "openra-ai.balance-harness/v1"
SHADOWED_MODS = ("ra", "ra2")
CHECKPOINT_MINUTES = (5, 10, 15, 20, 30, 40)


# ---------------------------------------------------------------- planning

@dataclass(frozen=True)
class Match:
    id: str
    suite: str
    mod: str
    map: str
    map_title: str
    map_kind: str
    factions: tuple[str, str]
    spawns: tuple[int, int]
    bots: tuple[str, str]
    experience: str
    replicate: int
    seed: int
    tick_cap: int
    sample_interval: int
    order: int = 0

    def to_dict(self) -> dict:
        data = asdict(self)
        data["factions"] = list(self.factions)
        data["spawns"] = list(self.spawns)
        data["bots"] = list(self.bots)
        return data


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower().removesuffix(".oramap")).strip("-")


def derived_seed(seed: int, key: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{key}".encode()).digest()[:4], "big")


def load_campaign(name: str, path: Path = CAMPAIGNS) -> dict:
    campaigns = json.loads(path.read_text(encoding="utf-8"))
    if name not in campaigns:
        raise SystemExit(f"Unknown campaign '{name}'. Known: {', '.join(sorted(campaigns))}")
    campaign = dict(campaigns[name])
    campaign["name"] = name
    return campaign


def pairings(suite: dict) -> list[tuple[str, str]]:
    factions = list(suite["factions"])
    pairs = list(itertools.combinations(factions, 2))
    if suite.get("mirrors"):
        pairs += [(f, f) for f in factions]
    focus = set(suite.get("focus", ()))
    if focus:
        pairs = [p for p in pairs if focus & set(p)]
    return pairs


def plan(campaign: dict, seed: int | None = None, suites: set[str] | None = None) -> list[Match]:
    """Expand a campaign into matches, deterministically ordered by ``seed``.

    Every unordered faction pairing is played from both slot/spawn
    orientations on every map, bot profile and replicate, so spawn advantage
    cancels within a pairing. Execution order is shuffled per replicate with
    the campaign seed; a partial (``--limit``) run is therefore an unbiased
    subset while completing whole replicates first.
    """
    seed = campaign.get("seed", 0) if seed is None else seed
    matches: list[Match] = []
    for suite in campaign["suites"]:
        if suites and suite["id"] not in suites:
            continue
        for map_entry, bot, replicate, (a, b) in itertools.product(
                suite["maps"], suite["bots"], range(suite.get("replicates", 1)), pairings(suite)):
            for first, second in ((a, b), (b, a)) if a != b else ((a, b),):
                key = f"{suite['id']}.{slug(map_entry['map'])}.{bot}.{first}-{second}.r{replicate}"
                matches.append(Match(
                    id=key, suite=suite["id"], mod=suite["mod"], map=map_entry["map"],
                    map_title=map_entry.get("title", map_entry["map"]), map_kind=map_entry.get("kind", "land"),
                    factions=(first, second), spawns=tuple(map_entry.get("spawns", (1, 2))),
                    bots=(bot, bot), experience=suite.get("experience", "default"), replicate=replicate,
                    seed=derived_seed(seed, key), tick_cap=int(suite.get("tick_cap", 45000)),
                    sample_interval=int(suite.get("sample_interval", 250))))
    ordered = sorted(matches, key=lambda m: (m.replicate, derived_seed(seed, "order:" + m.id)))
    return [replace(m, order=i) for i, m in enumerate(ordered)]


# -------------------------------------------------------------- resources

def patch_manifest_speed(text: str, timestep: int = HARNESS_TIMESTEP) -> str:
    """Return a mod manifest whose ``default`` game speed has ``timestep`` ms."""
    pattern = re.compile(r"(^GameSpeeds:\n(?:[ \t][^\n]*\n)*?\t\tdefault:\n(?:\t\t\t[^\n]*\n)*?\t\t\tTimestep: )(\d+)",
                         re.MULTILINE)
    patched, count = pattern.subn(lambda m: m.group(1) + str(timestep), text)
    if count != 1:
        raise ValueError("Manifest has no unique GameSpeeds default Timestep")
    return patched


def _mirror(source: Path, target: Path, *, manifest_timestep: int | None) -> None:
    target.mkdir(parents=True)
    for entry in sorted(source.iterdir()):
        destination = target / entry.name
        if entry.is_dir():
            link_directory(destination, entry)
        elif entry.name == "mod.yaml" and manifest_timestep is not None:
            destination.write_text(patch_manifest_speed(entry.read_text(encoding="utf-8"), manifest_timestep),
                                   encoding="utf-8")
        else:
            shutil.copy2(entry, destination)


def prepare_resources(engine: Path, output: Path, ra2_mod: Path | None) -> Path:
    """Build a private mod search path: every engine mod, pacing-patched ra/ra2.

    Directories are links, so no game data is copied. Only top-level mod
    files (manifests, small chrome/metrics YAML) are copied, and only the
    ``default`` speed Timestep differs from the source manifests.
    """
    mods = output / "resources" / "mods"
    if mods.exists():
        return mods
    staging = output / "resources" / ".staging-mods"
    if staging.exists():
        clear_tree(staging)
    staging.mkdir(parents=True)
    sources = {p.name: p for p in sorted((engine / "mods").iterdir()) if p.is_dir()}
    if ra2_mod is not None:
        sources["ra2"] = ra2_mod
    for name, source in sources.items():
        source = source.resolve()
        if name in SHADOWED_MODS and (source / "mod.yaml").is_file():
            _mirror(source, staging / name, manifest_timestep=HARNESS_TIMESTEP)
        else:
            link_directory(staging / name, source)
    staging.rename(mods)
    return mods


def clear_tree(path: Path) -> None:
    """Delete a harness directory without following links into game data."""
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or (os.name == "nt" and path.is_junction()):
        unlink_directory(path)
        return
    for child in list(path.iterdir()):
        if child.is_symlink() or (os.name == "nt" and child.is_junction()):
            unlink_directory(child)
        elif child.is_dir():
            clear_tree(child)
        else:
            child.unlink()
    path.rmdir()


# ------------------------------------------------------------ map fixture

def read_map(maps_dir: Path, name: str) -> dict[str, bytes]:
    source = maps_dir / name
    if source.is_dir():
        return {p.name: p.read_bytes() for p in source.iterdir() if p.is_file()}
    if source.is_file():
        with zipfile.ZipFile(source) as archive:
            return {n: archive.read(n) for n in archive.namelist() if not n.endswith("/")}
    raise FileNotFoundError(f"Map not found: {source}")


def spawn_points(map_yaml: str) -> list[tuple[int, int]]:
    """Return mpspawn locations in engine spawn order (map actor order)."""
    points = []
    for block in re.finditer(r"^\t[^\t\n][^\n]*: mpspawn\n((?:\t\t[^\n]*\n)+)", map_yaml, re.MULTILINE):
        loc = re.search(r"Location: (-?\d+),\s*(-?\d+)", block.group(1))
        if loc:
            points.append((int(loc.group(1)), int(loc.group(2))))
    return points


def _set_field(block: str, key: str, value: str) -> str:
    line = f"\t\t{key}: {value}\n"
    if re.search(rf"^\t\t{key}:[^\n]*\n", block, re.MULTILINE):
        return re.sub(rf"^\t\t{key}:[^\n]*\n", line, block, count=1, flags=re.MULTILINE)
    return block + line


def patch_map_yaml(text: str, factions: tuple[str, str], spawns: tuple[int, int], title: str) -> str:
    """Lock both combatant slots' faction and spawn and add telemetry rules."""
    text = text.replace("\r\n", "\n")
    if "LuaScript" in text:
        raise ValueError("Map already defines a LuaScript; choose a map without mission scripting")
    count = len(spawn_points(text))
    for spawn in spawns:
        if not 1 <= spawn <= count:
            raise ValueError(f"Spawn {spawn} outside 1..{count}")
    colors = ("E04444", "4477EE")
    for slot, (faction, spawn) in enumerate(zip(factions, spawns)):
        pattern = re.compile(rf"(^\tPlayerReference@Multi{slot}:\n)((?:\t\t[^\n]*\n)+)", re.MULTILINE)
        found = pattern.search(text)
        if not found:
            raise ValueError(f"Map has no Multi{slot} slot")
        block = found.group(2)
        if "Playable: True" not in block:
            raise ValueError(f"Multi{slot} is not playable")
        for key, value in (("Faction", faction), ("LockFaction", "True"), ("LockSpawn", "True"),
                           ("Spawn", str(spawn)), ("LockColor", "True"), ("Color", colors[slot])):
            block = _set_field(block, key, value)
        text = text[:found.start(2)] + block + text[found.end(2):]
    text = re.sub(r"^Title: [^\n]*$", f"Title: {title}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^Visibility: [^\n]*$", "Visibility: Lobby", text, count=1, flags=re.MULTILINE)
    rules = re.search(r"^Rules:([^\n]*)\n", text, re.MULTILINE)
    if rules is None:
        text = text.rstrip("\n") + "\n\nRules: balance-rules.yaml\n"
    else:
        files = [f.strip() for f in rules.group(1).split(",") if f.strip()]
        files.append("balance-rules.yaml")
        text = text[:rules.start()] + "Rules: " + ", ".join(files) + "\n" + text[rules.end():]
    return text


def write_fixture(match: Match, engine_maps: Path, target: Path) -> None:
    files = read_map(engine_maps, match.map)
    if "map.yaml" not in files:
        raise ValueError(f"{match.map} has no map.yaml")
    for rules_file, content in files.items():
        if rules_file.endswith((".yaml", ".lua")) and b"LuaScript" in content:
            raise ValueError(f"{match.map} contains mission scripting ({rules_file})")
    target.mkdir(parents=True)
    for name, content in files.items():
        if name != "map.yaml":
            (target / name).write_bytes(content)
    map_yaml = patch_map_yaml(files["map.yaml"].decode("utf-8-sig"), match.factions, match.spawns,
                              "Balance " + match.id)
    (target / "map.yaml").write_text(map_yaml, encoding="utf-8")
    # ScriptTriggers is passive plumbing for Lua triggers; RA2's world lacks it.
    (target / "balance-rules.yaml").write_text(
        "World:\n\tScriptTriggers:\n\tLuaScript:\n\t\tScripts: balance-telemetry.lua\n", encoding="utf-8")
    script = TELEMETRY.read_text(encoding="utf-8")
    script = (script.replace("__MATCH_ID__", match.id)
              .replace("__SAMPLE_INTERVAL__", str(match.sample_interval))
              .replace("__TICK_CAP__", str(match.tick_cap)))
    (target / "balance-telemetry.lua").write_text(script, encoding="utf-8")


def experience_settings(mod: str, experience: str, campaign: dict) -> str:
    spec = campaign.get("experiences", {}).get(experience, {"profile": experience})
    if experience == "default":
        return ""
    if "components" in spec:
        return (f"Experience@{mod}:\n\tUseCustomComponents: true\n"
                f"\tEnabledComponents: {', '.join(spec['components'])}\n")
    return f"Experience@{mod}:\n\tProfile: {spec['profile']}\n"


# --------------------------------------------------------------- running

def user_map_dir(mod_dir: Path, mod: str) -> str:
    manifest = (mod_dir / "mod.yaml").read_text(encoding="utf-8")
    found = re.search(rf"^\t~\^SupportDir\|(maps/{mod}/[^:\n]+): User$", manifest, re.MULTILINE)
    if not found:
        raise ValueError(f"{mod} manifest has no user map folder")
    return found.group(1)


def engine_seed(replay: Path) -> int | None:
    if not replay.is_file():
        return None
    found = re.search(rb"RandomSeed: (-?\d+)", replay.read_bytes())
    return int(found.group(1)) if found else None


def run_match(match: Match, *, engine: Path, mods: Path, content: Path, output: Path, campaign: dict,
              keep_support: bool = False, dotnet: str = "dotnet") -> dict:
    match_dir = output / "matches" / match.id
    result_path = match_dir / "result.json"
    if match_dir.exists():
        clear_tree(match_dir)
    match_dir.mkdir(parents=True)
    support = match_dir / "support"
    support.mkdir()
    link_directory(support / "Content", content)
    fixture = "balance-" + slug(match.id)
    write_fixture(match, mods / match.mod / "maps", support / user_map_dir(mods / match.mod, match.mod) / fixture)
    settings = experience_settings(match.mod, match.experience, campaign)
    (support / "settings.yaml").write_text(settings, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("OPENRA_AI_")}
    env.update(OPENRA_AI_DISABLE_AUTOSTART="1", DOTNET_ROLL_FORWARD=env.get("DOTNET_ROLL_FORWARD", "Major"))
    command = [dotnet, str(engine / "bin" / "OpenRA.dll"), f"Engine.EngineDir={engine}",
               f"Engine.ModSearchPaths={mods}", f"Engine.SupportDir={support}", f"Game.Mod={match.mod}",
               "Game.Platform=Null", "Game.FetchNews=false", f"Launch.Map={fixture}",
               f"Launch.Bots=Multi0:{match.bots[0]},Multi1:{match.bots[1]}", "Launch.Benchmark=benchmark-"]
    guard = float(campaign.get("wall_guard_seconds", 2400))
    started = time.monotonic()
    status = "complete"
    with (match_dir / "game.log").open("w", encoding="utf-8", errors="replace") as log:
        process = subprocess.Popen(command, cwd=engine / "bin", env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            exit_code = process.wait(timeout=guard)
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code = process.wait(timeout=30)
            status = "hang"
    wall = round(time.monotonic() - started, 1)
    logs = support / "Logs"
    lua_log = logs / "lua.log"
    if lua_log.is_file():
        shutil.copy2(lua_log, match_dir / "telemetry.log")
    exceptions = sorted(logs.glob("exception-*.log")) if logs.is_dir() else []
    for exception in exceptions:
        shutil.copy2(exception, match_dir / exception.name)
    replays = sorted((support / "Replays").rglob("*.orarep")) if (support / "Replays").is_dir() else []
    replay = None
    if replays:
        replay = match_dir / "replay.orarep"
        shutil.copy2(replays[-1], replay)
        # Keep the exact fixture map beside the replay so it can be played back.
        pack_map(support / user_map_dir(mods / match.mod, match.mod) / fixture, match_dir / (fixture + ".oramap"))
    telemetry = parse_telemetry((match_dir / "telemetry.log").read_text(encoding="utf-8", errors="replace")
                                if (match_dir / "telemetry.log").is_file() else "", match.id)
    lua_errors = [line for line in (match_dir / "telemetry.log").read_text(errors="replace").splitlines()
                  if "Fatal Lua Error" in line or "Lua error" in line] if (match_dir / "telemetry.log").is_file() else []
    outcome = decide_outcome(telemetry, exit_code, status, exceptions, lua_errors)
    result = {
        "schema": SCHEMA, "match": match.to_dict(), "status": outcome["status"], "outcome": outcome,
        "exit_code": exit_code, "wall_seconds": wall, "exceptions": [p.name for p in exceptions],
        "lua_errors": lua_errors[:5], "replay": replay.name if replay else None,
        "engine_random_seed": engine_seed(replay) if replay else None,
        "harness_timestep_ms": HARNESS_TIMESTEP, "settings": settings, "telemetry": telemetry,
    }
    result_path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    if not keep_support and outcome["status"] == "complete":
        clear_tree(support)
    return result


def pack_map(folder: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.iterdir()):
            archive.write(path, path.name)


def replay_check(result_path: Path, *, engine: Path, mods: Path, content: Path, guard: float = 1800,
                 dotnet: str = "dotnet") -> dict:
    """Play a match's replay back headless and compare its telemetry.

    The replay carries every order and the engine seed, and the saved map
    carries the telemetry script, so an exact playback must re-emit exactly
    the telemetry recorded during the match. Any difference means the replay
    is not a faithful record (or the simulation is not deterministic).
    """
    result = json.loads(result_path.read_text(encoding="utf-8"))
    match = result["match"]
    match_dir = result_path.parent
    maps = sorted(match_dir.glob("*.oramap"))
    if not result.get("replay") or not maps:
        return {"match": match["id"], "status": "skipped", "reason": "no replay or map"}
    check = match_dir / "replay-check"
    if check.exists():
        clear_tree(check)
    check.mkdir()
    link_directory(check / "Content", content)
    map_dir = check / user_map_dir(mods / match["mod"], match["mod"])
    map_dir.mkdir(parents=True)
    shutil.copy2(maps[0], map_dir / maps[0].name)
    # The viewer's experience selection loads the rules; use the match's own.
    (check / "settings.yaml").write_text(result.get("settings", ""), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("OPENRA_AI_")}
    env.update(OPENRA_AI_DISABLE_AUTOSTART="1", DOTNET_ROLL_FORWARD=env.get("DOTNET_ROLL_FORWARD", "Major"))
    command = [dotnet, str(engine / "bin" / "OpenRA.dll"), f"Engine.EngineDir={engine}",
               f"Engine.ModSearchPaths={mods}", f"Engine.SupportDir={check}", f"Game.Mod={match['mod']}",
               "Game.Platform=Null", "Game.FetchNews=false",
               f"Launch.Replay={match_dir / result['replay']}", "Launch.Benchmark=benchmark-"]
    started = time.monotonic()
    with (check / "game.log").open("w", encoding="utf-8", errors="replace") as log:
        process = subprocess.Popen(command, cwd=engine / "bin", env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            exit_code = process.wait(timeout=guard)
            hung = False
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code, hung = process.wait(timeout=30), True
    lua_log = check / "Logs" / "lua.log"
    replayed = parse_telemetry(lua_log.read_text(encoding="utf-8", errors="replace") if lua_log.is_file() else "",
                               match["id"])
    original = result["telemetry"]
    differences = [key for key in ("players", "samples", "produced", "placed", "lost", "events")
                   if json.loads(json.dumps(replayed[key])) != original[key]]
    game_log = (check / "game.log").read_text(encoding="utf-8", errors="replace")
    report = {"match": match["id"], "status": "identical" if not differences and not hung else "different",
              "differences": differences, "exit_code": exit_code, "hung": hung,
              "out_of_sync": any((check / "Logs").glob("syncreport-*.log")) or "out of sync" in game_log.lower(),
              "wall_seconds": round(time.monotonic() - started, 1),
              "events": {k: len(replayed[k]) for k in ("produced", "placed", "lost")},
              "samples": sum(len(v) for v in replayed["samples"].values())}
    (match_dir / "replay-check.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    if report["status"] == "identical":
        clear_tree(check)
    return report


# ------------------------------------------------------------- telemetry

SAMPLE_FIELDS = ("cash", "resources", "kills_cost", "deaths_cost", "units_killed", "units_lost",
                 "buildings_killed", "buildings_lost", "army_value", "armed_units", "unit_spend",
                 "building_spend", "actors")


def parse_telemetry(text: str, match_id: str) -> dict:
    players: dict[str, dict] = {}
    samples: dict[str, list] = {}
    produced: list = []
    placed: list = []
    lost: list = []
    events = {"won": [], "defeated": [], "cap": None}
    record = _telemetry_recorder(players, samples, produced, placed, lost, events)
    malformed = 0
    prefix = f"BALANCE|{match_id}|"
    for line in text.splitlines():
        start = line.find(prefix)
        if start < 0:
            continue
        parts = line[start:].strip().split("|")
        try:
            record(parts[2], int(parts[3]), parts[4:])
        except (IndexError, ValueError):
            malformed += 1
    return {"players": players, "sample_fields": ["tick", *SAMPLE_FIELDS], "samples": samples,
            "produced": produced, "placed": placed, "lost": lost, "events": events, "malformed_lines": malformed}


def _telemetry_recorder(players, samples, produced, placed, lost, events):
    def record(kind: str, tick: int, fields: list[str]) -> None:
        if kind == "player":
            players[fields[0]] = {"faction": fields[1], "spawn": int(fields[2]), "bot": fields[3] == "true"}
        elif kind == "sample":
            samples.setdefault(fields[0], []).append([tick] + [int(v) for v in fields[1:]])
        elif kind == "produced":
            produced.append([tick, fields[0], fields[1], fields[2], int(fields[3])])
        elif kind == "starting":
            produced.append([tick, fields[0], fields[1], "Starting", int(fields[2])])
        elif kind == "placed":
            placed.append([tick, fields[0], fields[1], int(fields[2])])
        elif kind == "lost":
            lost.append([tick, fields[0], fields[1], fields[2], int(fields[3]), fields[4]])
        elif kind in ("won", "defeated"):
            events[kind].append([tick, fields[0]])
        elif kind == "cap":
            events["cap"] = tick
    return record


def decide_outcome(telemetry: dict, exit_code: int | None, status: str, exceptions: list, lua_errors: list) -> dict:
    events = telemetry["events"]
    last_tick = max((s[-1][0] for s in telemetry["samples"].values() if s), default=0)
    for group in (events["won"], events["defeated"]):
        last_tick = max([last_tick] + [tick for tick, _ in group])
    if status == "hang":
        return {"status": "hang", "result": "error", "reason": "wall-clock guard", "end_tick": last_tick}
    if exceptions or lua_errors or exit_code not in (0, None) or not telemetry["players"]:
        reason = "exception" if exceptions else "lua-error" if lua_errors else (
            "no-telemetry" if not telemetry["players"] else f"exit {exit_code}")
        return {"status": "crash", "result": "error", "reason": reason, "end_tick": last_tick}
    if events["cap"] is not None:
        return {"status": "complete", "result": "draw", "reason": "tick-cap", "end_tick": events["cap"]}
    winners = sorted({p for _, p in events["won"]})
    losers = sorted({p for _, p in events["defeated"]})
    if len(winners) == 1:
        tick = max(t for t, p in events["won"] if p == winners[0])
        return {"status": "complete", "result": "win", "winner": winners[0], "reason": "conquest", "end_tick": tick}
    if len(losers) == 1 and len(telemetry["players"]) == 2:
        winner = next(p for p in telemetry["players"] if p not in losers)
        tick = max(t for t, _ in events["defeated"])
        return {"status": "complete", "result": "win", "winner": winner, "reason": "conquest", "end_tick": tick}
    if len(losers) == 2:
        return {"status": "complete", "result": "draw", "reason": "mutual-defeat", "end_tick": last_tick}
    return {"status": "crash", "result": "error", "reason": "ended-without-result", "end_tick": last_tick}


# ------------------------------------------------------------ statistics

def wilson(successes: float, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval; draws may contribute half a success."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def minutes(ticks: int) -> float:
    return ticks / TICKS_PER_SECOND / 60


def sample_at(samples: list, tick: int) -> list | None:
    best = None
    for row in samples:
        if row[0] <= tick:
            best = row
        else:
            break
    return best


def stall_windows(result: dict, *, bank_threshold: int = 2000, min_ticks: int = 4500,
                  grace_ticks: int = 3000) -> dict[str, dict]:
    """Longest no-production window per slot while holding unspent money.

    A window counts only after ``grace_ticks`` (opening build) and only while
    the player's bank (cash + stored resources) stays at or above
    ``bank_threshold``; ``stalled`` marks windows of ``min_ticks`` or more.
    """
    telemetry = result["telemetry"]
    fields = telemetry["sample_fields"]
    cash, resources = fields.index("cash"), fields.index("resources")
    production: dict[str, list[int]] = {}
    for tick, player, *_ in telemetry["produced"] + telemetry["placed"]:
        production.setdefault(player, []).append(tick)
    report = {}
    for player, samples in telemetry["samples"].items():
        events = sorted(production.get(player, []))
        longest, start_tick, rich_since, index, last = 0, None, None, 0, grace_ticks
        for row in samples:
            tick = row[0]
            while index < len(events) and events[index] <= tick:
                last = max(last, events[index])
                index += 1
            if tick < grace_ticks:
                continue
            if row[cash] + row[resources] < bank_threshold:
                rich_since = None
                continue
            rich_since = tick if rich_since is None else rich_since
            start = max(last, rich_since)
            if tick - start > longest:
                longest, start_tick = tick - start, start
        report[player] = {"longest_ticks": longest, "start_tick": start_tick,
                          "stalled": longest >= min_ticks}
    return report


def idle_army_windows(result: dict, *, army_threshold: int = 3000, min_ticks: int = 7500) -> dict[str, dict]:
    """Longest window where a slot fielded a large army but destroyed nothing."""
    telemetry = result["telemetry"]
    fields = telemetry["sample_fields"]
    kills, army = fields.index("kills_cost"), fields.index("army_value")
    report = {}
    for player, samples in telemetry["samples"].items():
        longest, since, last_kills = 0, None, None
        for row in samples:
            if row[army] >= army_threshold and last_kills is not None and row[kills] == last_kills:
                since = row[0] if since is None else since
                longest = max(longest, row[0] - since)
            else:
                since = row[0] if row[army] >= army_threshold else None
            last_kills = row[kills]
        report[player] = {"longest_ticks": longest, "idle": longest >= min_ticks}
    return report


def slot_faction(result: dict, player: str) -> str:
    slot = int(player.removeprefix("Multi"))
    return result["match"]["factions"][slot]


def summarize(results: list[dict]) -> dict:
    complete = [r for r in results if r["status"] == "complete"]
    errors = [r for r in results if r["status"] != "complete"]
    suites: dict[str, dict] = {}
    for result in results:
        suites.setdefault(result["match"]["suite"], {"results": []})["results"].append(result)
    summary = {"schema": SCHEMA, "matches": len(results), "complete": len(complete), "errors": len(errors),
               "error_matches": [{"id": r["match"]["id"], "status": r["status"], "reason": r["outcome"]["reason"],
                                  "exceptions": r["exceptions"], "lua_errors": r["lua_errors"]} for r in errors],
               "suites": {}}
    for suite_id, suite in sorted(suites.items()):
        summary["suites"][suite_id] = summarize_suite([r for r in suite["results"] if r["status"] == "complete"],
                                                      suite["results"])
    return summary


def summarize_suite(complete: list[dict], all_results: list[dict]) -> dict:
    factions: dict[str, dict] = {}
    pairings: dict[str, dict] = {}
    lengths = []
    by_map: dict[str, list] = {}
    by_bot: dict[str, list] = {}
    for result in complete:
        match, outcome = result["match"], result["outcome"]
        a, b = match["factions"]
        end = outcome["end_tick"]
        lengths.append(end)
        by_map.setdefault(match["map_title"], []).append(result)
        by_bot.setdefault(match["bots"][0], []).append(result)
        winner = slot_faction(result, outcome["winner"]) if outcome["result"] == "win" else None
        winner_slot = outcome.get("winner")
        for slot, faction in enumerate((a, b)):
            opponent = (a, b)[1 - slot]
            f = factions.setdefault(faction, new_faction_stats())
            f["games"] += 1
            player = f"Multi{slot}"
            if outcome["result"] == "draw":
                f["draws"] += 1
            elif winner_slot == player:
                f["wins"] += 1
            else:
                f["losses"] += 1
            f["lengths"].append(end)
            accumulate_player(f, result, player)
            if faction == opponent:
                continue
            key = " vs ".join(sorted((faction, opponent)))
            p = pairings.setdefault(key, {"a": sorted((faction, opponent))[0], "b": sorted((faction, opponent))[1],
                                          "games": 0, "a_wins": 0, "b_wins": 0, "draws": 0, "lengths": []})
            if slot == 0:
                p["games"] += 1
                p["lengths"].append(end)
                if outcome["result"] == "draw":
                    p["draws"] += 1
                elif winner == p["a"]:
                    p["a_wins"] += 1
                else:
                    p["b_wins"] += 1
    for f in factions.values():
        finalize_faction(f)
    for p in pairings.values():
        score = p["a_wins"] + 0.5 * p["draws"]
        p["a_score"] = round(score / p["games"], 3) if p["games"] else None
        p["a_score_ci95"] = [round(v, 3) for v in wilson(score, p["games"])]
        p["median_minutes"] = round(minutes(statistics.median(p["lengths"])), 1) if p["lengths"] else None
        del p["lengths"]
    crashes = [r for r in all_results if r["status"] != "complete"]
    return {
        "games": len(complete),
        "errors": len(crashes),
        "error_reasons": count_by(crashes, lambda r: r["outcome"]["reason"]),
        "draws": sum(1 for r in complete if r["outcome"]["result"] == "draw"),
        "length_minutes": length_stats(lengths),
        "by_map": {name: {"games": len(rs), "draws": sum(1 for r in rs if r["outcome"]["result"] == "draw"),
                          "length_minutes": length_stats([r["outcome"]["end_tick"] for r in rs]),
                          "first_slot_score": round(sum(first_slot_score(r) for r in rs) / len(rs), 3)}
                   for name, rs in sorted(by_map.items())},
        "by_bot": {name: {"games": len(rs), "length_minutes": length_stats([r["outcome"]["end_tick"] for r in rs])}
                   for name, rs in sorted(by_bot.items())},
        "factions": dict(sorted(factions.items(), key=lambda kv: -(kv[1]["score"] or 0))),
        "pairings": dict(sorted(pairings.items())),
        "wall_seconds": round(sum(r["wall_seconds"] for r in all_results), 1),
    }


def first_slot_score(result: dict) -> float:
    outcome = result["outcome"]
    if outcome["result"] == "draw":
        return 0.5
    return 1.0 if outcome.get("winner") == "Multi0" else 0.0


def count_by(items, key) -> dict:
    counts: dict = {}
    for item in items:
        counts[key(item)] = counts.get(key(item), 0) + 1
    return counts


def length_stats(ticks: list[int]) -> dict:
    if not ticks:
        return {}
    values = sorted(minutes(t) for t in ticks)
    return {"mean": round(statistics.mean(values), 1), "median": round(statistics.median(values), 1),
            "p10": round(values[int(0.1 * (len(values) - 1))], 1), "p90": round(values[int(0.9 * (len(values) - 1))], 1),
            "max": round(values[-1], 1)}


def new_faction_stats() -> dict:
    return {"games": 0, "wins": 0, "losses": 0, "draws": 0, "lengths": [], "kills_cost": 0, "deaths_cost": 0,
            "produced": {}, "lost": {}, "economy": {m: [] for m in CHECKPOINT_MINUTES},
            "stalled_games": 0, "idle_army_games": 0, "longest_stall_minutes": [], "actor_types": {}}


def accumulate_player(stats: dict, result: dict, player: str) -> None:
    telemetry = result["telemetry"]
    fields = telemetry["sample_fields"]
    samples = telemetry["samples"].get(player, [])
    if samples:
        final = samples[-1]
        stats["kills_cost"] += final[fields.index("kills_cost")]
        stats["deaths_cost"] += final[fields.index("deaths_cost")]
    for tick, owner, actor, role, cost in telemetry["produced"]:
        if owner == player:
            row = stats["produced"].setdefault(role, {"count": 0, "value": 0})
            row["count"] += 1
            row["value"] += cost
            stats["actor_types"][actor] = stats["actor_types"].get(actor, 0) + 1
    for tick, owner, actor, cost in telemetry["placed"]:
        if owner == player:
            row = stats["produced"].setdefault("Building", {"count": 0, "value": 0})
            row["count"] += 1
            row["value"] += cost
    for tick, owner, actor, role, cost, killer in telemetry["lost"]:
        if owner == player:
            row = stats["lost"].setdefault(role, {"count": 0, "value": 0})
            row["count"] += 1
            row["value"] += cost
    def funds(row: list) -> tuple[int, int]:
        bank = row[fields.index("cash")] + row[fields.index("resources")]
        return bank, row[fields.index("unit_spend")] + row[fields.index("building_spend")]

    # Starting funds: everything held or already spent at the first sample,
    # before any harvester has delivered.
    initial = sum(funds(samples[0])) if samples else 0
    for minute in CHECKPOINT_MINUTES:
        row = sample_at(samples, minute * 60 * TICKS_PER_SECOND)
        if row is None or row[0] < (minute * 60 - 20) * TICKS_PER_SECOND:
            continue  # The match ended before this checkpoint.
        bank, spend = funds(row)
        stats["economy"][minute].append({"bank": bank, "spend": spend, "earned": bank + spend - initial,
                                         "army": row[fields.index("army_value")]})
    stall = stall_windows(result).get(player)
    if stall:
        stats["stalled_games"] += int(stall["stalled"])
        stats["longest_stall_minutes"].append(minutes(stall["longest_ticks"]))
    idle = idle_army_windows(result).get(player)
    if idle:
        stats["idle_army_games"] += int(idle["idle"])


def finalize_faction(stats: dict) -> None:
    games = stats["games"]
    score = stats["wins"] + 0.5 * stats["draws"]
    stats["score"] = round(score / games, 3) if games else None
    stats["score_ci95"] = [round(v, 3) for v in wilson(score, games)]
    stats["cost_efficiency"] = round(stats["kills_cost"] / stats["deaths_cost"], 2) if stats["deaths_cost"] else None
    stats["length_minutes"] = length_stats(stats.pop("lengths"))
    economy = {}
    for minute, rows in stats["economy"].items():
        if rows:
            economy[str(minute)] = {
                "games": len(rows),
                "bank": round(statistics.mean(r["bank"] for r in rows)),
                "spend": round(statistics.mean(r["spend"] for r in rows)),
                "army": round(statistics.mean(r["army"] for r in rows)),
                # Earned since the start: spent plus banked, minus starting funds.
                "earned": round(statistics.mean(r["earned"] for r in rows)),
            }
    stats["economy"] = economy
    stalls = stats.pop("longest_stall_minutes")
    stats["median_longest_stall_minutes"] = round(statistics.median(stalls), 1) if stalls else None
    stats["top_actor_types"] = dict(sorted(stats["actor_types"].items(), key=lambda kv: -kv[1])[:8])
    del stats["actor_types"]


# --------------------------------------------------------------- report

def pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.0f}%"


def render_report(summary: dict, campaign: dict, matches_planned: int, meta: dict) -> str:
    lines = [f"# Balance campaign `{campaign['name']}`", "",
             f"Generated by `scripts/balance_harness.py` ({SCHEMA}). Seed {meta.get('seed')}; "
             f"{summary['complete']} of {matches_planned} planned matches complete, {summary['errors']} errors.",
             "Scores count a draw as half a win; intervals are 95% Wilson intervals. Game time is "
             "normal-speed equivalent (25 ticks/s).", ""]
    for suite_id, suite in summary["suites"].items():
        lines += [f"## Suite `{suite_id}`", "",
                  f"{suite['games']} complete games, {suite['draws']} draws (tick cap), {suite['errors']} errors"
                  + (f" ({', '.join(f'{k}: {v}' for k, v in suite['error_reasons'].items())})"
                     if suite["error_reasons"] else "")
                  + f". Match length (min): {fmt_lengths(suite['length_minutes'])}.", "",
                  "| Map | Games | Draws | Median min | First-slot score |", "|---|---:|---:|---:|---:|"]
        for name, row in suite["by_map"].items():
            lines.append(f"| {name} | {row['games']} | {row['draws']} | {row['length_minutes'].get('median', '—')} | "
                         f"{pct(row['first_slot_score'])} |")
        lines += ["", "### Factions", "",
                  "| Faction | Games | W-D-L | Score (95% CI) | Value destroyed / lost | Median min | Stalled games | Idle-army games |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for name, f in suite["factions"].items():
            ci = f["score_ci95"]
            lines.append(f"| {name} | {f['games']} | {f['wins']}-{f['draws']}-{f['losses']} | "
                         f"{pct(f['score'])} ({pct(ci[0])}–{pct(ci[1])}) | {f['cost_efficiency'] or '—'} | "
                         f"{f['length_minutes'].get('median', '—')} | {f['stalled_games']} | {f['idle_army_games']} |")
        lines += ["", "### Pairings (row faction's score)", "",
                  "| Pairing | Games | A wins | B wins | Draws | A score (95% CI) | Median min |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for key, p in suite["pairings"].items():
            ci = p["a_score_ci95"]
            lines.append(f"| **{p['a']}** vs {p['b']} | {p['games']} | {p['a_wins']} | {p['b_wins']} | {p['draws']} | "
                         f"{pct(p['a_score'])} ({pct(ci[0])}–{pct(ci[1])}) | {p['median_minutes']} |")
        lines += ["", "### Economy (mean per game at checkpoint)", "",
                  "Earned = credits harvested since the start (spent + banked - starting funds); army = build "
                  "cost of living armed units. Only games still running at a checkpoint contribute (n).", "",
                  "| Faction | " + " | ".join(f"{m} min earned / army" for m in CHECKPOINT_MINUTES[:4]) + " |",
                  "|---|" + "---:|" * 4]
        for name, f in suite["factions"].items():
            cells = []
            for minute in CHECKPOINT_MINUTES[:4]:
                row = f["economy"].get(str(minute))
                cells.append(f"{row['earned']:,} / {row['army']:,} (n={row['games']})" if row else "—")
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines += ["", "### Production and losses by role (count, value)", "",
                  "| Faction | Produced | Lost |", "|---|---|---|"]
        for name, f in suite["factions"].items():
            produced = ", ".join(f"{role} {row['count']} (${row['value']:,})" for role, row in sorted(f["produced"].items()))
            lost = ", ".join(f"{role} {row['count']} (${row['value']:,})" for role, row in sorted(f["lost"].items()))
            lines.append(f"| {name} | {produced} | {lost} |")
        lines.append("")
    replays = summary.get("replay_checks")
    if replays:
        lines += ["## Replay playback", "",
                  "Each checked replay was played back headless with its saved map; `identical` means the "
                  "playback re-emitted exactly the telemetry recorded live.", "",
                  "| Suite | Checked | Identical | Out of sync | Other |", "|---|---:|---:|---:|---:|"]
        for suite_id, row in sorted(replays.items()):
            lines.append(f"| {suite_id} | {row['checked']} | {row['identical']} | {row['out_of_sync']} | "
                         f"{row['checked'] - row['identical'] - row['out_of_sync']} |")
        lines.append("")
    if summary["error_matches"]:
        lines += ["## Errors", "", "| Match | Status | Reason | Exceptions |", "|---|---|---|---|"]
        for row in summary["error_matches"]:
            lines.append(f"| {row['id']} | {row['status']} | {row['reason']} | {', '.join(row['exceptions']) or '—'} |")
        lines.append("")
    return "\n".join(lines)


def fmt_lengths(stats: dict) -> str:
    if not stats:
        return "—"
    return f"median {stats['median']}, mean {stats['mean']}, p10 {stats['p10']}, p90 {stats['p90']}, max {stats['max']}"


# ------------------------------------------------------------------ CLI

def load_results(output: Path) -> list[dict]:
    results = []
    for path in sorted((output / "matches").glob("*/result.json")):
        results.append(json.loads(path.read_text(encoding="utf-8")))
    return results


def write_summary(output: Path, campaign: dict, planned: list[Match], meta: dict) -> dict:
    planned_ids = {m.id for m in planned}
    results = [r for r in load_results(output) if r["match"]["id"] in planned_ids]
    summary = summarize(results)
    summary.update(campaign=campaign["name"], seed=meta.get("seed"), planned=len(planned))
    checks = output / "replay-checks.json"
    if checks.is_file():
        suites = {r["match"]["id"]: r["match"]["suite"] for r in results}
        by_suite: dict[str, dict] = {}
        for check in json.loads(checks.read_text(encoding="utf-8")):
            if check["match"] not in suites or check["status"] == "skipped":
                continue
            row = by_suite.setdefault(suites[check["match"]], {"checked": 0, "identical": 0, "out_of_sync": 0})
            row["checked"] += 1
            row["identical"] += check["status"] == "identical"
            row["out_of_sync"] += bool(check.get("out_of_sync")) and check["status"] != "identical"
        summary["replay_checks"] = by_suite
    (output / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    (output / "report.md").write_text(render_report(summary, campaign, len(planned), meta) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run", "report", "replay"):
        p = sub.add_parser(name)
        p.add_argument("--campaign", default="baseline-2026-09")
        p.add_argument("--campaigns-file", type=Path, default=CAMPAIGNS)
        p.add_argument("--seed", type=int)
        p.add_argument("--suite", action="append", help="Limit to these suite ids")
        p.add_argument("--limit", type=int, help="Only the first N matches of the seeded order")
        if name in ("run", "report", "replay"):
            p.add_argument("--output", type=Path, required=True)
        if name in ("run", "replay"):
            p.add_argument("--engine", type=Path, default=ROOT / "engine/openra")
            p.add_argument("--content", type=Path, required=True, help="Directory containing ra/ and ra2/ content")
            p.add_argument("--ra2-mod", type=Path, help="Prepared RA2 mod directory (default: <engine>/mods/ra2)")
            p.add_argument("--parallel", type=int, default=4)
        if name == "replay":
            p.add_argument("--match", action="append", help="Match ids to play back (default: every match)")
        if name == "run":
            p.add_argument("--rerun", action="store_true", help="Rerun matches that already have results")
            p.add_argument("--keep-support", action="store_true")
    args = parser.parse_args(argv)
    campaign = load_campaign(args.campaign, args.campaigns_file)
    seed = campaign.get("seed", 0) if args.seed is None else args.seed
    matches = plan(campaign, seed, set(args.suite) if args.suite else None)
    if args.limit:
        matches = matches[:args.limit]
    meta = {"seed": seed}
    if args.command == "plan":
        for match in matches:
            print(json.dumps(match.to_dict()))
        print(f"{len(matches)} matches", file=sys.stderr)
        return 0
    output = absolute_path(args.output)  # Never an extended-length path; see native_fixture.
    output.mkdir(parents=True, exist_ok=True)
    if args.command == "report":
        summary = write_summary(output, campaign, matches, meta)
        print(json.dumps({k: summary[k] for k in ("matches", "complete", "errors")}))
        return 0
    engine = args.engine.resolve()
    ra2_mod = args.ra2_mod.resolve() if args.ra2_mod else None
    if args.command == "replay":
        mods = prepare_resources(engine, output, ra2_mod)
        wanted = set(args.match or [m.id for m in matches])
        paths = [output / "matches" / m / "result.json" for m in sorted(wanted)
                 if (output / "matches" / m / "result.json").is_file()]
        with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as executor:
            reports = list(executor.map(lambda path: replay_check(path, engine=engine, mods=mods,
                                                                  content=args.content.resolve()), paths))
        for report in reports:
            print(json.dumps(report), flush=True)
        previous = []
        if (output / "replay-checks.json").is_file():
            previous = [r for r in json.loads((output / "replay-checks.json").read_text(encoding="utf-8"))
                        if r["match"] not in {n["match"] for n in reports}]
        (output / "replay-checks.json").write_text(json.dumps(previous + reports, indent=1) + "\n", encoding="utf-8")
        write_summary(output, campaign, matches, meta)
        return 0 if all(r["status"] in ("identical", "skipped") for r in reports) else 3
    if any(m.mod == "ra2" for m in matches) and ra2_mod is None and not (engine / "mods/ra2/mod.yaml").is_file():
        raise SystemExit("RA2 suites need --ra2-mod (see scripts/prepare-local-ra2.py)")
    mods = prepare_resources(engine, output, ra2_mod)
    (output / "campaign.json").write_text(json.dumps({"campaign": campaign, "seed": seed, "planned": [
        m.to_dict() for m in matches]}, indent=1) + "\n", encoding="utf-8")
    pending = [m for m in matches if args.rerun or not (output / "matches" / m.id / "result.json").is_file()]
    print(f"{len(matches)} planned, {len(pending)} to run, parallel {args.parallel}", flush=True)
    started = time.monotonic()
    done = 0

    def work(match: Match) -> dict:
        try:
            return run_match(match, engine=engine, mods=mods, content=args.content.resolve(), output=output,
                             campaign=campaign, keep_support=args.keep_support)
        except Exception as exc:  # Harness/fixture failure: record, keep going.
            failure = {"schema": SCHEMA, "match": match.to_dict(), "status": "harness-error",
                       "outcome": {"status": "harness-error", "result": "error", "reason": str(exc), "end_tick": 0},
                       "exit_code": None, "wall_seconds": 0, "exceptions": [], "lua_errors": [], "replay": None,
                       "telemetry": parse_telemetry("", match.id)}
            path = output / "matches" / match.id
            path.mkdir(parents=True, exist_ok=True)
            (path / "result.json").write_text(json.dumps(failure, indent=1) + "\n", encoding="utf-8")
            return failure

    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as executor:
        for result in executor.map(work, pending):
            done += 1
            outcome = result["outcome"]
            print(f"[{done}/{len(pending)} {time.monotonic() - started:.0f}s] {result['match']['id']}: "
                  f"{outcome['result']} {outcome.get('winner', '')} {outcome['reason']} "
                  f"@{minutes(outcome['end_tick']):.1f}min wall {result['wall_seconds']}s", flush=True)
    summary = write_summary(output, campaign, matches, meta)
    print(json.dumps({k: summary[k] for k in ("matches", "complete", "errors")}))
    return 0 if summary["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
