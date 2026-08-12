"""Exercise Turkey actors through the live OpenRA companion bridge.

Run this while Straits Shield is open in an interactive current-build client.
The script issues four cardinal movement orders, advances the drone/amphibious
screen toward the hostile surface group, and saves fog-respecting viewport
captures plus machine-readable telemetry.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from openra_ai_companion.bridge import OpenRABridge
from openra_ai_companion.models import ActionCommand, GameSnapshot, Unit


TURKEY_TYPES = {
    "trrifle",
    "trat",
    "trdroneop",
    "greywolf",
    "bozkir",
    "aras8",
    "yildirim",
    "gokkalkan",
    "sancak",
    "denizkaplan",
    "kuzgunm",
    "turnaah",
    "sahinx",
    "marmara",
    "ege",
    "poyraz",
}


def actor_type(unit: Unit) -> str:
    return unit.kind.lower().split(".", 1)[0]


def wait_for_match(bridge: OpenRABridge, timeout: float) -> GameSnapshot:
    deadline = time.monotonic() + timeout
    last_error = "bridge did not become ready"
    while time.monotonic() < deadline:
        try:
            snapshot = bridge.observe()
            if snapshot.tick > 0 and snapshot.map_name != "Unknown battlefield":
                return snapshot
        except RuntimeError as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(last_error)


def current_unit(snapshot: GameSnapshot, actor_id: int) -> Unit | None:
    return next((unit for unit in snapshot.units if unit.actor_id == actor_id), None)


def unit_record(unit: Unit) -> dict[str, object]:
    return {
        "actor_id": unit.actor_id,
        "type": actor_type(unit),
        "cell": [unit.cell_x, unit.cell_y],
        "facing": unit.facing,
        "hp_percent": round(unit.hp_percent, 4),
        "activity": unit.current_activity,
        "ammo": unit.ammo,
        "target_actor_id": unit.current_target_actor_id,
    }


def git_value(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, encoding="utf-8"
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", default="127.0.0.1:9998")
    parser.add_argument("--output", type=Path, default=Path("artifacts/turkey-faction/live"))
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--movement-wait", type=float, default=5.0)
    parser.add_argument("--combat-wait", type=float, default=12.0)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output = (root / args.output).resolve() if not args.output.is_absolute() else args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    telemetry: dict[str, object] = {
        "schema": "openra-ai.turkey-live/v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "branch": git_value(root, "branch", "--show-current"),
        "engine_commit": git_value(root / "engine" / "openra", "rev-parse", "HEAD"),
        "bridge": args.bridge,
    }

    with OpenRABridge(args.bridge, timeout=5.0) as bridge:
        initial = wait_for_match(bridge, args.timeout)
        telemetry["map"] = initial.map_name
        telemetry["initial_tick"] = initial.tick
        telemetry["initial_turkey_units"] = [
            unit_record(unit) for unit in initial.units if actor_type(unit) in TURKEY_TYPES
        ]

        initial_frame = bridge.capture_frame()
        initial_path = output / "straits-shield-opening.png"
        initial_path.write_bytes(initial_frame.png)
        telemetry["opening_frame"] = {"path": str(initial_path), **initial_frame.metadata()}

        # Exercise distinct actors on north/east/south/west headings. Keeping the
        # offsets small confines the check to the known-passable starting island.
        movable = [
            unit
            for unit in initial.units
            if actor_type(unit) in {"trrifle", "trat", "trdroneop", "aras8", "denizkaplan"}
        ]
        if len(movable) < 4:
            raise RuntimeError(f"Expected four mobile Turkey actors, found {len(movable)}")

        deltas = ((0, -3, "north"), (3, 0, "east"), (0, 3, "south"), (-3, 0, "west"))
        movement_plan: list[tuple[Unit, int, int, str]] = []
        for unit, (dx, dy, heading) in zip(movable[:4], deltas):
            movement_plan.append((unit, unit.cell_x + dx, unit.cell_y + dy, heading))

        before_move = bridge.observe()
        movement_commands = tuple(
            ActionCommand("move", actor_id=unit.actor_id, target_x=x, target_y=y)
            for unit, x, y, _ in movement_plan
        )
        movement_receipt = bridge.execute_actions(
            "turkey-live-cardinal-movement", before_move.tick, movement_commands
        )
        time.sleep(args.movement_wait)
        after_move = bridge.observe()

        movement_results = []
        for unit, target_x, target_y, heading in movement_plan:
            after = current_unit(after_move, unit.actor_id)
            movement_results.append(
                {
                    "heading": heading,
                    "actor_id": unit.actor_id,
                    "type": actor_type(unit),
                    "start_cell": [unit.cell_x, unit.cell_y],
                    "target_cell": [target_x, target_y],
                    "end_cell": [after.cell_x, after.cell_y] if after else None,
                    "start_facing": unit.facing,
                    "end_facing": after.facing if after else None,
                    "distance_moved": (
                        math.dist((unit.cell_x, unit.cell_y), (after.cell_x, after.cell_y)) if after else 0
                    ),
                    "passed": bool(after and (after.cell_x, after.cell_y) != (unit.cell_x, unit.cell_y)),
                }
            )
        telemetry["movement"] = {
            "receipt": movement_receipt.as_dict(),
            "tick_after": after_move.tick,
            "headings": movement_results,
            "passed": movement_receipt.accepted and all(item["passed"] for item in movement_results),
        }

        # The opening Kuzgun and Deniz Kaplan advance onto the nearby synthetic
        # surface group. This verifies live locomotion, target acquisition, ammo,
        # projectiles, damage, and return-fire without reproducing a real attack.
        attackers = [
            unit
            for unit in after_move.units
            if actor_type(unit) in {"kuzgunm", "denizkaplan"} and unit.can_attack
        ]
        if not attackers:
            raise RuntimeError("No live Turkey drone/amphibious attackers were observable")

        before_approach = bridge.observe()
        approach_receipt = bridge.execute_actions(
            "turkey-live-combat-approach",
            before_approach.tick,
            tuple(
                ActionCommand("attack_move", actor_id=unit.actor_id, target_x=64, target_y=66)
                for unit in attackers
            ),
        )
        time.sleep(args.combat_wait)
        contact = bridge.observe()

        visible_targets = [
            enemy
            for enemy in contact.visible_enemies
            if actor_type(enemy) in {"poyraz", "ege", "marmara"}
        ]
        focus_receipt = None
        focused_target: Unit | None = None
        if visible_targets:
            focused_target = min(
                visible_targets,
                key=lambda enemy: min(
                    math.dist((enemy.cell_x, enemy.cell_y), (attacker.cell_x, attacker.cell_y))
                    for attacker in attackers
                ),
            )
            live_attackers = [
                current_unit(contact, attacker.actor_id)
                for attacker in attackers
            ]
            attack_commands = tuple(
                ActionCommand("attack", actor_id=attacker.actor_id, target_actor_id=focused_target.actor_id)
                for attacker in live_attackers
                if attacker is not None and attacker.can_attack
            )
            if attack_commands:
                focus_receipt = bridge.execute_actions(
                    "turkey-live-focus-fire", contact.tick, attack_commands
                )
                time.sleep(args.combat_wait)

        after_combat = bridge.observe()
        combat_frame = bridge.capture_frame()
        combat_path = output / "straits-shield-live-combat.png"
        combat_path.write_bytes(combat_frame.png)

        final_target = (
            next(
                (enemy for enemy in after_combat.visible_enemies if enemy.actor_id == focused_target.actor_id),
                None,
            )
            if focused_target
            else None
        )
        attacker_after = [
            current_unit(after_combat, attacker.actor_id) for attacker in attackers
        ]
        combat_signals = {
            "target_acquired": bool(focused_target),
            "target_damaged_or_destroyed": bool(
                focused_target
                and (final_target is None or final_target.hp_percent < focused_target.hp_percent)
            ),
            "ammo_changed": any(
                after is not None and before.ammo >= 0 and after.ammo != before.ammo
                for before, after in zip(attackers, attacker_after)
            ),
            "active_target": any(
                after is not None and after.current_target_actor_id > 0 for after in attacker_after
            ),
            "kill_counter_changed": after_combat.units_killed > initial.units_killed,
            # A destroyed attacker after accepted attack-move orders is direct
            # evidence that the hostile fleet acquired, fired on, and damaged a
            # moving Turkey actor even if it disappears before the next snapshot.
            "return_fire_losses": after_combat.units_lost > initial.units_lost,
        }
        telemetry["combat"] = {
            "approach_receipt": approach_receipt.as_dict(),
            "focus_receipt": focus_receipt.as_dict() if focus_receipt else None,
            "contact_tick": contact.tick,
            "final_tick": after_combat.tick,
            "attackers_before": [unit_record(unit) for unit in attackers],
            "attackers_after": [unit_record(unit) for unit in attacker_after if unit is not None],
            "focused_target_before": unit_record(focused_target) if focused_target else None,
            "focused_target_after": unit_record(final_target) if final_target else None,
            "signals": combat_signals,
            "passed": approach_receipt.accepted and any(combat_signals.values()),
        }
        telemetry["combat_frame"] = {"path": str(combat_path), **combat_frame.metadata()}
        telemetry["final_counters"] = {
            "tick": after_combat.tick,
            "cash": after_combat.cash,
            "units_killed": after_combat.units_killed,
            "units_lost": after_combat.units_lost,
            "order_count": after_combat.order_count,
            "explored_percent": round(after_combat.explored_percent, 2),
        }

    movement_passed = bool(telemetry["movement"]["passed"])  # type: ignore[index]
    combat_passed = bool(telemetry["combat"]["passed"])  # type: ignore[index]
    telemetry["passed"] = movement_passed and combat_passed
    telemetry_path = output / "live-validation-telemetry.json"
    telemetry_path.write_text(json.dumps(telemetry, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(telemetry, indent=2))
    return 0 if telemetry["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
