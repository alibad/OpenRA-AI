from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .models import ActionCommand, GameSnapshot, Unit
from .strategy import base_center, tactical_plan
from .strategy_contracts import StrategyProgram, compile_strategy_program


@dataclass(frozen=True)
class ControllerDecision:
    owner: str
    priority: int
    key: str
    summary: str
    commands: tuple[ActionCommand, ...]
    evidence: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "priority": self.priority,
            "key": self.key,
            "summary": self.summary,
            "commands": [command.as_dict() for command in self.commands],
            "evidence": self.evidence,
        }


def _kind(actor: Unit) -> str:
    return actor.kind.lower().split("@", 1)[0].split(".", 1)[0]


def _distance(left: Unit, right: Unit) -> float:
    return math.hypot(left.cell_x - right.cell_x, left.cell_y - right.cell_y)


class TacticalController:
    """Fast, deterministic safety and micro loop above slow strategic planning."""

    def __init__(self) -> None:
        self._retreat_cooldown_until: dict[int, int] = {}

    def decide(self, snapshot: GameSnapshot, profile: str = "normal") -> ControllerDecision | None:
        program = compile_strategy_program(profile, snapshot)
        plan = tactical_plan(snapshot)

        escapes = plan["immediate_safety"]["spy_dog_escapes"]
        if escapes:
            commands = tuple(
                ActionCommand(
                    "move",
                    actor_id=int(item["spy_actor_id"]),
                    target_x=int(item["immediate_move_to"][0]),
                    target_y=int(item["immediate_move_to"][1]),
                )
                for item in escapes[:4]
            )
            return ControllerDecision(
                "safety", 100, "spy-dog-escape",
                "Move exposed Spies outside visible dog detection zones",
                commands, {"hazards": escapes},
            )

        unit_by_id = {unit.actor_id: unit for unit in snapshot.units}
        damaged = []
        for item in plan["immediate_safety"]["damaged_armor_retreats"]:
            unit = unit_by_id.get(int(item["actor_id"]))
            retreat = item["retreat_to"]
            if (
                unit is not None
                and float(item["hp_percent"]) / 100 < program.retreat_hp
                and math.hypot(unit.cell_x - int(retreat[0]), unit.cell_y - int(retreat[1])) > 2.5
                and snapshot.tick >= self._retreat_cooldown_until.get(unit.actor_id, 0)
                and not (
                    not unit.idle
                    and unit.move_target_x == int(retreat[0])
                    and unit.move_target_y == int(retreat[1])
                )
            ):
                damaged.append(item)
        if damaged:
            commands = tuple(
                ActionCommand(
                    "move",
                    actor_id=int(item["actor_id"]),
                    target_x=int(item["retreat_to"][0]),
                    target_y=int(item["retreat_to"][1]),
                )
                for item in damaged[:8]
            )
            for item in damaged[:8]:
                self._retreat_cooldown_until[int(item["actor_id"])] = snapshot.tick + 750
            return ControllerDecision(
                "safety", 95, "retreat-damaged-armor",
                "Withdraw critically damaged armor for repair or preservation",
                commands, {"retreat_hp": program.retreat_hp, "units": damaged},
            )

        siege_threats = plan["immediate_safety"]["siege_threats"]
        if siege_threats:
            commands = tuple(
                ActionCommand(
                    "move",
                    actor_id=int(item["siege_actor_id"]),
                    target_x=int(item["retreat_to"][0]),
                    target_y=int(item["retreat_to"][1]),
                )
                for item in siege_threats[:4]
            )
            return ControllerDecision(
                "safety", 92, "protect-siege",
                "Pull exposed artillery behind the armored screen",
                commands, {"threats": siege_threats},
            )

        aircraft_ids = set(plan["air_response"]["visible_aircraft_ids"])
        if aircraft_ids:
            aircraft = [enemy for enemy in snapshot.visible_enemies if enemy.actor_id in aircraft_ids]
            counters = [
                unit for unit in snapshot.units
                if unit.can_attack and unit.can_target_air and unit.hp_percent > program.retreat_hp
            ]
            if aircraft and counters:
                commands = tuple(
                    ActionCommand(
                        "attack",
                        actor_id=unit.actor_id,
                        target_actor_id=min(aircraft, key=lambda target: _distance(unit, target)).actor_id,
                    )
                    for unit in sorted(counters, key=lambda value: value.actor_id)[:8]
                )
                return ControllerDecision(
                    "safety", 90, "intercept-aircraft",
                    "Focus visible aircraft with available anti-air units",
                    commands, {"aircraft_ids": sorted(aircraft_ids), "counter_ids": [unit.actor_id for unit in counters]},
                )

            counter = next(iter(plan["air_response"]["available_counter_production"]), "")
            if counter:
                return ControllerDecision(
                    "operational", 80, "produce-anti-air",
                    "Produce an available counter to the visible aircraft",
                    (ActionCommand("train", item_type=str(counter)),),
                    {"aircraft_ids": sorted(aircraft_ids), "counter": counter},
                )

        enemies = {enemy.actor_id: enemy for enemy in snapshot.visible_enemies}
        standoff_commands: list[ActionCommand] = []
        edges = []
        for edge in plan["range_control"]["tank_engagement_edges"]:
            tank = next((unit for unit in snapshot.units if unit.actor_id == edge["tank_actor_id"]), None)
            enemy = enemies.get(int(edge["enemy_actor_id"]))
            if tank is None or enemy is None or not edge["can_outrange"]:
                continue
            # Reposition only inside the opponent's impact envelope, and prefer
            # doing it while our weapon is reloading. This avoids needless kiting.
            if float(edge["distance_cells"]) > float(edge["enemy_range_cells"]) + 0.75:
                continue
            if tank.reload_total_ticks > 0 and tank.reload_remaining_ticks <= 0 and tank.hp_percent >= 0.7:
                continue
            hold = edge["standoff_or_safe_hold"]
            standoff_commands.append(ActionCommand(
                "move", actor_id=tank.actor_id, target_x=int(hold[0]), target_y=int(hold[1]),
            ))
            edges.append(edge)
        if standoff_commands:
            return ControllerDecision(
                "safety", 88, "range-kite",
                "Reposition longer-ranged armor outside hostile impact range",
                tuple(standoff_commands[:6]), {"engagement_edges": edges},
            )

        lure = plan["defensive_lure"]
        own_attackers = [unit for unit in snapshot.units if unit.can_attack and unit.hp_percent > program.retreat_hp]
        visible_attackers = [unit for unit in snapshot.visible_enemies if unit.can_attack]
        if lure.get("available") and len(visible_attackers) > max(2, len(own_attackers)):
            anchor = lure["fallback_anchor_behind_defense"]
            commands = tuple(
                ActionCommand("move", actor_id=unit.actor_id, target_x=int(anchor[0]), target_y=int(anchor[1]))
                for unit in sorted(own_attackers, key=lambda value: value.actor_id)[:10]
            )
            if commands:
                return ControllerDecision(
                    "safety", 86, "lure-through-defense",
                    "Fall back behind powered defenses and force the larger enemy group into coverage",
                    commands, {"own": len(own_attackers), "enemy": len(visible_attackers), "lure": lure},
                )

        cohesion = plan["formation"]["tank_cohesion"]
        if not snapshot.visible_enemies and cohesion["status"] == "dispersed":
            center = cohesion["center"]
            stragglers = set(cohesion["straggler_actor_ids"])
            commands = tuple(
                ActionCommand("move", actor_id=unit.actor_id, target_x=int(center[0]), target_y=int(center[1]))
                for unit in snapshot.units
                if unit.actor_id in stragglers and unit.idle
            )
            if commands:
                return ControllerDecision(
                    "operational", 45, "regroup-armor",
                    "Regroup idle tank stragglers before the next engagement",
                    commands[:6], {"cohesion": cohesion},
                )

        return None


def controller_state(snapshot: GameSnapshot, profile: str) -> dict[str, Any]:
    program: StrategyProgram = compile_strategy_program(profile, snapshot)
    decision = TacticalController().decide(snapshot, profile)
    return {
        "strategy_program": program.as_dict(),
        "next_fast_decision": decision.as_dict() if decision is not None else None,
        "home": list(base_center(snapshot)),
    }
