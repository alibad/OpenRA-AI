"""Exercise the installed Iran faction through the rendered OpenRA bridge.

Run this against a fresh Iran Doctrine Range match started with
OPENRA_AI_COMPANION=1 and Launch.Bots=Multi1:dummy.  The dummy observer keeps
the deterministic doctrine-range match alive while the script intentionally
records renderer captures and live actor state instead of treating static YAML
checks as gameplay proof.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "companion" / "src"))

from openra_ai_companion.bridge import OpenRABridge  # noqa: E402
from openra_ai_companion.models import ActionCommand, GameSnapshot, Unit  # noqa: E402


EXPECTED_ROSTER = {
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


def wait_until(
    bridge: OpenRABridge,
    predicate: Callable[[GameSnapshot], bool],
    *,
    timeout: float,
    interval: float = 0.12,
) -> GameSnapshot:
    deadline = time.monotonic() + timeout
    last = bridge.observe()
    while time.monotonic() < deadline:
        last = bridge.observe()
        if predicate(last):
            return last
        time.sleep(interval)
    raise RuntimeError(f"Live condition did not resolve by tick {last.tick}")


def own(snapshot: GameSnapshot, kind: str) -> Unit:
    return next(unit for unit in snapshot.units if unit.kind == kind)


def enemy(snapshot: GameSnapshot, kind: str) -> Unit:
    return next(
        unit
        for unit in (*snapshot.visible_enemies, *snapshot.visible_enemy_buildings)
        if unit.kind == kind
    )


def issue(bridge: OpenRABridge, name: str, *commands: ActionCommand) -> dict[str, object]:
    snapshot = bridge.observe()
    receipt = bridge.execute_actions(name, snapshot.tick, tuple(commands))
    if not receipt.accepted or not all(result.get("accepted", False) for result in receipt.results):
        raise RuntimeError(f"OpenRA rejected {name}: {receipt.as_dict()}")
    return receipt.as_dict()


def move_trace(
    bridge: OpenRABridge,
    kind: str,
    destinations: list[tuple[int, int]],
    *,
    tolerance: int,
    timeout_per_leg: float,
) -> dict[str, object]:
    samples: list[dict[str, object]] = []
    receipts: list[dict[str, object]] = []
    for leg, (target_x, target_y) in enumerate(destinations):
        unit = own(bridge.observe(), kind)
        receipts.append(
            issue(
                bridge,
                f"{kind}-heading-{leg}",
                ActionCommand("move", unit.actor_id, target_x=target_x, target_y=target_y),
            )
        )
        deadline = time.monotonic() + timeout_per_leg
        while time.monotonic() < deadline:
            snapshot = bridge.observe()
            unit = own(snapshot, kind)
            sample = {
                "tick": snapshot.tick,
                "cell": [unit.cell_x, unit.cell_y],
                "facing": unit.facing,
                "activity": unit.current_activity,
                "target": [target_x, target_y],
            }
            if not samples or sample != samples[-1]:
                samples.append(sample)
            if max(abs(unit.cell_x - target_x), abs(unit.cell_y - target_y)) <= tolerance:
                break
            time.sleep(0.12)
        else:
            raise RuntimeError(f"{kind} did not reach heading target {(target_x, target_y)}")

    facings = sorted({int(sample["facing"]) for sample in samples})
    if len(facings) < 3:
        raise RuntimeError(f"{kind} exposed only {len(facings)} live facings: {facings}")
    return {
        "kind": kind,
        "destinations": [list(cell) for cell in destinations],
        "distinct_facings": facings,
        "samples": samples,
        "receipts": receipts,
    }


def target_hp(snapshot: GameSnapshot, kind: str) -> float:
    return enemy(snapshot, kind).hp_percent


def first_damage(
    bridge: OpenRABridge,
    attacker_kind: str,
    target_kind: str,
    *,
    timeout: float,
) -> tuple[GameSnapshot, float, dict[str, object]]:
    snapshot = bridge.observe()
    attacker = own(snapshot, attacker_kind)
    target = enemy(snapshot, target_kind)
    before = target.hp_percent
    receipt = issue(
        bridge,
        f"{attacker_kind}-attack-{target_kind}",
        ActionCommand("attack", attacker.actor_id, target_actor_id=target.actor_id),
    )
    damaged = wait_until(
        bridge,
        lambda state: target_hp(state, target_kind) < before,
        timeout=timeout,
        interval=0.08,
    )
    issue(
        bridge,
        f"{attacker_kind}-stop-after-hit",
        ActionCommand("stop", own(damaged, attacker_kind).actor_id),
    )
    return damaged, before, receipt


def capture(
    bridge: OpenRABridge,
    output: Path,
    name: str,
    captures: list[dict[str, object]],
) -> None:
    frame = bridge.capture_frame()
    path = output / name
    path.write_bytes(frame.png)
    captures.append(
        {
            "file": path.name,
            "tick": frame.tick,
            "width": frame.width,
            "height": frame.height,
            "scope": frame.scope,
            "sha256": hashlib.sha256(frame.png).hexdigest(),
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="127.0.0.1:10018")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs" / "iran-faction-evidence",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    telemetry: dict[str, object] = {
        "schema": "openra-ai.iran-live-validation/v1",
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "bridge": args.bridge,
        "checks": {},
    }
    captures: list[dict[str, object]] = []

    with OpenRABridge(args.bridge, timeout=5.0) as bridge:
        start = wait_until(
            bridge,
            lambda state: state.map_name == "Iran Doctrine Range" and state.tick > 0,
            timeout=20,
        )
        state = bridge.state()
        roster = {unit.kind for unit in start.units}
        missing = sorted(EXPECTED_ROSTER - roster)
        if missing:
            raise RuntimeError(f"Fresh doctrine range is missing actors: {missing}")
        if state.get("player_faction") != "iran":
            raise RuntimeError(f"Faction selector resolved to {state.get('player_faction')!r}")
        if start.units_lost:
            raise RuntimeError(f"Fresh doctrine range already lost {start.units_lost} units")
        building_roster = {building.kind for building in start.buildings}
        if "irhpad" not in building_roster:
            raise RuntimeError("Fresh doctrine range has no Forward Aviation Pad for Toufan rearming")

        telemetry["runtime"] = {
            "map": start.map_name,
            "tick": start.tick,
            "phase": state.get("phase"),
            "player_faction": state.get("player_faction"),
            "enemy_faction": state.get("enemy_faction"),
            "cash": start.cash,
            "explored_percent": round(start.explored_percent, 2),
            "buildings": sorted(building_roster),
            "roster": [asdict(unit) for unit in start.units if unit.kind in EXPECTED_ROSTER],
        }
        capture(bridge, output, "01-doctrine-range.png", captures)

        headings = {
            "basij_infantry": move_trace(
                bridge,
                "irbas",
                [(61, 79), (61, 82), (64, 84), (62, 78)],
                tolerance=0,
                timeout_per_leg=8,
            ),
            "atgm_infantry": move_trace(
                bridge,
                "iratgm",
                [(62, 81), (64, 84), (66, 81), (63, 80)],
                tolerance=0,
                timeout_per_leg=8,
            ),
            "controller_infantry": move_trace(
                bridge,
                "irdc",
                [(63, 79), (62, 82), (66, 82), (64, 78)],
                tolerance=0,
                timeout_per_leg=8,
            ),
            "shadow_infantry": move_trace(
                bridge,
                "shadowone",
                [(64, 81), (62, 83), (67, 82), (65, 80)],
                tolerance=0,
                timeout_per_leg=8,
            ),
            "ground_vehicle": move_trace(
                bridge,
                "irkarr",
                [(69, 80), (70, 84), (66, 86), (62, 82)],
                tolerance=0,
                timeout_per_leg=5,
            ),
            "fixed_wing": move_trace(
                bridge,
                "irazar",
                [(70, 80), (70, 88), (61, 89), (59, 80)],
                tolerance=2,
                timeout_per_leg=6,
            ),
            "helicopter": move_trace(
                bridge,
                "irtoufan",
                [(69, 82), (68, 89), (60, 89), (59, 82)],
                tolerance=1,
                timeout_per_leg=6,
            ),
            "ship": move_trace(
                bridge,
                "irpey",
                [(37, 94), (39, 96), (39, 94), (37, 94)],
                tolerance=0,
                timeout_per_leg=5,
            ),
        }
        telemetry["checks"]["live_headings"] = headings
        capture(bridge, output, "02-live-headings.png", captures)

        # Toufan uses the stock two-pool helicopter ammo contract.  Fire one
        # burst, then exercise the aircraft deploy command (Return to Base) and
        # wait for the Forward Aviation Pad to restore the full combined pool.
        toufan_start = bridge.observe()
        toufan = own(toufan_start, "irtoufan")
        tank_for_toufan = enemy(toufan_start, "irantargettank")
        if toufan.ammo <= 0:
            raise RuntimeError(f"Toufan started without usable ammo: {toufan.ammo}")
        full_ammo = toufan.ammo
        fire_receipt = issue(
            bridge,
            "toufan-expend-ammo",
            ActionCommand("attack", toufan.actor_id, target_actor_id=tank_for_toufan.actor_id),
        )
        expended_state = wait_until(
            bridge,
            lambda state: 0 <= own(state, "irtoufan").ammo < full_ammo,
            timeout=12,
            interval=0.06,
        )
        expended = own(expended_state, "irtoufan")
        expended_ammo = expended.ammo
        return_receipt = issue(
            bridge,
            "toufan-return-to-pad",
            ActionCommand("deploy", expended.actor_id),
        )
        rearm_samples: list[dict[str, object]] = []
        deadline = time.monotonic() + 24
        rearmed_state = expended_state
        while time.monotonic() < deadline:
            rearmed_state = bridge.observe()
            rearming = own(rearmed_state, "irtoufan")
            sample = {
                "tick": rearmed_state.tick,
                "cell": [rearming.cell_x, rearming.cell_y],
                "ammo": rearming.ammo,
                "activity": rearming.current_activity,
            }
            if not rearm_samples or sample != rearm_samples[-1]:
                rearm_samples.append(sample)
            if rearming.ammo == full_ammo:
                break
            time.sleep(0.08)
        else:
            raise RuntimeError(
                f"Toufan failed to rearm from {expended_ammo} to {full_ammo}; "
                f"last sample: {rearm_samples[-1]}"
            )
        capture(bridge, output, "03-toufan-rearmed.png", captures)
        telemetry["checks"]["toufan_rearm"] = {
            "fire_receipt": fire_receipt,
            "return_receipt": return_receipt,
            "full_ammo": full_ammo,
            "ammo_after_fire": expended_ammo,
            "ammo_after_rearm": own(rearmed_state, "irtoufan").ammo,
            "forward_aviation_pad_present": True,
            "samples": rearm_samples,
        }

        # The ATGM must damage armor, enter its authored reload state, and stay
        # immobile when a move order is issued during that vulnerable window.
        tank_kind = "irantargettank"
        atgm_start = bridge.observe()
        atgm = own(atgm_start, "iratgm")
        tank = enemy(atgm_start, tank_kind)
        tank_hp_before = tank.hp_percent
        atgm_receipt = issue(
            bridge,
            "atgm-live-fire",
            ActionCommand("attack", atgm.actor_id, target_actor_id=tank.actor_id),
        )
        reload_state = wait_until(
            bridge,
            lambda state: own(state, "iratgm").reload_remaining_ticks > 0,
            timeout=12,
            interval=0.06,
        )
        reloading = own(reload_state, "iratgm")
        paused_cell = [reloading.cell_x, reloading.cell_y]
        issue(
            bridge,
            "atgm-move-during-reload",
            ActionCommand("move", reloading.actor_id, target_x=60, target_y=84),
        )
        time.sleep(0.8)
        paused_state = bridge.observe()
        paused_unit = own(paused_state, "iratgm")
        if paused_unit.reload_remaining_ticks <= 0:
            raise RuntimeError("ATGM reload completed before the vulnerability check")
        if [paused_unit.cell_x, paused_unit.cell_y] != paused_cell:
            raise RuntimeError("ATGM moved while its setup/reload condition was active")
        damaged_state = wait_until(
            bridge,
            lambda state: target_hp(state, tank_kind) < tank_hp_before,
            timeout=8,
            interval=0.08,
        )
        issue(
            bridge,
            "atgm-stop",
            ActionCommand("stop", own(damaged_state, "iratgm").actor_id),
        )
        telemetry["checks"]["atgm_setup_reload"] = {
            "receipt": atgm_receipt,
            "target_hp_before": tank_hp_before,
            "target_hp_after": target_hp(damaged_state, tank_kind),
            "reload_total_ticks": reloading.reload_total_ticks,
            "reload_remaining_at_move_order": reloading.reload_remaining_ticks,
            "cell_before_move_order": paused_cell,
            "cell_during_reload": [paused_unit.cell_x, paused_unit.cell_y],
            "movement_paused": True,
        }

        karrar_hit, karrar_before, karrar_receipt = first_damage(
            bridge, "irkarr", tank_kind, timeout=10
        )
        telemetry["checks"]["tank_combat"] = {
            "receipt": karrar_receipt,
            "target_hp_before": karrar_before,
            "target_hp_after": target_hp(karrar_hit, tank_kind),
        }

        shadow_start = bridge.observe()
        power = enemy(shadow_start, "powr")
        shadow_before = power.hp_percent
        shadow_receipt = issue(
            bridge,
            "shadowone-sabotage",
            ActionCommand(
                "attack",
                own(shadow_start, "shadowone").actor_id,
                target_actor_id=power.actor_id,
            ),
        )
        shadow_hit = wait_until(
            bridge,
            lambda state: target_hp(state, "powr") < shadow_before,
            timeout=12,
            interval=0.06,
        )
        capture(bridge, output, "04-shadow-sabotage.png", captures)
        issue(
            bridge,
            "shadowone-stop",
            ActionCommand("stop", own(shadow_hit, "shadowone").actor_id),
        )
        telemetry["checks"]["shadow_one"] = {
            "receipt": shadow_receipt,
            "target_hp_before": shadow_before,
            "target_hp_after": target_hp(shadow_hit, "powr"),
            "can_demolish": own(shadow_hit, "shadowone").can_demolish,
            "valid_demolition_targets": list(
                own(shadow_hit, "shadowone").valid_demolition_targets
            ),
        }

        loiter_start = bridge.observe()
        loiter = own(loiter_start, "irloiter")
        tank_before_loiter = target_hp(loiter_start, tank_kind)
        loiter_receipt = issue(
            bridge,
            "loitering-munition-dive",
            ActionCommand(
                "attack",
                loiter.actor_id,
                target_actor_id=enemy(loiter_start, tank_kind).actor_id,
            ),
        )
        time.sleep(0.35)
        capture(bridge, output, "05-loitering-attack.png", captures)
        loiter_end = wait_until(
            bridge,
            lambda state: all(unit.actor_id != loiter.actor_id for unit in state.units)
            and target_hp(state, tank_kind) < tank_before_loiter,
            timeout=15,
            interval=0.08,
        )
        telemetry["checks"]["loitering_munition"] = {
            "receipt": loiter_receipt,
            "actor_consumed": True,
            "target_hp_before": tank_before_loiter,
            "target_hp_after": target_hp(loiter_end, tank_kind),
        }

        naval_target = "irantargetpt"
        pey_hit, pey_before, pey_receipt = first_damage(
            bridge, "irpey", naval_target, timeout=10
        )
        # Let the missile impact settle before testing the submarine's native
        # two-torpedo burst, so the damage sources cannot be conflated.
        time.sleep(0.8)
        ghadir_hit, ghadir_before, ghadir_receipt = first_damage(
            bridge, "irghadir", naval_target, timeout=10
        )
        time.sleep(1.2)
        naval_end = bridge.observe()
        capture(bridge, output, "06-naval-combat.png", captures)
        telemetry["checks"]["naval_combat"] = {
            "peykaap": {
                "receipt": pey_receipt,
                "target_hp_before": pey_before,
                "target_hp_after": target_hp(pey_hit, naval_target),
            },
            "ghadir": {
                "receipt": ghadir_receipt,
                "target_hp_before": ghadir_before,
                "target_hp_after_first_impact": target_hp(ghadir_hit, naval_target),
                "target_hp_after_burst_settled": target_hp(naval_end, naval_target),
            },
            "target_survived": target_hp(naval_end, naval_target) > 0,
        }

        end = bridge.observe()
        telemetry["result"] = {
            "status": "passed",
            "end_tick": end.tick,
            "units_lost": end.units_lost,
            "units_killed": end.units_killed,
            "order_count": end.order_count,
            "captures": captures,
        }

    telemetry_path = output / "live-validation.json"
    telemetry_path.write_text(
        json.dumps(telemetry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(telemetry["result"], ensure_ascii=False))
    print(f"Telemetry: {telemetry_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
