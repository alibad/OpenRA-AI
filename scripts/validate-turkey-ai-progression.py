"""Delegate a Turkey skirmish player to a native bot and record progression."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from openra_ai_companion.bridge import OpenRABridge


TURKEY_COMBAT = {
    "trrifle", "trat", "trdroneop", "greywolf", "bozkir", "aras8",
    "yildirim", "gokkalkan", "sancak", "denizkaplan", "kuzgunm",
    "turnaah", "sahinx", "marmara", "ege", "poyraz",
}


def kind(value: str) -> str:
    return value.lower().split(".", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", default="127.0.0.1:18082")
    parser.add_argument("--personality", default="normal")
    parser.add_argument("--duration", type=float, default=150.0)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument(
        "--output", type=Path,
        default=Path("artifacts/turkey-faction/ai-progression-telemetry.json"),
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output = (root / args.output).resolve() if not args.output.is_absolute() else args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.duration
    samples: list[dict[str, object]] = []

    with OpenRABridge(args.bridge, timeout=5.0) as bridge:
        snapshot = bridge.observe()
        state = bridge.state()
        delegated = bridge.update_companion_status(
            f"auto-active:{args.personality}",
            f"TURKEY AI VALIDATION - {args.personality.upper()}",
        )
        while time.monotonic() < deadline:
            snapshot = bridge.observe()
            buildings = sorted(kind(actor.kind) for actor in snapshot.buildings)
            units = sorted(kind(actor.kind) for actor in snapshot.units)
            custom_units = sorted(actor for actor in units if actor in TURKEY_COMBAT)
            production = sorted(
                {
                    item
                    for actor in (*snapshot.units, *snapshot.buildings)
                    for item in actor.can_produce
                }
            )
            sample = {
                "wall_seconds": round(args.duration - max(0, deadline - time.monotonic()), 1),
                "tick": snapshot.tick,
                "cash": snapshot.cash,
                "power": [snapshot.power_provided, snapshot.power_drained],
                "buildings": buildings,
                "units": units,
                "custom_units": custom_units,
                "available_production": production,
            }
            samples.append(sample)

            economy = "proc" in buildings and ("harv" in units or snapshot.harvester_count > 0)
            construction = "fact" in buildings and "powr" in buildings
            production_ready = any(actor in buildings for actor in ("tent", "weap", "hpad", "syrd"))
            if construction and economy and production_ready and custom_units:
                break
            time.sleep(args.interval)

        frame = bridge.capture_frame()
        screenshot = output.with_name("turkey-ai-progression.png")
        screenshot.write_bytes(frame.png)
        bridge.update_companion_status(
            f"ready:{args.personality}", "TURKEY AI VALIDATION COMPLETE"
        )

    final = samples[-1]
    buildings = set(final["buildings"])
    units = set(final["units"])
    checks = {
        "turkey_faction": str(state.get("player_faction", "")).lower() == "turkey",
        "delegation_accepted": delegated,
        "ticks_advanced": len(samples) > 1 and samples[-1]["tick"] > samples[0]["tick"],
        "construction": "fact" in buildings and "powr" in buildings,
        "economy": "proc" in buildings and ("harv" in units or any(s["custom_units"] for s in samples)),
        "production_structure": any(actor in buildings for actor in ("tent", "weap", "hpad", "syrd")),
        "turkey_unit_produced": bool(final["custom_units"]),
    }
    telemetry = {
        "schema": "openra-ai.turkey-ai-progression/v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "map": snapshot.map_name,
        "personality": args.personality,
        "state": state,
        "samples": samples,
        "checks": checks,
        "screenshot": {"path": str(screenshot), **frame.metadata()},
        "passed": all(checks.values()),
    }
    output.write_text(json.dumps(telemetry, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(telemetry, indent=2))
    return 0 if telemetry["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
