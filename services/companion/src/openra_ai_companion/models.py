from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Unit:
    actor_id: int
    kind: str
    cell_x: int = 0
    cell_y: int = 0
    hp_percent: float = 1.0
    idle: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Unit":
        return cls(
            actor_id=int(value.get("actor_id", 0)),
            kind=str(value.get("type", value.get("kind", "unknown"))),
            cell_x=int(value.get("cell_x", 0)),
            cell_y=int(value.get("cell_y", 0)),
            hp_percent=float(value.get("hp_percent", 1.0)),
            idle=bool(value.get("is_idle", value.get("idle", False))),
        )


@dataclass(frozen=True)
class GameSnapshot:
    tick: int
    map_name: str = "Unknown battlefield"
    cash: int = 0
    ore: int = 0
    power_provided: int = 0
    power_drained: int = 0
    harvester_count: int = 0
    army_value: int = 0
    explored_percent: float = 0.0
    units: tuple[Unit, ...] = ()
    buildings: tuple[Unit, ...] = ()
    visible_enemies: tuple[Unit, ...] = ()
    visible_enemy_buildings: tuple[Unit, ...] = ()
    production: tuple[dict[str, Any], ...] = ()
    done: bool = False
    result: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GameSnapshot":
        economy = value.get("economy") or {}
        military = value.get("military") or {}
        map_info = value.get("map_info") or {}
        return cls(
            tick=int(value.get("tick", 0)),
            map_name=str(value.get("map_name", map_info.get("map_name", "Unknown battlefield"))),
            cash=int(value.get("cash", economy.get("cash", 0))),
            ore=int(value.get("ore", economy.get("ore", 0))),
            power_provided=int(value.get("power_provided", economy.get("power_provided", 0))),
            power_drained=int(value.get("power_drained", economy.get("power_drained", 0))),
            harvester_count=int(value.get("harvester_count", economy.get("harvester_count", 0))),
            army_value=int(value.get("army_value", military.get("army_value", 0))),
            explored_percent=float(value.get("explored_percent", 0)),
            units=tuple(Unit.from_dict(v) for v in value.get("units", [])),
            buildings=tuple(Unit.from_dict(v) for v in value.get("buildings", [])),
            visible_enemies=tuple(Unit.from_dict(v) for v in value.get("visible_enemies", [])),
            visible_enemy_buildings=tuple(Unit.from_dict(v) for v in value.get("visible_enemy_buildings", [])),
            production=tuple(value.get("production", [])),
            done=bool(value.get("done", False)),
            result=str(value.get("result", "")),
        )

    def compact(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "map": self.map_name,
            "economy": {
                "cash": self.cash,
                "ore": self.ore,
                "power": f"{self.power_provided}/{self.power_drained}",
                "harvesters": self.harvester_count,
            },
            "army_value": self.army_value,
            "explored_percent": round(self.explored_percent, 1),
            "own_units": len(self.units),
            "own_unit_types": [unit.kind for unit in self.units[:16]],
            "own_buildings": [building.kind for building in self.buildings[:16]],
            "visible_enemies": [
                {"type": unit.kind, "x": unit.cell_x, "y": unit.cell_y, "hp": round(unit.hp_percent, 2)}
                for unit in self.visible_enemies[:12]
            ],
            "visible_enemy_buildings": [unit.kind for unit in self.visible_enemy_buildings[:8]],
            "production": list(self.production[:6]),
            "done": self.done,
            "result": self.result,
        }


@dataclass(frozen=True)
class Insight:
    key: str
    score: int
    fact: str
    fallback_text: str
    tick: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompanionResponse:
    text: str
    source: str
    interrupted: bool = False
    utterance_id: int = 0
    insight: Insight | None = None
    latency_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.insight:
            result["insight"] = self.insight.as_dict()
        return result
