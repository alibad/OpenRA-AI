#!/usr/bin/env python3
"""Check native AUTO combined-arms recruitment in isolated RA2 test matches.

This is a FULL-TECH, FAST-BUILD, 50,000-CREDIT fixture, not a normal-start
economy or balance benchmark. Technology prerequisites remain enabled; their
real buildings are prebuilt. No combat units are granted or manually queued.
The opponent is an inert range bot with a durable target construction yard.
The base-builder module is disabled in this fixture so its unrelated expansion
cannot consume the finite recruitment budget on a map without ore income.
Each match has its own support profile and bridge port. The packaged stage is
copied before launch, retaining its platform-native libraries and RA2 adapter.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time

from openra_ai_companion.bridge import OpenRABridge
from ra2_china_assets import CHINA_UNITS
from ra2_iran_assets import UNITS as IRAN_UNITS
from ra2_turkey_assets import TURKEY_UNITS

SPEC = importlib.util.spec_from_file_location("turkey_fixture", Path(__file__).with_name("validate-ra2-turkey.py"))
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

ROSTERS = {"china": set(CHINA_UNITS), "iran": set(IRAN_UNITS), "turkey": set(TURKEY_UNITS)}
GROUPS = {
    "china": {"line_infantry": {"r2cnrifle"}, "main_battle_tank": {"r2qilin"},
              "anti_air": {"r2mantis"}, "artillery": {"r2phl"},
              "aircraft": {"r2cloud", "r2skyspear"},
              "naval": {"r2luyang", "r2haiwang", "r2haiying", "r2jiaolong"}},
    "iran": {"line_infantry": {"r2basij"}, "main_battle_tank": {"r2karrar"},
             "anti_air": {"r2raad"}, "artillery": {"r2fajr", "r2coast"},
             "aircraft": {"r2mohajer", "r2toufan", "r2azar", "r2loiter"},
             "naval": {"r2peykaap", "r2ghadir"}},
    "turkey": {"line_infantry": {"r2trrifle"}, "main_battle_tank": {"r2bozkir"},
               "anti_air": {"r2gokkalkan"}, "artillery": {"r2yildirim"},
               "aircraft": {"r2kuzgun", "r2turna", "r2sahin"},
               "naval": {"r2poyraz", "r2ege"}},
}
NATIVES = ("SDL2.dylib", "freetype6.dylib", "lua51.dylib", "soft_oal.dylib")


def fixture(resources: Path, profile: Path, country: str) -> dict[str, int]:
    target = BASE.fixture(resources, profile)
    text = (target / "map.yaml").read_text().replace("Faction: turkey", "Faction: " + country)
    text = text.replace("EnemyBase: nacnst", "EnemyBase: composition-target")
    if country == "iran":
        for old, new in (("gacnst", "nacnst"), ("gaweap", "naweap"), ("gapowr", "napowr"),
                         ("garefn", "narefn"), ("gaairc", "naradr"), ("gapile", "nahand"),
                         ("gatech", "natech"), ("gayard", "nayard")):
            text = text.replace(": " + old + "\n", ": " + new + "\n")
    power = "napowr" if country == "iran" else "gapowr"
    extra = "".join(f"\tRangePower{i}: {power}\n\t\tOwner: Multi0\n\t\tLocation: {25+i*8},-10\n"
                    for i in range(2))
    if country != "iran":
        extra += "\tAirfield2: gaairc\n\t\tOwner: Multi0\n\t\tLocation: 74,-25\n"
    text = text.replace("Rules:\n", extra + "Rules:\n")
    text = text.replace("\tPlayer:\n", "\tPlayer:\n\t\tModularBot@range:\n\t\t\tName: ra2-bot-normal\n\t\t\tType: range-target\n")
    text = text.replace("\tPlayer:\n", "\tPlayer:\n\t\t-BaseBuilderBotModule@normal:\n")
    text += ("\tcomposition-target:\n\t\tInherits: nacnst\n\t\tRenderSprites:\n\t\t\tImage: nacnst\n"
             "\t\tHealth:\n\t\t\tHP: 100000000\n")
    (target / "map.yaml").write_text(text)
    # Rally only sets the fixture's factory exit; AUTO chooses every recruit.
    (target / "review.lua").write_text(
        'WorldLoaded = function()\n  Player.GetPlayer("Multi0").Cash = 50000\n'
        '  Factory0.RallyPoint = CPos.New(56, -3)\n  Factory5.RallyPoint = CPos.New(80, 0)\n'
        '  Yard.RallyPoint = CPos.New(85, 40)\nend\n')
    limits = {}
    for suffix in (".yaml", "-ai.yaml"):
        rules = (resources / "mods/ra2/modern-factions" / (country + suffix)).read_text()
        normal = rules.split("\tUnitBuilderBotModule@normal:\n", 1)[1].split("\n\tUnitBuilderBotModule@", 1)[0]
        match = re.search(r"\t\tUnitLimits:\n((?:\t\t\t[^\n]+\n)+)", normal)
        if match:
            limits.update({name: int(value) for name, value in re.findall(r"\t\t\t(\w+): (\d+)", match.group(1))})
    return limits


def run(country: str, resources: Path, binaries: Path, content: Path, output: Path, seconds: int) -> dict:
    profile = Path(tempfile.mkdtemp(prefix=country + "-", dir=output))
    (profile / "Content").symlink_to(content, target_is_directory=True)
    limits = fixture(resources, profile, country)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = {**os.environ, "OPENRA_AI_COMPANION": "1", "OPENRA_AI_COMPANION_READY": "1",
                   "OPENRA_AI_STARTUP_ENABLED": "1", "OPENRA_AI_STARTUP_AUTO_ACT": "1",
                   "OPENRA_AI_STARTUP_STRATEGY": "normal", "OPENRA_AI_STARTUP_MUTED": "1",
                   "OPENRA_AI_GRPC_PORT": str(port)}
    command = ["dotnet", str(binaries / "OpenRA.dll"), f"Engine.EngineDir={resources}",
               f"Engine.SupportDir={profile}", "Game.Mod=ra2", "Game.FetchNews=false", "Game.Platform=Null",
               "Launch.Map=modern-art-review", "Launch.Bots=Multi1:range-target"]
    report = {"country": country, "passed": False, "profile": str(profile), "bridge_port": port,
              "fixture": "prebuilt full technology, fast build, 50000 starting credits, inert enemy, base expansion disabled",
              "base_expansion_disabled": True, "starting_credits": 50000, "credit_topups": 0,
              "normal_game_balance_proof": False, "manual_recruitment_orders": 0,
              "configured_unit_limits": limits, "first_seen_tick": {}, "max_simultaneous_units": {}}
    started = time.monotonic()
    observed = set()
    with (profile / "game.log").open("w") as log:
        process = subprocess.Popen(command, cwd=binaries, env=environment, stdout=log, stderr=subprocess.STDOUT)
        bridge = OpenRABridge(f"127.0.0.1:{port}", timeout=1)
        try:
            last_progress = started
            while process.poll() is None and time.monotonic() - started < seconds:
                try:
                    state = bridge.observe()
                except RuntimeError as error:
                    report["last_connection_error"] = str(error)
                    time.sleep(.2)
                    continue
                if state.done:
                    raise ValueError("Fixture match ended unexpectedly")
                available = set(state.available_production)
                if "available_production" not in report:
                    session = bridge.state()
                    if session.get("player_faction") != country:
                        raise ValueError("Incorrect local faction: " + str(session.get("player_faction")))
                    report["session"] = session
                    # Already recruited build-limit-one commandos disappear from
                    # buildable choices, so accept the real owned actor as proof.
                    missing = ROSTERS[country] - available - {unit.kind for unit in state.units}
                    if missing:
                        raise ValueError("Prebuilt fixture is missing technology for: " + str(sorted(missing)))
                    report["available_production"] = sorted(available)
                counts = Counter(unit.kind for unit in state.units)
                observed.update(counts)
                foreign = (observed | available) & set.union(*(roster for name, roster in ROSTERS.items() if name != country))
                if foreign:
                    raise ValueError("Foreign faction recruits or production choices: " + str(sorted(foreign)))
                for name, count in counts.items():
                    report["first_seen_tick"].setdefault(name, state.tick)
                    report["max_simultaneous_units"][name] = max(count, report["max_simultaneous_units"].get(name, 0))
                    if name in limits and count > limits[name]:
                        raise ValueError(f"Native AI exceeded {name} limit {limits[name]}: {count}")
                report["tick"] = state.tick
                report["cash"] = state.cash
                report["last_production"] = state.production
                report["power"] = {"provided": state.power_provided, "drained": state.power_drained}
                report["observed_units"] = sorted(observed)
                report["role_evidence"] = {role: sorted(choices & observed) for role, choices in GROUPS[country].items()}
                # Keep AUTO active. Sending "ready" here would turn it OFF.
                bridge.update_companion_status("auto-active:normal", "Private native AI composition validation", muted=True)
                if time.monotonic() - last_progress > 25:
                    print(json.dumps({"progress": country, "tick": state.tick, "roles": report["role_evidence"]}), flush=True)
                    last_progress = time.monotonic()
                time.sleep(.15)
            report["elapsed_seconds"] = round(time.monotonic() - started, 2)
            report["process_exit"] = process.poll()
            report["missing_roles"] = [role for role in GROUPS[country] if not report.get("role_evidence", {}).get(role)]
            report["limits_checked"] = {name: {"maximum": report["max_simultaneous_units"].get(name, 0), "limit": limit}
                                        for name, limit in limits.items()}
            native_logs = list((profile / "Logs").glob("*rl-bridge*"))
            report["native_auto_delegation_logged"] = any("Native assistant delegated the local player to OpenRA normal AI."
                                                          in path.read_text() for path in native_logs)
            report["passed"] = not report["missing_roles"] and report["native_auto_delegation_logged"] and process.poll() is None
            if not report["passed"]:
                report["error"] = "Missing composition roles, native delegation evidence, or process exited"
        except Exception as error:
            report["error"] = str(error)
        finally:
            bridge.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    (profile / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--binaries", type=Path, required=True)
    parser.add_argument("--managed-binaries", type=Path, help="Optional freshly built engine DLL/PDB overlay; never copies native dylibs")
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--factions", nargs="+", choices=tuple(ROSTERS), default=list(ROSTERS))
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="runtime-", dir=args.output))
    resources, binaries = stage / "Resources", stage / "binaries"
    shutil.copytree(args.resources, resources)
    shutil.copytree(args.binaries, binaries)
    if args.managed_binaries:
        for pattern in ("OpenRA*.dll", "OpenRA*.pdb", "OpenRA*.deps.json"):
            for source in args.managed_binaries.glob(pattern):
                shutil.copy2(source, binaries / source.name)
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in binaries.glob("OpenRA*.dll")}
    natives = subprocess.check_output(["file", *(str(binaries / name) for name in NATIVES)], text=True)
    if os.uname().machine == "arm64" and any("arm64" not in line for line in natives.splitlines()):
        raise SystemExit("Runtime must retain all four arm64 native libraries: " + natives)
    # Separate spawned Python workers avoid forking a game while another thread
    # has a live gRPC channel (which can stall gRPC's fork synchronization).
    with ProcessPoolExecutor(max_workers=len(args.factions), mp_context=multiprocessing.get_context("spawn")) as pool:
        jobs = [pool.submit(run, country, resources, binaries, args.content.resolve(), args.output, args.seconds)
                for country in args.factions]
        results = [job.result() for job in jobs]
    summary = {"passed": all(result["passed"] for result in results), "runtime": str(stage),
               "managed_sha256": hashes, "native_libraries": natives, "results": results}
    (args.output / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
