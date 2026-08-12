"""Run every standard bot personality against the Iran build contract."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "companion" / "src"))

from openra_ai_companion.bridge import OpenRABridge  # noqa: E402
from openra_ai_companion.models import ActionCommand, GameSnapshot  # noqa: E402


PERSONALITIES = ("beginner", "easy", "medium", "rush", "normal", "turtle", "naval")
CUSTOM_UNITS = {
    "irbas",
    "iratgm",
    "irdc",
    "shadowone",
    "irkarr",
    "irraad",
    "irfajr",
    "ircoast",
    "irazar",
    "irtoufan",
    "irmohajer",
    "irloiter",
    "irpey",
    "irghadir",
}
DOMAINS = {
    "infantry": {
        "e1", "e2", "e3", "e4", "e7", "dog", "shok",
        "irbas", "iratgm", "irdc", "shadowone",
    },
    "vehicle": {
        "apc", "jeep", "arty", "v2rl", "ftrk", "1tnk", "2tnk", "3tnk", "4tnk", "ttnk", "stnk",
        "irkarr", "irraad", "irfajr", "ircoast",
    },
    "air": {
        "mig", "yak", "heli", "hind", "mh60",
        "irazar", "irtoufan", "irmohajer", "irloiter",
    },
    "naval": {
        "ss", "msub", "dd", "ca", "lst", "pt",
        "irpey", "irghadir",
    },
}
DESTROYED_CUSTOM_EVIDENCE = {
    "irkarr.husk": "irkarr",
    "irraad.husk": "irraad",
    "irfajr.husk": "irfajr",
    "ircoast.husk": "ircoast",
    "irazar.husk": "irazar",
    "irtoufan.husk": "irtoufan",
    "irmohajer.husk": "irmohajer",
    "irpey.sink": "irpey",
    "irghadir.sink": "irghadir",
}
CORE_BUILDINGS = {
    "powr", "apwr", "proc", "barr", "tent", "weap", "afld", "irhpad",
    "dome", "stek", "fix", "spen",
}


def scout_commands(snapshot: GameSnapshot) -> tuple[ActionCommand, ...]:
    commands = []
    for unit in snapshot.units:
        if unit.kind in {"irmohajer", "irazar", "irtoufan", "irloiter"}:
            commands.append(
                ActionCommand("move", unit.actor_id, target_x=66, target_y=38)
            )
    return tuple(commands)


def run_personality(
    bridge: OpenRABridge,
    personality: str,
    ticks: int,
) -> dict[str, object]:
    session_id = bridge.create_session(
        "iran-doctrine-range.oramap",
        f"Multi0:rl-agent,Multi1:{personality}",
        seed=8122026,
    )
    seen_units: set[str] = set()
    seen_buildings: set[str] = set()
    seen_base_buildings: set[str] = set()
    timeline: list[dict[str, object]] = []
    try:
        snapshot = bridge.fast_advance(
            1, check_events_every=0, enabled_interrupts=()
        )
        commands = scout_commands(snapshot)
        while snapshot.tick < ticks and not snapshot.done:
            step = min(500, ticks - snapshot.tick)
            snapshot = bridge.fast_advance(
                step,
                commands,
                check_events_every=0,
                enabled_interrupts=(),
            )
            commands = ()
            visible_units = {unit.kind for unit in snapshot.visible_enemies}
            visible_buildings = {
                unit.kind for unit in snapshot.visible_enemy_buildings
            }
            remembered = {
                unit.kind for unit in snapshot.remembered_enemy_buildings
            }
            seen_units.update(visible_units)
            seen_buildings.update(visible_buildings | remembered)
            seen_base_buildings.update(
                unit.kind
                for unit in (*snapshot.visible_enemy_buildings, *snapshot.remembered_enemy_buildings)
                if unit.cell_y < 65 and unit.kind in CORE_BUILDINGS
            )
            if snapshot.tick % 2000 < 500 or snapshot.done:
                timeline.append(
                    {
                        "tick": snapshot.tick,
                        "visible_units": sorted(visible_units),
                        "visible_buildings": sorted(visible_buildings),
                        "remembered_buildings": sorted(remembered),
                        "own_units_remaining": len(snapshot.units),
                        "done": snapshot.done,
                        "result": snapshot.result,
                    }
                )
            # Reissue scout routes if aircraft were repelled but survived.
            if snapshot.tick % 2000 < 500:
                commands = scout_commands(snapshot)

        normalized_units = set(seen_units)
        normalized_units.update(
            DESTROYED_CUSTOM_EVIDENCE[kind]
            for kind in seen_units
            if kind in DESTROYED_CUSTOM_EVIDENCE
        )
        produced = sorted(normalized_units & CUSTOM_UNITS)
        custom_domains = sorted(
            domain
            for domain, kinds in DOMAINS.items()
            if kinds & set(produced)
        )
        force_domains = sorted(
            domain
            for domain, kinds in DOMAINS.items()
            if kinds & normalized_units
        )
        # A faction-specific production event plus two live force domains is a
        # concrete mixed-force run. Static tests separately verify that every
        # personality configures all four Iran-specific domains.
        passed = (
            len(produced) >= 1
            and len(force_domains) >= 2
            and len(seen_base_buildings) >= 3
        )
        return {
            "personality": personality,
            "session_id": session_id,
            "end_tick": snapshot.tick,
            "done": snapshot.done,
            "result": snapshot.result,
            "custom_units_seen": produced,
            "custom_domains_seen": custom_domains,
            "force_domains_seen": force_domains,
            "all_enemy_units_seen": sorted(seen_units),
            "base_buildings_seen": sorted(seen_base_buildings),
            "all_buildings_seen": sorted(seen_buildings),
            "timeline": timeline,
            "passed": passed,
        }
    finally:
        bridge.destroy_session(session_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="127.0.0.1:10019")
    parser.add_argument("--ticks", type=int, default=12000)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs" / "iran-faction-evidence" / "ai-validation.json",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, object] = {
        "schema": "openra-ai.iran-ai-validation/v1",
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "map": "Iran Doctrine Range",
        "ticks_per_personality": args.ticks,
        "personalities": [],
    }
    with OpenRABridge(args.bridge, timeout=10.0) as bridge:
        results = [
            run_personality(bridge, personality, args.ticks)
            for personality in PERSONALITIES
        ]
    failed = [result["personality"] for result in results if not result["passed"]]
    report["personalities"] = results
    report["summary"] = {
        "passed": len(results) - len(failed),
        "total": len(results),
        "failed": failed,
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"Telemetry: {args.output.resolve()}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
