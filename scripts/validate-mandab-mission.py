#!/usr/bin/env python3
"""Run Bab al-Mandab victory and objective-failure paths in the real engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path


CASES = (
    "headless-victory",
    "fail-readiness",
    "fail-recon",
    "fail-threats",
    "fail-shipping",
    "fail-passage",
)
FIXED_ZIP_TIME = (2026, 8, 11, 0, 0, 0)


def deterministic_variant(source: Path, destination: Path, case: str) -> str:
    with zipfile.ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}

    script_name = "bab-al-mandab-passage.lua"
    script = files[script_name].decode("utf-8")
    marker = 'MANDAB_TEST_PATH = "live"'
    if script.count(marker) != 1:
        raise RuntimeError(f"expected one validation marker in {script_name}")
    files[script_name] = script.replace(marker, f'MANDAB_TEST_PATH = "{case}"').encode("utf-8")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def support_maps_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is required for the Windows OpenRA map cache")
    return Path(appdata) / "OpenRA" / "maps" / "ra" / "{DEV_VERSION}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path("generated/missions/bab-al-mandab-passage-2026.oramap"))
    parser.add_argument("--evidence-root", type=Path, default=Path("artifacts/mandab-engine-validation"))
    parser.add_argument("--port", type=int, default=9994)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    package = (root / args.package).resolve() if not args.package.is_absolute() else args.package.resolve()
    evidence = (root / args.evidence_root).resolve() if not args.evidence_root.is_absolute() else args.evidence_root.resolve()
    if not package.is_file():
        raise FileNotFoundError(f"build the mission package first: {package}")

    sys.path.insert(0, str(root / "services" / "companion" / "src"))
    from openra_ai_companion.autonomous import EngineProcess
    from openra_ai_companion.bridge import OpenRABridge
    from openra_ai_companion.models import ActionCommand

    variants_dir = evidence / "packages"
    maps_dir = support_maps_dir()
    maps_dir.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    package_hashes: dict[str, str] = {}
    for case in CASES:
        name = f"bab-al-mandab-passage-2026-{case}.oramap"
        variant = variants_dir / name
        package_hashes[case] = deterministic_variant(package, variant, case)
        target = maps_dir / name
        shutil.copyfile(variant, target)
        installed.append(target)

    production_name = "bab-al-mandab-passage-2026-production.oramap"
    production_target = maps_dir / production_name
    shutil.copyfile(package, production_target)
    installed.append(production_target)

    engine = EngineProcess(root / "engine" / "openra" / "bin" / "OpenRA.exe", root / "engine" / "openra", args.port, evidence / "engine")
    results: list[dict[str, object]] = []
    try:
        engine.start()
        bridge = OpenRABridge(f"127.0.0.1:{args.port}", timeout=20)

        # Exercise the distributable (unpatched) economy and objective gate with
        # synchronized player orders: construction, placement, production,
        # harvesting presence, and three real mobile reconnaissance actors.
        session = bridge.create_session(production_name, "Saudi Arabia:rl-agent", 20260811)
        snapshot = bridge.fast_advance(1, check_events_every=0, enabled_interrupts=())
        initial_cash = snapshot.cash
        initial_harvesters = snapshot.harvester_count

        def actor_kinds(actors: object) -> list[str]:
            return [actor.kind.lower().split(".", 1)[0] for actor in actors]  # type: ignore[attr-defined]

        for item, (x, y) in (("dome", (68, 84)), ("atek", (68, 78))):
            if item not in snapshot.available_production:
                raise RuntimeError(f"{item} was not available at its required tech stage")
            snapshot = bridge.fast_advance(1, (ActionCommand("build", item_type=item),), check_events_every=0, enabled_interrupts=())
            for _ in range(20):
                snapshot = bridge.fast_advance(100, check_events_every=0, enabled_interrupts=())
                if any(entry.get("item") == item and float(entry.get("progress", 0)) >= 0.99 for entry in snapshot.production):
                    break
            snapshot = bridge.fast_advance(
                1,
                (ActionCommand("place_building", item_type=item, target_x=x, target_y=y),),
                check_events_every=0,
                enabled_interrupts=(),
            )
            snapshot = bridge.fast_advance(25, check_events_every=0, enabled_interrupts=())
            if item not in actor_kinds(snapshot.buildings):
                raise RuntimeError(f"engine did not place {item} at the validated base cell")

        snapshot = bridge.fast_advance(1, (ActionCommand("train", item_type="m1a2s"),), check_events_every=0, enabled_interrupts=())
        for _ in range(20):
            snapshot = bridge.fast_advance(100, check_events_every=0, enabled_interrupts=())
            if actor_kinds(snapshot.units).count("m1a2s") >= 2:
                break

        scouts = [unit for unit in snapshot.units if unit.kind.lower().split(".", 1)[0] in {"e1", "m1a2s"}][:3]
        recon_targets = ((70, 20), (70, 43), (70, 63))
        snapshot = bridge.fast_advance(
            1,
            tuple(ActionCommand("move", actor_id=unit.actor_id, target_x=x, target_y=y) for unit, (x, y) in zip(scouts, recon_targets)),
            check_events_every=0,
            enabled_interrupts=(),
        )
        for _ in range(35):
            snapshot = bridge.fast_advance(100, check_events_every=0, enabled_interrupts=())
            if len(snapshot.objectives) > 1 and snapshot.objectives[1].state == "completed":
                break

        production_passed = (
            initial_harvesters >= 1
            and snapshot.resource_capacity > 0
            and {"dome", "atek"}.issubset(actor_kinds(snapshot.buildings))
            and actor_kinds(snapshot.units).count("m1a2s") >= 2
            and len(snapshot.objectives) > 1
            and snapshot.objectives[0].state == "completed"
            and snapshot.objectives[1].state == "completed"
        )
        results.append({
            "case": "production-and-recon",
            "passed": production_passed,
            "expected": "Radar Dome, Tech Center, M1A2S, harvesting, and three recon sectors",
            "actual": "complete" if production_passed else "incomplete",
            "tick": snapshot.tick,
            "initial_cash": initial_cash,
            "final_cash": snapshot.cash,
            "harvesters": snapshot.harvester_count,
            "resource_capacity": snapshot.resource_capacity,
            "buildings": actor_kinds(snapshot.buildings),
            "units": actor_kinds(snapshot.units),
            "final_objectives": [objective.as_dict() for objective in snapshot.objectives],
            "package_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        })
        bridge.destroy_session(session)

        for case in CASES:
            request = f"bab-al-mandab-passage-2026-{case}.oramap"
            session = bridge.create_session(request, "Saudi Arabia:rl-agent", 20260811)
            started = time.monotonic()
            snapshot = bridge.fast_advance(1, check_events_every=0, enabled_interrupts=())
            initial = [objective.as_dict() for objective in snapshot.objectives]
            while not snapshot.done and snapshot.tick < 8_000:
                snapshot = bridge.fast_advance(100, check_events_every=25, enabled_interrupts=())

            expected = "win" if case == "headless-victory" else "lose"
            actual = snapshot.result.lower()
            passed = snapshot.mission_mode and actual == expected
            results.append({
                "case": case,
                "passed": passed,
                "expected": expected,
                "actual": actual,
                "tick": snapshot.tick,
                "wall_seconds": round(time.monotonic() - started, 3),
                "initial_objectives": initial,
                "final_objectives": [objective.as_dict() for objective in snapshot.objectives],
                "package_sha256": package_hashes[case],
            })
            bridge.destroy_session(session)
    finally:
        engine.stop()
        for path in installed:
            path.unlink(missing_ok=True)

    evidence.mkdir(parents=True, exist_ok=True)
    report = {
        "mission": "bab-al-mandab-passage-2026",
        "engine": "real OpenRA multi-session headless engine",
        "cases": results,
        "passed": all(result["passed"] for result in results),
    }
    (evidence / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for result in results:
        print(f"{result['case']}: {result['actual']} at tick {result['tick']} ({'PASS' if result['passed'] else 'FAIL'})")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
