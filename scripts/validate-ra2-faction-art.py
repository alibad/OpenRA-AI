#!/usr/bin/env python3
"""Capture real RA2-rendered faction art in a disposable, noncombat review map.

Never uses a telemetry drawing as visual evidence. Does not edit user profiles.
"""
from __future__ import annotations

import argparse
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

UNITS = (("r2qilin", "r2lynx", "r2mantis", "r2cloud"),
         ("r2karrar", "r2raad", "r2fajr", "r2mohajer"),
         ("r2bozkir", "r2yildirim", "r2sancak", "r2kuzgun"))


def fixture(resources: Path, profile: Path, facing: int = 640, color: str = "E04444"):
    manifest = (resources / "mods/ra2/mod.yaml").read_text()
    maps = re.search(r"^\t~\^SupportDir\|(maps/ra2/[^:\n]+): User$", manifest, re.MULTILINE).group(1)
    target = profile / maps / "modern-art-review"
    shutil.copytree(resources / "mods/ra2/maps/blank-shellmap", target)
    actors = "\tReviewBase: gacnst\n\t\tOwner: Multi0\n\t\tLocation: 74,0\n"
    actors += "\tEnemyBase: nacnst\n\t\tOwner: Multi1\n\t\tLocation: 110,0\n"
    actors += "\tSpawn0: mpspawn\n\t\tOwner: Neutral\n\t\tLocation: 74,0\n\tSpawn1: mpspawn\n\t\tOwner: Neutral\n\t\tLocation: 110,0\n"
    for i, unit in enumerate(("mtnk", "htnk", "fv", "e1")):
        actors += f"\tReference{i}: {unit}\n\t\tOwner: Multi0\n\t\tLocation: {59+3*i},{-6-3*i}\n\t\tFacing: {facing}\n"
    for row, units in enumerate(UNITS):
        for col, unit in enumerate(units):
            # Rows/columns aligned to the isometric screen axes, not map x/y.
            x, y = 62 + 3*row + 3*col, -3 + 3*row - 3*col
            actors += f"\t{unit}: {unit}\n\t\tOwner: Multi0\n\t\tLocation: {x},{y}\n\t\tFacing: {facing}\n"
    text = (target / "map.yaml").read_text().split("Players:\n", 1)[0]
    text = text.replace("Title: Blank", "Title: Modern Faction Art Review").replace("Visibility: Shellmap", "Visibility: Lobby")
    text += "Players:\n\tPlayerReference@Neutral:\n\t\tName: Neutral\n\t\tOwnsWorld: True\n\t\tNonCombatant: True\n\t\tFaction: america\n"
    for i, country in enumerate(("china", "iran")):
        text += f"\tPlayerReference@Multi{i}:\n\t\tName: Multi{i}\n\t\tPlayable: True\n\t\tFaction: {country}\n\t\tLockFaction: True\n\t\tColor: {color if i == 0 else '4477EE'}\n\t\tLockColor: True\n"
    text += "Actors:\n" + actors
    text += "Rules:\n\tWorld:\n\t\t-SpawnStartingUnits:\n\t\tLuaScript:\n\t\t\tScripts: review.lua\n\tPlayer:\n\t\tShroud:\n\t\t\tFogEnabled: false\n\t\t\tExploredMapEnabled: true\n"
    (target / "map.yaml").write_text(text)
    (target / "review.lua").write_text("WorldLoaded = function()\n  Camera.Position = r2fajr.CenterPosition\nend\n")
    return target


def run(resources: Path, binaries: Path, content: Path, output: Path, facing=640, color="E04444"):
    output.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix="art-", dir=output))
    (profile / "Content").symlink_to(content, target_is_directory=True)
    fixture(resources, profile, facing, color)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {**os.environ, "OPENRA_AI_COMPANION": "1", "OPENRA_AI_COMPANION_READY": "1",
           "OPENRA_AI_STARTUP_ENABLED": "1", "OPENRA_AI_STARTUP_AUTO_ACT": "0", "OPENRA_AI_STARTUP_MUTED": "1",
           "OPENRA_AI_GRPC_PORT": str(port)}
    command = ["dotnet", str(binaries / "OpenRA.dll"), f"Engine.EngineDir={resources}",
               f"Engine.SupportDir={profile}", "Game.Mod=ra2", "Game.FetchNews=false",
               "Graphics.Mode=Windowed", "Graphics.WindowedSize=1440,900", "Graphics.ViewportDistance=Close", "Launch.Map=modern-art-review"]
    with (profile / "game.log").open("w") as log:
        process = subprocess.Popen(command, cwd=binaries, env=env, stdout=log, stderr=subprocess.STDOUT)
        bridge = OpenRABridge(f"127.0.0.1:{port}", timeout=5)
        try:
            deadline = time.monotonic() + 80
            last_error = "No frame"
            while process.poll() is None and time.monotonic() < deadline:
                try:
                    snapshot = bridge.observe()
                    if snapshot.tick < 20:
                        time.sleep(0.2)
                        continue
                    frame = bridge.capture_frame()
                    if frame.scope != "rendered-player-viewport-fog-respecting":
                        raise ValueError("Expected actual rendered game pixels")
                    (output / "native-ra2-review.png").write_bytes(frame.png)
                    report = {"tick": snapshot.tick, "scope": frame.scope, "facing": facing, "color": color, "units": [u.kind for u in snapshot.units],
                              "width": frame.width, "height": frame.height, "profile": str(profile)}
                    (output / "capture.json").write_text(json.dumps(report, indent=2) + "\n")
                    print(json.dumps(report), flush=True)
                    return
                except RuntimeError as error:
                    last_error = str(error)
                    time.sleep(0.3)
            raise RuntimeError(f"Art capture failed: {last_error}. See {profile / 'game.log'}")
        finally:
            bridge.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("resources", "binaries", "content", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--facings", nargs="+", type=int, default=[640])
    parser.add_argument("--color", default="E04444")
    args = parser.parse_args()
    if not re.fullmatch("[0-9A-Fa-f]{6}", args.color) or any(not 0 <= f < 1024 for f in args.facings):
        parser.error("Expected an RGB hex color and facings in 0..1023")
    for facing in args.facings:
        output = args.output if len(args.facings) == 1 else args.output / str(facing)
        run(*(getattr(args, key).resolve() for key in ("resources", "binaries", "content")), output.resolve(), facing, args.color)
