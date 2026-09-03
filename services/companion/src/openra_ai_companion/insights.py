from __future__ import annotations

from collections import Counter

from .models import GameSnapshot, Insight, ThreatAssessment
from .strategy import maximum_silo_count


THREAT_RANK = {"calm": 0, "guarded": 1, "high": 2, "critical": 3}
MESSAGE_INTERVAL_TICKS = {
    "calm": 1500,
    "guarded": 1500,
    "high": 250,
    "critical": 100,
}
EVENT_OVERRIDE_KEYS = frozenset({
    "opening_deploy",
    "enemy_spotted",
    "structure_spotted",
    "low_power",
    "storage_pressure",
    "no_harvester",
    "critical_damage",
    "mission_started",
    "mission_objective_updated",
    "mission_step_ready",
    "game_over",
})


def is_event_override_key(key: str) -> bool:
    """Return whether a state change should interrupt routine planning immediately."""
    return key in EVENT_OVERRIDE_KEYS or key.startswith("production_complete:")


def _completed_production_keys(snapshot: GameSnapshot) -> set[str]:
    return {
        f"production_complete:{str(item.get('item', 'unknown'))}"
        for item in snapshot.production
        if str(item.get("queue_type", "")).lower() in {"building", "defense"}
        and (
            float(item.get("progress", 0)) >= 0.999
            or int(item.get("remaining_ticks", 1)) <= 0
        )
    }


