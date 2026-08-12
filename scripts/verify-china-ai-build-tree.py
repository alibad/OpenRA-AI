"""Run a live normal-bot build-tree contract for the China faction."""

from __future__ import annotations

import argparse
import json
import shutil
import time
import zipfile
from pathlib import Path

from openra_ai_companion.autonomous import EngineProcess
from openra_ai_companion.bridge import OpenRABridge
from openra_ai_companion.models import GameSnapshot


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "missions" / "china-faction" / "ai-build-contract"
PACKAGE = ROOT / "generated" / "missions" / "china-ai-build-contract.oramap"
EVIDENCE = ROOT / ".artifacts" / "china-faction" / "ai-build-tree"

REQUIRED_BUILDINGS = {
    "fact", "proc", "tent", "weap", "dome", "atek", "fix", "hpad", "syrd",
    "cnbastion", "cnskyshield", "cnspectrum",
}
REQUIRED_UNITS = {
    "cnrifle", "cnportable", "cnnetwork", "redspear", "cnlynx", "cnzbd", "cnqilin", "cnphl",
    "cncloud", "cncrane", "cnskyspear", "cnmantis", "cnluyang", "cnhaiwang",
    "cnhaiying", "cnkunlun", "cnjiaolong",
}


def package_fixture(engine_root: Path) -> None:
    PACKAGE.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PACKAGE, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SOURCE.iterdir()):
            if path.is_file() and path.name != "README.md":
                info = zipfile.ZipInfo(path.name, (2026, 8, 12, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    install = engine_root / "mods" / "ra" / "maps" / PACKAGE.name
    install.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PACKAGE, install)


def wait_for_session(bridge: OpenRABridge) -> GameSnapshot:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            return bridge.fast_advance(1, check_events_every=0, enabled_interrupts=())
        except RuntimeError:
            time.sleep(0.1)
    raise RuntimeError("China AI build-contract session did not start")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9995)
    parser.add_argument("--max-ticks", type=int, default=80000)
    parser.add_argument("--engine-root", type=Path, default=ROOT / "engine" / "openra")
    args = parser.parse_args()
    engine_root = args.engine_root.resolve()
    package_fixture(engine_root)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    engine = EngineProcess(engine_root / "bin" / "OpenRA.exe", engine_root, args.port, EVIDENCE)
    engine.start()
    bridge = OpenRABridge(f"127.0.0.1:{args.port}", timeout=20)
    session_id = ""
    observed_buildings: set[str] = set()
    observed_units: set[str] = set()
    timeline = []
    try:
        session_id = bridge.create_session(PACKAGE.name, "Observer:rl-agent,ChinaAI:normal", 8122026)
        snapshot = wait_for_session(bridge)
        while snapshot.tick < args.max_ticks and not snapshot.done:
            visible = list(snapshot.visible_enemies) + list(snapshot.visible_enemy_buildings)
            observed_buildings.update(item.kind.lower() for item in snapshot.visible_enemy_buildings)
            observed_units.update(item.kind.lower() for item in snapshot.visible_enemies)
            timeline.append({
                "tick": snapshot.tick,
                "buildings": sorted(observed_buildings),
                "units": sorted(observed_units),
                "visible": len(visible),
                "result": snapshot.result,
            })
            if REQUIRED_BUILDINGS <= observed_buildings and REQUIRED_UNITS <= observed_units:
                break
            (EVIDENCE / "ai-build-progress.json").write_text(json.dumps(timeline[-1], indent=2) + "\n", encoding="utf-8")
            try:
                snapshot = bridge.fast_advance(500, check_events_every=0, enabled_interrupts=())
            except RuntimeError:
                time.sleep(2)
                raise

        missing_buildings = sorted(REQUIRED_BUILDINGS - observed_buildings)
        missing_units = sorted(REQUIRED_UNITS - observed_units)
        evidence = {
            "schema": "openra-ai.china-ai-build-tree/v1",
            "seed": 8122026,
            "bot": "normal",
            "tick": snapshot.tick,
            "observed_buildings": sorted(observed_buildings),
            "observed_units": sorted(observed_units),
            "required_buildings": sorted(REQUIRED_BUILDINGS),
            "required_units": sorted(REQUIRED_UNITS),
            "missing_buildings": missing_buildings,
            "missing_units": missing_units,
            "timeline": timeline,
        }
        output = EVIDENCE / "ai-build-tree.json"
        output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        if missing_buildings or missing_units:
            raise RuntimeError(f"AI build tree incomplete at tick {snapshot.tick}: buildings={missing_buildings}, units={missing_units}")
        print(json.dumps({"ok": True, "tick": snapshot.tick, "buildings": len(observed_buildings),
                          "units": len(observed_units), "evidence": str(output.resolve())}))
        return 0
    finally:
        if session_id:
            try:
                bridge.destroy_session(session_id)
            except RuntimeError:
                pass
        bridge.close()
        engine.stop()


if __name__ == "__main__":
    raise SystemExit(main())
