#!/usr/bin/env python3
"""Verify real RA2 production/roles/movement for each modern country.

Uses private flat maps with prebuilt native factories and fast-build ONLY to
bound smoke-test duration. Does not bypass tech prerequisites or unit costs.
Normal-speed AUTO-from-MCV tests are separate (validate-ra2.py --require-unit).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time

from openra_ai_companion.bridge import OpenRABridge
from openra_ai_companion.models import ActionCommand

SPEC = importlib.util.spec_from_file_location("art_review", Path(__file__).with_name("validate-ra2-faction-art.py"))
ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)
ROSTERS = dict(zip(("china", "iran", "turkey"), ART.UNITS))


def verify(resources, binaries, content, output, country):
    profile = Path(tempfile.mkdtemp(prefix=country + "-", dir=output))
    (profile / "Content").symlink_to(content, target_is_directory=True)
    target = ART.fixture(resources, profile)
    text = (target / "map.yaml").read_text()
    text = re.sub(r"^\t(?:r2\w+|Reference\d+):[^\n]*\n(?:\t\t[^\n]*\n)*", "", text, flags=re.MULTILINE)
    text = text.replace("Faction: china", "Faction: " + country)
    side = "na" if country == "iran" else "ga"
    text = text.replace("ReviewBase: gacnst", "ReviewBase: " + side + "cnst")
    text = text.replace("\t\tLocation: 74,0\n", "\t\tLocation: 74,15\n")
    buildings = (side + "weap", side + "powr", side + "powr", side + "refn",
                 "naradr" if country == "iran" else "gaairc", "nahand" if country == "iran" else "gapile")
    actors = ""
    for i, building in enumerate(buildings):
        # RA2 factories are five cells wide and exit at +4,+1. Keep the
        # neighboring power plant out of the exit/rally corridor.
        actors += f"\tProduction{i}: {building}\n\t\tOwner: Multi0\n\t\tLocation: {52 + i*8},0\n"
    text = text.replace("Rules:\n", actors + "Rules:\n")
    text = text.replace("\tPlayer:\n", "\tPlayer:\n\t\tDeveloperMode:\n\t\t\tCheckboxEnabled: true\n\t\t\tFastBuild: true\n")
    (target / "map.yaml").write_text(text)
    (target / "review.lua").write_text("WorldLoaded = function() Camera.Position = ReviewBase.CenterPosition end\n")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {**os.environ, "OPENRA_AI_COMPANION": "1", "OPENRA_AI_COMPANION_READY": "1",
           "OPENRA_AI_STARTUP_ENABLED": "1", "OPENRA_AI_STARTUP_AUTO_ACT": "0",
           "OPENRA_AI_STARTUP_MUTED": "1", "OPENRA_AI_GRPC_PORT": str(port)}
    command = ["dotnet", str(binaries / "OpenRA.dll"), f"Engine.EngineDir={resources}",
               f"Engine.SupportDir={profile}", "Game.Mod=ra2", "Game.Platform=Null",
               "Game.FetchNews=false", "Launch.Map=modern-art-review"]
    result = {"faction": country, "passed": False, "profile": str(profile), "fast_build": True,
              "prebuilt_native_economy": True, "all_tech_cheat": False}
    with (profile / "game.log").open("w") as log:
        process = subprocess.Popen(command, cwd=binaries, env=env, stdout=log, stderr=subprocess.STDOUT)
        bridge = OpenRABridge(f"127.0.0.1:{port}", timeout=1)
        try:
            deadline = time.monotonic() + 65
            queued = False
            destination = None
            last_error = "No observation"
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    state = bridge.observe()
                    result["last_state"] = {"tick": state.tick, "units": [u.kind for u in state.units],
                        "production": state.production, "cash": state.cash,
                        "buildings": [{"kind": b.kind, "powered": b.powered, "producing": b.producing_item} for b in state.buildings]}
                    if not queued:
                        available = set(state.available_production)
                        if not set(ROSTERS[country]) <= available:
                            raise ValueError("Missing signature production: " + str(set(ROSTERS[country]) - available))
                        foreign = {unit for c, units in ROSTERS.items() if c != country for unit in units}
                        if available & foreign:
                            raise ValueError("Foreign country units incorrectly unlocked")
                        receipt = bridge.execute_actions("modern-roster-smoke", state.tick,
                            tuple(ActionCommand("train", item_type=actor) for actor in ROSTERS[country]))
                        if not receipt.accepted:
                            raise ValueError("Production rejected: " + str(receipt.as_dict()))
                        result["production_receipt"] = receipt.as_dict()
                        result["production_available"] = sorted(available)
                        queued = True
                    units = {u.kind: u for u in state.units if u.kind in ROSTERS[country]}
                    if len(units) == 4:
                        result["units"] = {kind: {"weapon": u.weapon, "air": u.can_target_air,
                            "ground": u.can_target_ground, "range": u.attack_range, "minimum_range": u.minimum_attack_range}
                            for kind, u in units.items()}
                        for kind, u in units.items():
                            if not u.can_attack or not u.weapon:
                                raise ValueError(kind + " has no working weapon")
                            if kind in ("r2mantis", "r2raad") and (not u.can_target_air or u.can_target_ground):
                                raise ValueError(kind + " must be air-only")
                        tank = units[ROSTERS[country][0]]
                        if destination is None:
                            # Fixed clear map-storage cell, south of the factory
                            # corridor. A relative +2,+2 can land inside the next
                            # power plant depending on the precise exit tick.
                            destination = (25, 64)
                            receipt = bridge.execute_actions("modern-movement-smoke", state.tick,
                                (ActionCommand("move", actor_id=tank.actor_id, target_x=destination[0], target_y=destination[1]),))
                            if not receipt.accepted:
                                raise ValueError("Tank movement rejected")
                        elif (tank.cell_x, tank.cell_y) == destination:
                            result.update(passed=not state.done, tick=state.tick, movement_target=destination,
                                          final_facing=tank.facing, cash=state.cash)
                            break
                    bridge.update_companion_status("ready", "Roster validation", muted=True)
                    last_error = "Waiting for production or movement completion"
                except RuntimeError as error:
                    last_error = str(error)
                time.sleep(0.15)
            if not result["passed"]:
                result["error"] = last_error
        except Exception as error:
            result["error"] = str(error)
        finally:
            bridge.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("resources", "binaries", "content", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    values = [getattr(args, key).resolve() for key in ("resources", "binaries", "content", "output")]
    values[-1].mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda country: verify(*values, country), ROSTERS))
    (values[-1] / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)
