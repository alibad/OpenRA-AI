#!/usr/bin/env python3
"""Run bounded RA2 map/AUTO smoke tests without touching the player's profile."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

from openra_ai_companion.bridge import OpenRABridge


def check_map(resources: Path, binaries: Path, content: Path, output: Path, name: str, ticks: int) -> dict:
    profile = Path(tempfile.mkdtemp(prefix=name + "-", dir=output))
    (profile / "Content").symlink_to(content, target_is_directory=True)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {**os.environ, "OPENRA_AI_COMPANION": "1", "OPENRA_AI_COMPANION_READY": "1",
           "OPENRA_AI_STARTUP_AUTO_ACT": "1", "OPENRA_AI_STARTUP_ENABLED": "1",
           "OPENRA_AI_STARTUP_MUTED": "1", "OPENRA_AI_GRPC_PORT": str(port)}
    command = ["dotnet", str(binaries / "OpenRA.dll"), f"Engine.EngineDir={resources}",
               f"Engine.SupportDir={profile}", "Game.Mod=ra2", "Game.Platform=Null",
               "Game.FetchNews=false", f"Launch.Map={name}", "Launch.Bots=Multi1:normal"]
    result = {"map": name, "passed": False, "log": str(profile / "game.log")}
    with (profile / "game.log").open("w") as log:
        process = subprocess.Popen(command, cwd=binaries, env=env, stdout=log, stderr=subprocess.STDOUT)
        bridge = OpenRABridge(f"127.0.0.1:{port}", timeout=0.5)
        try:
            deadline = time.monotonic() + 35
            last_error = "No game observation"
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    snapshot = bridge.observe()
                    if snapshot.tick >= ticks:
                        result.update(tick=snapshot.tick, mod=snapshot.mod_id,
                                      buildings=[actor.kind for actor in snapshot.buildings],
                                      state=bridge.state(), names=snapshot.actor_names)
                        if snapshot.mod_id != "ra2" or snapshot.done:
                            raise ValueError("Wrong game or match ended during startup")
                        if not any(actor.kind in {"gacnst", "nacnst"} for actor in snapshot.buildings):
                            raise ValueError("AUTO did not deploy the starting MCV")
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
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    maps = args.maps or sorted(path.parent.name for path in (args.resources / "mods/ra2/maps").glob("*/map.yaml")
                              if "Visibility: Lobby" in path.read_text())
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda name: check_map(args.resources.resolve(), args.binaries.resolve(),
                       args.content.resolve(), args.output.resolve(), name, args.ticks), maps))
    (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    raise SystemExit(0 if results and all(result["passed"] for result in results) else 1)
