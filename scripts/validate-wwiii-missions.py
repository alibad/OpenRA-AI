"""Load every World War III campaign mission under each built-in experience profile.

Each mission map declares the faction and component rule files it needs so it
stays playable when the player's selected profile does not enable that faction.
This check starts the real headless engine for every mission/profile pair,
creates the mission session for its playable slot, and advances simulation time.
It catches missing component dependencies (for example a faction that inherits
from a component template the map never loads), which only fail at map load.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MISSIONS = (
    "jizan-corridor-2026",
    "hodeidah-lifeline-2026",
    "straits-shield-2026",
    "haitan-network-2026",
    "bab-al-mandab-passage-2026",
)
PROFILES = ("world-war-iii", "ai-assistant-only")


def playable_slot(map_path: Path) -> str:
    text = zipfile.ZipFile(map_path).read("map.yaml").decode("utf-8-sig").replace("\r\n", "\n")
    name = None
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("PlayerReference@"):
            name = None
        elif stripped.startswith("Name: "):
            name = stripped[len("Name: "):]
        elif stripped == "Playable: True" and name:
            return name
    raise RuntimeError(f"{map_path.name} has no playable slot")


def link_content(support: Path, content: Path) -> Path:
    link = support / "Content"
    if link.exists():
        return link
    if os.name == "nt":
        # Directory junctions need no symlink privilege; removing one never touches its target.
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(content)], check=True, capture_output=True)
    else:
        link.symlink_to(content, target_is_directory=True)
    return link


def unlink_content(link: Path) -> None:
    if link.is_symlink() or (os.name == "nt" and link.exists()):
        os.rmdir(link) if os.name == "nt" else link.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=ROOT / "engine" / "openra")
    parser.add_argument("--content", type=Path, required=True, help="Directory containing the owned ra content folder (read-only)")
    parser.add_argument("--output", type=Path, default=ROOT / ".artifacts" / "wwiii-missions")
    parser.add_argument("--ticks", type=int, default=3000)
    parser.add_argument("--port", type=int, default=47310)
    parser.add_argument("--mission", action="append", choices=MISSIONS)
    parser.add_argument("--profile", action="append", choices=PROFILES)
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "services" / "companion" / "src"))
    from openra_ai_companion.autonomous import EngineProcess
    from openra_ai_companion.bridge import OpenRABridge

    engine = args.engine.resolve()
    executable = engine / "bin" / ("OpenRA.exe" if os.name == "nt" else "OpenRA")
    results = []
    port = args.port
    for profile in args.profile or PROFILES:
        for mission in args.mission or MISSIONS:
            map_path = engine / "mods" / "ra" / "maps" / f"{mission}.oramap"
            log_dir = (args.output / profile / mission).resolve()
            support = log_dir / "openra-support"
            support.mkdir(parents=True, exist_ok=True)
            (support / "settings.yaml").write_text(f"Experience@ra:\n\tProfile: {profile}\n", encoding="utf-8")
            link = link_content(support, args.content.resolve())
            process = EngineProcess(executable, engine, port, log_dir)
            record = {"profile": profile, "mission": mission, "passed": False}
            started = time.monotonic()
            try:
                process.start()
                bridge = OpenRABridge(f"127.0.0.1:{port}", timeout=30)
                slot = playable_slot(map_path)
                bridge.create_session(map_path.name, f"{slot}:rl-agent", 20260928)
                snapshot = None
                remaining = args.ticks
                while remaining > 0:
                    step = min(500, remaining)
                    snapshot = bridge.fast_advance(step, check_events_every=0, enabled_interrupts=())
                    remaining -= step
                    if process.process is not None and process.process.poll() is not None:
                        raise RuntimeError(f"engine exited with code {process.process.returncode}")
                record.update(
                    passed=True,
                    slot=slot,
                    tick=snapshot.tick if snapshot is not None else 0,
                    units=len(snapshot.units) if snapshot is not None else 0,
                    buildings=len(snapshot.buildings) if snapshot is not None else 0,
                )
            except Exception as error:  # noqa: BLE001 - every failure is reported per pair
                record["error"] = f"{type(error).__name__}: {error}"
            finally:
                process.stop()
                unlink_content(link)
                record["seconds"] = round(time.monotonic() - started, 1)
                stderr = log_dir / "engine.stderr.log"
                exceptions = [line for line in stderr.read_text(errors="replace").splitlines() if "Exception" in line] if stderr.exists() else []
                crash_logs = sorted(p.name for p in (support / "Logs").glob("exception*")) if (support / "Logs").exists() else []
                if exceptions or crash_logs:
                    record["passed"] = False
                    record["exceptions"] = exceptions[:5] + crash_logs
            results.append(record)
            print(json.dumps(record), flush=True)
            port += 1

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    failed = [r for r in results if not r["passed"]]
    print(f"{len(results) - len(failed)}/{len(results)} mission/profile pairs passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
