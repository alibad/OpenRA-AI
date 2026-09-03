#!/usr/bin/env python3
"""Run bounded RA2 map/AUTO smoke tests without touching the player's profile."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time

from openra_ai_companion.bridge import OpenRABridge
from openra_ai_companion.models import ActionCommand


def check_map(resources: Path, binaries: Path, content: Path, output: Path, name: str, ticks: int,
              movement: bool = False, timeout: float = 35, faction: str | None = None,
              require_unit: str | None = None, verify_deployment: bool = False) -> dict:
    profile = Path(tempfile.mkdtemp(prefix=name + "-", dir=output))
    (profile / "Content").symlink_to(content, target_is_directory=True)
    launch_map = name
    if faction:
        launch_map = name + "-validation"
        manifest = (resources / "mods/ra2/mod.yaml").read_text()
        user_maps = re.search(r"^\t~\^SupportDir\|(maps/ra2/[^:\n]+): User$", manifest, re.MULTILINE)
        if user_maps is None:
            raise ValueError("RA2 manifest has no versioned user-map directory")
        fixture = profile / user_maps.group(1) / launch_map
        shutil.copytree(resources / "mods/ra2/maps" / name, fixture)
        map_yaml = fixture / "map.yaml"
        text = map_yaml.read_text()
        text = re.sub(r"(\tPlayerReference@Multi\d+:\n(?:(?!\tPlayerReference)[^\n]*\n)*?\t\tFaction:) Random",
                      rf"\g<1> {faction}\n\t\tLockFaction: True", text)
        map_yaml.write_text(text)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {**os.environ, "OPENRA_AI_COMPANION": "1", "OPENRA_AI_COMPANION_READY": "1",
           "OPENRA_AI_STARTUP_AUTO_ACT": "0" if movement else "1", "OPENRA_AI_STARTUP_ENABLED": "1",
           "OPENRA_AI_STARTUP_MUTED": "1", "OPENRA_AI_GRPC_PORT": str(port)}
    command = ["dotnet", str(binaries / "OpenRA.dll"), f"Engine.EngineDir={resources}",
               f"Engine.SupportDir={profile}", "Game.Mod=ra2", "Game.Platform=Null",
               "Game.FetchNews=false", f"Launch.Map={launch_map}", "Launch.Bots=Multi1:normal"]
    result = {"map": name, "passed": False, "log": str(profile / "game.log")}
    with (profile / "game.log").open("w") as log:
        process = subprocess.Popen(command, cwd=binaries, env=env, stdout=log, stderr=subprocess.STDOUT)
        bridge = OpenRABridge(f"127.0.0.1:{port}", timeout=0.5)
        try:
            deadline = time.monotonic() + timeout
            last_error = "No game observation"
            move_target = None
            observed_units = set()
            deployment = None
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    snapshot = bridge.observe()
                    observed_units.update(unit.kind for unit in snapshot.units)
                    if movement:
                        mcv = next((unit for unit in snapshot.units if unit.kind in {"amcv", "smcv"}), None)
                        if mcv is None:
                            raise ValueError("No starting MCV for movement verification")
                        if move_target is None:
                            move_target = (mcv.cell_x + 2, mcv.cell_y + 2)
                            receipt = bridge.execute_actions("ra2-movement-smoke", snapshot.tick, (
                                ActionCommand("move", actor_id=mcv.actor_id,
                                              target_x=move_target[0], target_y=move_target[1]),))
                            result["movement"] = {"from": [mcv.cell_x, mcv.cell_y], "target": move_target,
                                                  "receipt": receipt.as_dict()}
                            if not receipt.accepted:
                                raise ValueError("Movement order rejected")
                        elif (mcv.cell_x, mcv.cell_y) == move_target:
                            result["movement"]["arrived_tick"] = snapshot.tick
                            result.update(passed=not snapshot.done and snapshot.mod_id == "ra2",
                                          tick=snapshot.tick, mod=snapshot.mod_id)
                            break
                        bridge.update_companion_status("ready", "RA2 movement validation", muted=True)
                        time.sleep(0.15)
                        continue
                    if snapshot.tick >= ticks:
                        result.update(tick=snapshot.tick, mod=snapshot.mod_id,
                                      buildings=[actor.kind for actor in snapshot.buildings],
                                      state=bridge.state(), names=snapshot.actor_names,
                                      observed_units=sorted(observed_units))
                        if snapshot.mod_id != "ra2" or snapshot.done:
                            raise ValueError("Wrong game or match ended during startup")
                        if not any(actor.kind in {"gacnst", "nacnst"} for actor in snapshot.buildings):
                            raise ValueError("AUTO did not deploy the starting MCV")
                        if require_unit and require_unit not in observed_units:
                            last_error = f"AUTO has not produced {require_unit}"
                            time.sleep(0.15)
                            continue
                        if verify_deployment:
                            bridge.update_companion_status("ready", "Verifying GI deployment", muted=True)
                            gi = next((unit for unit in snapshot.units if unit.kind == "e1" and
                                      (deployment is None or unit.actor_id == deployment["actor_id"])), None)
                            if gi is None:
                                last_error = "No surviving GI for deployment verification"
                                time.sleep(0.15)
                                continue
                            if deployment is None:
                                receipt = bridge.execute_actions("ra2-deployment-smoke", snapshot.tick, (
                                    ActionCommand("deploy", actor_id=gi.actor_id),))
                                if not receipt.accepted:
                                    raise ValueError("GI deployment rejected")
                                deployment = {"actor_id": gi.actor_id, "initial_range": gi.attack_range,
                                              "receipt": receipt.as_dict()}
                                result["deployment"] = deployment
                            elif gi.attack_range > deployment["initial_range"]:
                                deployment.update(deployed_range=gi.attack_range, tick=snapshot.tick)
                                result["passed"] = True
                                break
                            last_error = "GI did not switch to its deployed weapon range"
                            time.sleep(0.15)
                            continue
                        result["passed"] = True
                        break
                    bridge.update_companion_status("auto-active:normal", "RA2 validation", muted=True)
                except RuntimeError as error:
                    last_error = str(error)
                time.sleep(0.15)
            if not result["passed"]:
                result["error"] = f"Exit {process.poll()}: {last_error}"
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
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--binaries", type=Path, required=True)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maps", nargs="*")
    parser.add_argument("--ticks", type=int, default=150)
    parser.add_argument("--verify-movement", action="store_true", help="Check a manual MCV movement order instead of AUTO deployment")
    parser.add_argument("--timeout", type=float, default=35, help="Maximum wall-clock seconds per map")
    parser.add_argument("--faction", choices=("france", "iraq"), help="Lock both players in a private copy of each map")
    parser.add_argument("--require-unit", help="Wait for AUTO to produce this actor type")
    parser.add_argument("--verify-deployment", action="store_true", help="After AUTO play, deploy a GI and verify its weapon range changes")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    maps = args.maps or sorted(path.parent.name for path in (args.resources / "mods/ra2/maps").glob("*/map.yaml")
                              if "Visibility: Lobby" in path.read_text())
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda name: check_map(args.resources.resolve(), args.binaries.resolve(),
                       args.content.resolve(), args.output.resolve(), name, args.ticks, args.verify_movement,
                       args.timeout, args.faction, args.require_unit, args.verify_deployment), maps))
    (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    raise SystemExit(0 if results and all(result["passed"] for result in results) else 1)
