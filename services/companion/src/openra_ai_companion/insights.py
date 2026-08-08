from __future__ import annotations

from collections import Counter

from .models import GameSnapshot, Insight


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
            production,
        )

    @staticmethod
    def _situation_fact(snapshot: GameSnapshot) -> str:
        if snapshot.production:
            items = ", ".join(
                str(item.get("item", "unknown"))
                for item in snapshot.production[:3]
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
        new_enemies = [u for u in snapshot.visible_enemies if u.actor_id not in self.previous_enemy_ids]
        new_structures = [u for u in snapshot.visible_enemy_buildings if u.actor_id not in self.previous_enemy_building_ids]

        if new_enemies and self._ready("enemy_spotted", snapshot.tick):
            kinds = ", ".join(dict.fromkeys(u.kind for u in new_enemies[:4]))
            candidates.append(Insight("enemy_spotted", 96, f"New enemy units visible: {kinds}", f"New contact: {kinds}. Check the visible approach.", snapshot.tick, "important"))
        if new_structures and self._ready("structure_spotted", snapshot.tick):
            kinds = ", ".join(dict.fromkeys(u.kind for u in new_structures[:3]))
            candidates.append(Insight("structure_spotted", 88, f"New enemy structures visible: {kinds}", f"Enemy structure identified: {kinds}.", snapshot.tick, "important"))
        if snapshot.power_drained > snapshot.power_provided and self._ready("low_power", snapshot.tick):
            deficit = snapshot.power_drained - snapshot.power_provided
            candidates.append(Insight("low_power", 91, f"Power deficit is {deficit}", f"Power is short by {deficit}. Production and defenses may be impaired.", snapshot.tick, "critical"))
        if snapshot.tick > 400 and snapshot.harvester_count == 0 and self._ready("no_harvester", snapshot.tick):
            candidates.append(Insight("no_harvester", 94, "No active harvester", "You have no active harvester. Your economy will stall.", snapshot.tick, "critical"))
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
        if previous and len(snapshot.units) + len(snapshot.buildings) > len(previous.units) + len(previous.buildings):
            previous_production = {str(item.get("item", "unknown")) for item in previous.production}
            current_production = {str(item.get("item", "unknown")) for item in snapshot.production}
            completed = sorted(previous_production - current_production)
            if completed:
                item = completed[0]
                key = f"production_complete:{item}"
                if self._ready(key, snapshot.tick):
                    candidates.append(Insight(
                        key,
                        84,
                        f"Production completed: {item}",
                        f"{item} has completed production.",
                        snapshot.tick,
                    ))
        if snapshot.cash < 350 and not snapshot.production and snapshot.tick > 600 and self._ready("economy_idle", snapshot.tick):
            candidates.append(Insight("economy_idle", 68, f"Cash is {snapshot.cash} with no active production", "Cash is low and every production queue is idle.", snapshot.tick, "important"))
        critical = [u for u in (*snapshot.units, *snapshot.buildings) if u.hp_percent <= 0.22]
        if critical and self._ready("critical_damage", snapshot.tick):
            target = critical[0]
            candidates.append(Insight("critical_damage", 84, f"{target.kind} is at {round(target.hp_percent * 100)}% health", f"Your {target.kind} is critically damaged.", snapshot.tick, "critical"))
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

    def select(self, snapshot: GameSnapshot, threshold: int = 80) -> Insight | None:
        candidates = self.candidates(snapshot)
        selected = candidates[0] if candidates and candidates[0].score >= threshold else None
        self.previous_enemy_ids = {u.actor_id for u in snapshot.visible_enemies}
        self.previous_enemy_building_ids.update(u.actor_id for u in snapshot.visible_enemy_buildings)
        self.last_snapshot = snapshot
        signature = self._situation_signature(snapshot)
        if self.last_situation_signature is None or selected:
            self.last_situation_signature = signature
            self.last_situation_tick = snapshot.tick
        if selected:
            self.last_emitted[selected.key] = selected.tick
        return selected