class InsightEngine:
    """Selects scarce, actionable interruptions before any model is called."""

    def __init__(self, cooldown_ticks: int = 750, situation_interval_ticks: int = 250):
        self.cooldown_ticks = cooldown_ticks
        self.situation_interval_ticks = situation_interval_ticks
        self.last_emitted: dict[str, int] = {}
        self.previous_enemy_ids: set[int] = set()
        self.previous_enemy_building_ids: set[int] = set()
        self.last_snapshot: GameSnapshot | None = None
        self.last_situation_tick = 0
        self.last_situation_signature: tuple | None = None
        self.last_message_tick: int | None = None
        self.previous_threat = "calm"
        self.acknowledged_completed_production: set[str] = set()
        self.last_event: Insight | None = None
        self.last_event_dispatched: dict[str, int] = {}

    def configure_pace(self, pace: str) -> None:
        """Tune routine chatter without delaying genuinely important events."""
        timings = {
            "calm": (1000, 750),
            "balanced": (750, 500),
            "frequent": (500, 250),
        }
        self.cooldown_ticks, self.situation_interval_ticks = timings.get(pace, timings["calm"])

    def _ready(self, key: str, tick: int) -> bool:
        return tick - self.last_emitted.get(key, -10_000_000) >= self.cooldown_ticks

    def _message_ready(self, insight: Insight, threat: ThreatAssessment) -> bool:
        if (
            insight.key == "game_over"
            or insight.key in {"mission_started", "mission_objective_updated"}
            or insight.key.startswith("production_complete:")
            or self.last_message_tick is None
        ):
            return True
        escalated = (
            THREAT_RANK.get(threat.level, 0) >= THREAT_RANK["high"]
            and THREAT_RANK.get(threat.level, 0) > THREAT_RANK.get(self.previous_threat, 0)
        )
        if escalated:
            return True
        interval = MESSAGE_INTERVAL_TICKS.get(threat.level, MESSAGE_INTERVAL_TICKS["calm"])
        return insight.tick - self.last_message_tick >= interval

    @staticmethod
    def _situation_signature(snapshot: GameSnapshot) -> tuple:
        production = tuple(sorted(
            (
                str(item.get("item", "unknown")),
                min(4, max(0, int(float(item.get("progress", 0)) * 4))),
                bool(item.get("paused", False)),
            )
            for item in snapshot.production
        ))
        return (
            snapshot.harvester_count,
            snapshot.power_drained > snapshot.power_provided,
            tuple(sorted(Counter(unit.kind for unit in snapshot.units).items())),
            tuple(sorted(Counter(building.kind for building in snapshot.buildings).items())),
            tuple(sorted(unit.actor_id for unit in snapshot.visible_enemies)),
            tuple(sorted(building.actor_id for building in snapshot.visible_enemy_buildings)),
            tuple(sorted(building.actor_id for building in snapshot.remembered_enemy_buildings)),
            tuple((objective.objective_id, objective.state) for objective in snapshot.objectives),
            production,
        )

    @staticmethod
    def _situation_fact(snapshot: GameSnapshot) -> str:
        if snapshot.production:
            counts = Counter(
                snapshot.actor_name(str(item.get("item", "")))
                for item in snapshot.production[:6]
            )
            items = ", ".join(
                f"{name} ×{count}" if count > 1 else name
                for name, count in counts.items()
            )
            production = f"active production: {items}"
        else:
            production = "production queues idle"
        return (
            f"Current situation: {snapshot.harvester_count} harvesters, "
            f"power balance {snapshot.power_provided - snapshot.power_drained}, "
            f"{len(snapshot.units)} units, {len(snapshot.buildings)} buildings, "
            f"{len(snapshot.visible_enemy_buildings)} visible and "
            f"{len(snapshot.remembered_enemy_buildings)} remembered enemy buildings, {production}"
        )

    def candidates(self, snapshot: GameSnapshot) -> list[Insight]:
        candidates: list[Insight] = []
        previous = self.last_snapshot
        if snapshot.mission_mode:
            objective_state = tuple(
                (objective.objective_id, objective.state, objective.description)
                for objective in snapshot.objectives
            )
            previous_state = tuple(
                (objective.objective_id, objective.state, objective.description)
                for objective in previous.objectives
            ) if previous and previous.mission_mode else ()
            if objective_state and (previous is None or objective_state != previous_state):
                active = next((objective for objective in snapshot.objectives if objective.state == "incomplete"), None)
                if active is not None:
                    key = "mission_started" if not previous_state else "mission_objective_updated"
                    candidates.append(Insight(
                        key,
                        99,
                        f"Mission objective: {active.description}",
                        f"Mission objective: {active.description} I am evaluating the scripted next step now.",
                        snapshot.tick,
                        "important",
                    ))
            # A scripted mission action must wake the deterministic controller as
            # soon as it completes. This is deliberately independent of the normal
            # notification interval, and it does not require an LLM call.
            current_special = next((
                unit for unit in snapshot.units
                if unit.can_disguise or unit.can_infiltrate or unit.can_demolish or unit.kind.lower().split(".", 1)[0] == "spy"
            ), None)
            previous_special = next((
                unit for unit in previous.units
                if unit.can_disguise or unit.can_infiltrate or unit.can_demolish or unit.kind.lower().split(".", 1)[0] == "spy"
            ), None) if previous and previous.mission_mode else None
            special_advanced = (
                current_special is not None
                and previous_special is not None
                and current_special.idle
                and (
                    not previous_special.idle
                    or current_special.is_disguised != previous_special.is_disguised
                    or (current_special.cell_x, current_special.cell_y)
                    != (previous_special.cell_x, previous_special.cell_y)
                )
            )
            if special_advanced:
                candidates.append(Insight(
                    "mission_step_ready",
                    98,
                    "The scripted mission unit completed a step",
                    "Mission step complete; I am re-checking objectives and patrol positions.",
                    snapshot.tick,
                    "routine",
                ))
        undeployed_mcv = next((unit for unit in snapshot.units if unit.kind.split(".", 1)[0] in {"mcv", "amcv", "smcv"}), None)
        if previous is None and undeployed_mcv is not None and not snapshot.buildings:
            name = snapshot.actor_name(undeployed_mcv.kind)
            candidates.append(Insight(
                "opening_deploy",
                85,
                f"Starting {name} is ready to deploy",
                f"Your starting {name} is ready to deploy.",
                snapshot.tick,
            ))
        new_enemies = [u for u in snapshot.visible_enemies if u.actor_id not in self.previous_enemy_ids]
        new_structures = [u for u in snapshot.visible_enemy_buildings if u.actor_id not in self.previous_enemy_building_ids]

        if new_enemies and self._ready("enemy_spotted", snapshot.tick):
            kinds = ", ".join(dict.fromkeys(snapshot.actor_name(u.kind) for u in new_enemies[:4]))
            candidates.append(Insight("enemy_spotted", 96, f"New enemy units visible: {kinds}", f"New contact: {kinds}. Check the visible approach.", snapshot.tick, "important"))
        if new_structures and self._ready("structure_spotted", snapshot.tick):
            kinds = ", ".join(dict.fromkeys(snapshot.actor_name(u.kind) for u in new_structures[:3]))
            candidates.append(Insight("structure_spotted", 88, f"New enemy structures visible: {kinds}", f"Enemy structure identified: {kinds}.", snapshot.tick, "important"))
        power_deficit_started = (
            snapshot.power_drained > snapshot.power_provided
            and (previous is None or previous.power_drained <= previous.power_provided)
        )
        if power_deficit_started and self._ready("low_power", snapshot.tick):
            deficit = snapshot.power_drained - snapshot.power_provided
            candidates.append(Insight("low_power", 91, f"Power deficit is {deficit}", f"Power is short by {deficit}. Production and defenses may be impaired.", snapshot.tick, "critical"))
        storage_pressure = (
            snapshot.resource_capacity > 0
            and snapshot.ore * 100 > snapshot.resource_capacity * 80
        )
        silo_queued = any(
            str(item.get("item", "")).lower().split(".", 1)[0] == "silo"
            for item in snapshot.production
        )
        silo_count = sum(
            building.kind.lower().split(".", 1)[0] == "silo"
            for building in snapshot.buildings
        )
        at_silo_limit = silo_count >= maximum_silo_count(snapshot)
        overflow_spending_active = at_silo_limit and any(
            str(item.get("queue_type", "")).lower() in {"infantry", "vehicle", "aircraft"}
            for item in snapshot.production
        )
        if storage_pressure and not silo_queued and not overflow_spending_active:
            percent = round(snapshot.ore / snapshot.resource_capacity * 100)
            candidates.append(Insight(
                "storage_pressure",
                89,
                f"Ore storage is {percent}% full",
                "Ore storage is nearly full. Convert reserves into combat production now."
                if at_silo_limit else
                "Ore storage is nearly full. Build a silo so harvesters can keep unloading.",
                snapshot.tick,
                "important",
            ))
        has_refinery = any(building.kind in {"proc", "refinery"} for building in snapshot.buildings)
        previous_has_refinery = bool(previous and any(
            building.kind in {"proc", "refinery"} for building in previous.buildings
        ))
        harvester_outage_started = (
            snapshot.tick > 400
            and snapshot.harvester_count == 0
            and (has_refinery or (previous is not None and previous.harvester_count > 0))
            and (
                previous is None
                or previous.harvester_count > 0
                or previous.tick <= 400
                or (has_refinery and not previous_has_refinery)
            )
        )
        if harvester_outage_started and self._ready("no_harvester", snapshot.tick):
            candidates.append(Insight("no_harvester", 90, "No active harvester", "You have no active harvester. Your economy will stall.", snapshot.tick, "important"))
        if previous and previous.harvester_count == 0 and snapshot.harvester_count > 0:
            candidates.append(Insight(
                "economy_recovered",
                89,
                f"Harvester count recovered to {snapshot.harvester_count}",
                "A harvester is active now; the earlier economy warning is resolved.",
                snapshot.tick,
                "important",
            ))
        if (
            previous
            and previous.power_drained > previous.power_provided
            and snapshot.power_drained <= snapshot.power_provided
        ):
            candidates.append(Insight(
                "power_restored",
                86,
                f"Power recovered to {snapshot.power_provided}/{snapshot.power_drained}",
                "Power is back online; the earlier deficit is resolved.",
                snapshot.tick,
                "important",
            ))
        for key in sorted(_completed_production_keys(snapshot) - self.acknowledged_completed_production):
            item = key.split(":", 1)[1]
            name = snapshot.actor_name(item)
            candidates.append(Insight(
                key,
                98,
                f"Production completed: {name}",
                f"{name} has completed production.",
                snapshot.tick,
                "important",
            ))

        if previous and len(snapshot.units) + len(snapshot.buildings) > len(previous.units) + len(previous.buildings):
            previous_production = {
                str(item.get("item", "unknown")): str(item.get("queue_type", "")).lower()
                for item in previous.production
            }
            current_production = {str(item.get("item", "unknown")) for item in snapshot.production}
            new_building_kinds = {
                building.kind.lower().split(".", 1)[0]
                for building in snapshot.buildings
                if building.actor_id not in {previous_building.actor_id for previous_building in previous.buildings}
            }
            completed = sorted(
                item for item, queue_type in previous_production.items()
                if item not in current_production
                and (queue_type in {"building", "defense"} or item.split(".", 1)[0] in new_building_kinds)
            )
            if completed:
                item = completed[0]
                key = f"production_complete:{item}"
                if self._ready(key, snapshot.tick):
                    name = snapshot.actor_name(item)
                    candidates.append(Insight(
                        key,
                        98,
                        f"Production completed: {name}",
                        f"{name} has completed production.",
                        snapshot.tick,
                        "important",
                    ))
        if snapshot.cash < 350 and not snapshot.production and snapshot.tick > 600 and self._ready("economy_idle", snapshot.tick):
            candidates.append(Insight("economy_idle", 68, f"Cash is {snapshot.cash} with no active production", "Cash is low and every production queue is idle.", snapshot.tick, "important"))
        critical = [
            (unit, snapshot.actor_name(unit.kind))
            for unit in snapshot.units
            if unit.hp_percent <= 0.22
        ] + [
            (building, snapshot.actor_name(building.kind))
            for building in snapshot.buildings
            if building.hp_percent <= 0.22
        ]
        if critical and self._ready("critical_damage", snapshot.tick):
            target, name = critical[0]
            candidates.append(Insight("critical_damage", 84, f"{name} is at {round(target.hp_percent * 100)}% health", f"Your {name} is critically damaged.", snapshot.tick, "critical"))
        if snapshot.done and self._ready("game_over", snapshot.tick):
            candidates.append(Insight("game_over", 100, f"Match result: {snapshot.result or 'complete'}", f"Match complete: {snapshot.result or 'result pending'}.", snapshot.tick, "critical"))
        signature = self._situation_signature(snapshot)
        if (
            self.last_situation_signature is not None
            and signature != self.last_situation_signature
            and snapshot.tick - self.last_situation_tick >= self.situation_interval_ticks
        ):
            fact = self._situation_fact(snapshot)
            candidates.append(Insight("situation_update", 81, fact, fact + ".", snapshot.tick))
        return sorted(candidates, key=lambda item: item.score, reverse=True)

    def select(
        self,
        snapshot: GameSnapshot,
        threshold: int = 80,
        threat: ThreatAssessment | None = None,
    ) -> Insight | None:
        threat = threat or ThreatAssessment()
        if self.last_snapshot is not None and snapshot.tick < self.last_snapshot.tick:
            self.last_emitted.clear()
            self.previous_enemy_ids.clear()
            self.previous_enemy_building_ids.clear()
            self.last_message_tick = None
            self.previous_threat = "calm"
            self.acknowledged_completed_production.clear()
            self.last_event_dispatched.clear()
        self.acknowledged_completed_production.intersection_update(_completed_production_keys(snapshot))
        candidates = self.candidates(snapshot)
        candidate = candidates[0] if candidates and candidates[0].score >= threshold else None
        self.last_event = None
        if (
            candidate is not None
            and is_event_override_key(candidate.key)
            and candidate.tick - self.last_event_dispatched.get(candidate.key, -10_000_000) >= (
                100 if candidate.key == "storage_pressure" else self.cooldown_ticks
                if candidate.key == "critical_damage" else 0
            )
        ):
            self.last_event = candidate
            self.last_event_dispatched[candidate.key] = candidate.tick
        selected = candidate
        if selected is not None and not self._message_ready(selected, threat):
            selected = None
        self.previous_enemy_ids = {u.actor_id for u in snapshot.visible_enemies}
        self.previous_enemy_building_ids.update(u.actor_id for u in snapshot.visible_enemy_buildings)
        self.previous_threat = threat.level
        self.last_snapshot = snapshot
        signature = self._situation_signature(snapshot)
        if self.last_situation_signature is None or selected:
            self.last_situation_signature = signature
            self.last_situation_tick = snapshot.tick
        if selected:
            self.last_emitted[selected.key] = selected.tick
            self.last_message_tick = selected.tick
            if selected.key.startswith("production_complete:"):
                self.acknowledged_completed_production.add(selected.key)
        return selected
