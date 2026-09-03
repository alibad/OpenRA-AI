from __future__ import annotations

import base64
import binascii
from dataclasses import asdict, dataclass, field
from typing import Any

from .labels import building_name, production_name, unit_name


SAFE_ACTIONS = frozenset({
    "move",
    "attack_move",
    "attack",
    "stop",
    "harvest",
    "build",
    "train",
    "deploy",
    "sell",
    "repair",
    "place_building",
    "cancel_production",
    "set_rally_point",
    "guard",
    "set_stance",
    "enter_transport",
    "disguise",
    "infiltrate",
    "demolish",
    "capture",
    "unload",
    "power_down",
    "set_primary",
    "use_support_power",
})

ACTOR_ACTIONS = frozenset({
    "move",
    "attack_move",
    "attack",
    "stop",
    "harvest",
    "deploy",
    "sell",
    "repair",
    "set_rally_point",
    "guard",
    "set_stance",
    "enter_transport",
    "disguise",
    "infiltrate",
    "demolish",
    "capture",
    "unload",
    "power_down",
    "set_primary",
})
POSITION_ACTIONS = frozenset({"move", "attack_move", "harvest", "place_building", "set_rally_point", "use_support_power"})
ITEM_ACTIONS = frozenset({"build", "train", "place_building", "cancel_production", "use_support_power"})
TARGET_ACTOR_ACTIONS = frozenset({"attack", "guard", "enter_transport", "disguise", "infiltrate", "demolish", "capture"})


@dataclass(frozen=True)
class Unit:
    actor_id: int
    kind: str
    cell_x: int = 0
    cell_y: int = 0
    hp_percent: float = 1.0
    idle: bool = False
    can_attack: bool = False
    current_activity: str = ""
    owner: str = ""
    ammo: int = -1
    facing: int = 0
    experience_level: int = 0
    stance: int = 0
    speed: int = 0
    attack_range: int = 0
    minimum_attack_range: int = 0
    armor_type: str = ""
    target_types: tuple[str, ...] = ()
    cost: int = 0
    reload_remaining_ticks: int = 0
    reload_total_ticks: int = 0
    weapon: str = ""
    burst: int = 0
    current_target_actor_id: int = 0
    move_target_x: int = -1
    move_target_y: int = -1
    can_target_air: bool = False
    can_target_ground: bool = False
    last_seen_tick: int = 0
    passenger_count: int = -1
    is_building: bool = False
    is_producing: bool = False
    production_progress: float = 0.0
    producing_item: str = ""
    powered: bool = True
    repairing: bool = False
    sell_value: int = 0
    rally_x: int = -1
    rally_y: int = -1
    power_amount: int = 0
    can_produce: tuple[str, ...] = ()
    is_disguised: bool = False
    disguise_owner: str = ""
    can_disguise: bool = False
    can_infiltrate: bool = False
    valid_disguise_targets: tuple[int, ...] = ()
    valid_infiltration_targets: tuple[int, ...] = ()
    detects_disguise: bool = False
    can_demolish: bool = False
    valid_demolition_targets: tuple[int, ...] = ()
    can_capture: bool = False
    valid_capture_targets: tuple[int, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Unit":
        return cls(
            actor_id=int(value.get("actor_id", 0)),
            kind=str(value.get("type", value.get("kind", "unknown"))),
            cell_x=int(value.get("cell_x", 0)),
            cell_y=int(value.get("cell_y", 0)),
            hp_percent=float(value.get("hp_percent", 1.0)),
            idle=bool(value.get("is_idle", value.get("idle", False))),
            can_attack=bool(value.get("can_attack", False)),
            current_activity=str(value.get("current_activity", "")),
            owner=str(value.get("owner", "")),
            ammo=int(value.get("ammo", -1)),
            facing=int(value.get("facing", 0)),
            experience_level=int(value.get("experience_level", 0)),
            stance=int(value.get("stance", 0)),
            speed=int(value.get("speed", 0)),
            attack_range=int(value.get("attack_range", 0)),
            minimum_attack_range=int(value.get("minimum_attack_range", 0)),
            armor_type=str(value.get("armor_type", "")),
            target_types=tuple(str(item) for item in value.get("target_types", [])),
            cost=int(value.get("cost", 0)),
            reload_remaining_ticks=int(value.get("reload_remaining_ticks", 0)),
            reload_total_ticks=int(value.get("reload_total_ticks", 0)),
            weapon=str(value.get("weapon", "")),
            burst=int(value.get("burst", 0)),
            current_target_actor_id=int(value.get("current_target_actor_id", 0)),
            move_target_x=int(value.get("move_target_x", -1)),
            move_target_y=int(value.get("move_target_y", -1)),
            can_target_air=bool(value.get("can_target_air", False)),
            can_target_ground=bool(value.get("can_target_ground", False)),
            last_seen_tick=int(value.get("last_seen_tick", 0)),
            passenger_count=int(value.get("passenger_count", -1)),
            is_building=bool(value.get("is_building", False)),
            is_producing=bool(value.get("is_producing", False)),
            production_progress=float(value.get("production_progress", 0.0)),
            producing_item=str(value.get("producing_item", "")),
            powered=bool(value.get("is_powered", value.get("powered", True))),
            repairing=bool(value.get("is_repairing", value.get("repairing", False))),
            sell_value=int(value.get("sell_value", 0)),
            rally_x=int(value.get("rally_x", -1)),
            rally_y=int(value.get("rally_y", -1)),
            power_amount=int(value.get("power_amount", 0)),
            can_produce=tuple(str(item) for item in value.get("can_produce", [])),
            is_disguised=bool(value.get("is_disguised", False)),
            disguise_owner=str(value.get("disguise_owner", "")),
            can_disguise=bool(value.get("can_disguise", False)),
            can_infiltrate=bool(value.get("can_infiltrate", False)),
            valid_disguise_targets=tuple(int(item) for item in value.get("valid_disguise_targets", [])),
            valid_infiltration_targets=tuple(int(item) for item in value.get("valid_infiltration_targets", [])),
            detects_disguise=bool(value.get("detects_disguise", False)),
            can_demolish=bool(value.get("can_demolish", False)),
            valid_demolition_targets=tuple(int(item) for item in value.get("valid_demolition_targets", [])),
            can_capture=bool(value.get("can_capture", False)),
            valid_capture_targets=tuple(int(item) for item in value.get("valid_capture_targets", [])),
        )


@dataclass(frozen=True)
class MissionObjective:
    objective_id: int
    description: str
    kind: str = "Primary"
    required: bool = True
    state: str = "incomplete"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MissionObjective":
        return cls(
            objective_id=int(value.get("id", value.get("objective_id", 0))),
            description=str(value.get("description", "")),
            kind=str(value.get("type", value.get("kind", "Primary"))),
            required=bool(value.get("required", True)),
            state=str(value.get("state", "incomplete")).lower(),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.objective_id,
            "description": self.description,
            "type": self.kind,
            "required": self.required,
            "state": self.state,
        }


@dataclass(frozen=True)
class GameSnapshot:
    tick: int
    map_name: str = "Unknown battlefield"
    cash: int = 0
    ore: int = 0
    resource_capacity: int = 0
    power_provided: int = 0
    power_drained: int = 0
    harvester_count: int = 0
    army_value: int = 0
    assets_value: int = 0
    units_killed: int = 0
    units_lost: int = 0
    buildings_killed: int = 0
    buildings_lost: int = 0
    kills_cost: int = 0
    deaths_cost: int = 0
    order_count: int = 0
    explored_percent: float = 0.0
    map_width: int = 0
    map_height: int = 0
    map_bounds_x: int = 0
    map_bounds_y: int = 0
    map_bounds_width: int = 0
    map_bounds_height: int = 0
    units: tuple[Unit, ...] = ()
    buildings: tuple[Unit, ...] = ()
    visible_enemies: tuple[Unit, ...] = ()
    visible_enemy_buildings: tuple[Unit, ...] = ()
    remembered_enemy_buildings: tuple[Unit, ...] = ()
    production: tuple[dict[str, Any], ...] = ()
    available_production: tuple[str, ...] = ()
    spatial_map: bytes = b""
    spatial_channels: int = 0
    done: bool = False
    reward: float = 0.0
    result: str = ""
    interrupted: bool = False
    interrupt_reason: str = ""
    actual_ticks_advanced: int = 0
    mission_mode: bool = False
    mission_briefing: str = ""
    objectives: tuple[MissionObjective, ...] = ()
    support_powers: tuple[dict[str, Any], ...] = ()
    mod_id: str = "ra"
    actor_names: dict[str, str] = field(default_factory=dict)

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
            resource_capacity=int(value.get("resource_capacity", economy.get("resource_capacity", 0))),
            power_provided=int(value.get("power_provided", economy.get("power_provided", 0))),
            power_drained=int(value.get("power_drained", economy.get("power_drained", 0))),
            harvester_count=int(value.get("harvester_count", economy.get("harvester_count", 0))),
            army_value=int(value.get("army_value", military.get("army_value", 0))),
            assets_value=int(value.get("assets_value", military.get("assets_value", 0))),
            units_killed=int(value.get("units_killed", military.get("units_killed", 0))),
            units_lost=int(value.get("units_lost", military.get("units_lost", 0))),
            buildings_killed=int(value.get("buildings_killed", military.get("buildings_killed", 0))),
            buildings_lost=int(value.get("buildings_lost", military.get("buildings_lost", 0))),
            kills_cost=int(value.get("kills_cost", military.get("kills_cost", 0))),
            deaths_cost=int(value.get("deaths_cost", military.get("deaths_cost", 0))),
            order_count=int(value.get("order_count", military.get("order_count", 0))),
            explored_percent=float(value.get("explored_percent", 0)),
            map_width=int(value.get("map_width", map_info.get("width", 0))),
            map_height=int(value.get("map_height", map_info.get("height", 0))),
            map_bounds_x=int(value.get("map_bounds_x", map_info.get("bounds_x", 0))),
            map_bounds_y=int(value.get("map_bounds_y", map_info.get("bounds_y", 0))),
            map_bounds_width=int(value.get("map_bounds_width", map_info.get("bounds_width", map_info.get("width", 0)))),
            map_bounds_height=int(value.get("map_bounds_height", map_info.get("bounds_height", map_info.get("height", 0)))),
            units=tuple(Unit.from_dict(v) for v in value.get("units", [])),
            buildings=tuple(Unit.from_dict(v) for v in value.get("buildings", [])),
            visible_enemies=tuple(Unit.from_dict(v) for v in value.get("visible_enemies", [])),
            visible_enemy_buildings=tuple(Unit.from_dict(v) for v in value.get("visible_enemy_buildings", [])),
            remembered_enemy_buildings=tuple(Unit.from_dict(v) for v in value.get("remembered_enemy_buildings", [])),
            production=tuple(value.get("production", [])),
            available_production=tuple(str(item) for item in value.get("available_production", [])),
            spatial_map=cls._decode_bytes(value.get("spatial_map", b"")),
            spatial_channels=int(value.get("spatial_channels", 0)),
            done=bool(value.get("done", False)),
            reward=float(value.get("reward", 0.0)),
            result=str(value.get("result", "")),
            interrupted=bool(value.get("interrupted", False)),
            interrupt_reason=str(value.get("interrupt_reason", "")),
            actual_ticks_advanced=int(value.get("actual_ticks_advanced", 0)),
            mission_mode=bool(value.get("mission_mode", False)),
            mission_briefing=str(value.get("mission_briefing", "")),
            objectives=tuple(MissionObjective.from_dict(item) for item in value.get("objectives", [])),
            support_powers=tuple(dict(item) for item in value.get("support_powers", [])),
            mod_id=str(value.get("mod_id") or "ra"),
            actor_names={str(key): str(name) for key, name in (value.get("actor_names") or {}).items()},
        )

    @staticmethod
    def _decode_bytes(value: Any) -> bytes:
        if isinstance(value, bytes):
            return value
        if not isinstance(value, str) or not value:
            return b""
        try:
            return base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            return b""

    def contains_cell(self, x: int, y: int) -> bool:
        if self.mod_id == "ra2":
            return 0 <= x < self.map_width and 0 <= y < self.map_height
        width = self.map_bounds_width or self.map_width
        height = self.map_bounds_height or self.map_height
        return (
            self.map_bounds_x <= x < self.map_bounds_x + width
            and self.map_bounds_y <= y < self.map_bounds_y + height
        )

    def actor_name(self, kind: str) -> str:
        return self.actor_names.get(kind, production_name(kind) if self.mod_id == "ra" else kind)

    def humanize_text(self, text: str) -> str:
        from .labels import humanize_text
        return humanize_text(text, self.actor_names if self.mod_id != "ra" else None)

    def compact(self) -> dict[str, Any]:
        return {
            "mod_id": self.mod_id,
            "actor_names": self.actor_names,
            "tick": self.tick,
            "map": self.map_name,
            "mission": {
                "active": self.mission_mode,
                "briefing": self.mission_briefing,
                "objectives": [objective.as_dict() for objective in self.objectives],
            },
            "economy": {
                "cash": self.cash,
                "ore": self.ore,
                "resource_capacity": self.resource_capacity,
                "storage_percent": round(self.ore / self.resource_capacity * 100, 1) if self.resource_capacity else 0,
                "power_balance": self.power_provided - self.power_drained,
                "harvesters": self.harvester_count,
            },
            "military": {
                "army_value": self.army_value,
                "assets_value": self.assets_value,
                "units_killed": self.units_killed,
                "units_lost": self.units_lost,
                "buildings_killed": self.buildings_killed,
                "buildings_lost": self.buildings_lost,
                "kills_cost": self.kills_cost,
                "deaths_cost": self.deaths_cost,
            },
            "explored_percent": round(self.explored_percent, 1),
            "own_units": len(self.units),
            "own_unit_types": [self.actor_name(unit.kind) for unit in self.units[:16]],
            "own_buildings": [self.actor_name(building.kind) for building in self.buildings[:16]],
            "visible_enemies": [
                {"type": self.actor_name(unit.kind), "x": unit.cell_x, "y": unit.cell_y, "hp": round(unit.hp_percent, 2)}
                for unit in self.visible_enemies[:12]
            ],
            "visible_enemy_buildings": [self.actor_name(unit.kind) for unit in self.visible_enemy_buildings[:8]],
            "remembered_enemy_buildings": [
                {"type": self.actor_name(unit.kind), "x": unit.cell_x, "y": unit.cell_y, "hp_last_seen": round(unit.hp_percent, 2)}
                for unit in self.remembered_enemy_buildings[:16]
            ],
            "production": [
                {**item, "display_name": self.actor_name(str(item.get("item", "")))}
                for item in self.production[:6]
            ],
            "support_powers": [
                {
                    "key": str(power.get("key", "")),
                    "name": str(power.get("name", "")),
                    "ready": bool(power.get("ready", False)),
                    "remaining_ticks": int(power.get("remaining_ticks", 0)),
                }
                for power in self.support_powers
                if bool(power.get("active", False))
            ],
            "done": self.done,
            "reward": round(self.reward, 3),
            "result": self.result,
            "interrupt": self.interrupt_reason if self.interrupted else "",
        }

    def action_context(self) -> dict[str, Any]:
        """Return only action-relevant, fog-respecting state with stable actor ids."""
        units = sorted(self.units, key=lambda unit: (not unit.idle, unit.kind, unit.actor_id))[:48]
        buildings = sorted(self.buildings, key=lambda building: (building.hp_percent, building.kind, building.actor_id))[:32]
        return {
            "mod_id": self.mod_id,
            "actor_names": self.actor_names,
            "tick": self.tick,
            "map": {
                "name": self.map_name,
                "coordinate_space": "map_storage",
                "width": self.map_width,
                "height": self.map_height,
                "playable_bounds": [
                    self.map_bounds_x,
                    self.map_bounds_y,
                    self.map_bounds_width or self.map_width,
                    self.map_bounds_height or self.map_height,
                ],
            },
            "mission": {
                "active": self.mission_mode,
                "briefing": self.mission_briefing,
                "objectives": [objective.as_dict() for objective in self.objectives],
            },
            "economy": {
                "cash": self.cash,
                "ore": self.ore,
                "resource_capacity": self.resource_capacity,
                "storage_percent": round(self.ore / self.resource_capacity * 100, 1) if self.resource_capacity else 0,
                "power_provided": self.power_provided,
                "power_drained": self.power_drained,
                "power_balance": self.power_provided - self.power_drained,
                "harvesters": self.harvester_count,
            },
            "explored_percent": round(self.explored_percent, 1),
            "own_units": [
                {
                    "actor_id": unit.actor_id,
                    "type": unit.kind,
                    "display_name": self.actor_name(unit.kind),
                    "x": unit.cell_x,
                    "y": unit.cell_y,
                    "hp": round(unit.hp_percent, 2),
                    "idle": unit.idle,
                    "can_attack": unit.can_attack,
                    "activity": unit.current_activity,
                    "stance": unit.stance,
                    "attack_range": unit.attack_range,
                    "minimum_attack_range": unit.minimum_attack_range,
                    "armor_type": unit.armor_type,
                    "target_types": list(unit.target_types),
                    "cost": unit.cost,
                    "reload_remaining_ticks": unit.reload_remaining_ticks,
                    "reload_total_ticks": unit.reload_total_ticks,
                    "weapon": unit.weapon,
                    "burst": unit.burst,
                    "current_target_actor_id": unit.current_target_actor_id,
                    "move_target": [unit.move_target_x, unit.move_target_y],
                    "can_target_air": unit.can_target_air,
                    "can_target_ground": unit.can_target_ground,
                    "speed": unit.speed,
                    "passengers": unit.passenger_count,
                    "disguised": unit.is_disguised,
                    "disguise_owner": unit.disguise_owner,
                    "can_disguise": unit.can_disguise,
                    "can_infiltrate": unit.can_infiltrate,
                    "valid_disguise_targets": list(unit.valid_disguise_targets),
                    "valid_infiltration_targets": list(unit.valid_infiltration_targets),
                    "detects_disguise": unit.detects_disguise,
                    "can_demolish": unit.can_demolish,
                    "valid_demolition_targets": list(unit.valid_demolition_targets),
                    "can_capture": unit.can_capture,
                    "valid_capture_targets": list(unit.valid_capture_targets),
                }
                for unit in units
            ],
            "own_buildings": [
                {
                    "actor_id": building.actor_id,
                    "type": building.kind,
                    "display_name": self.actor_name(building.kind),
                    "x": building.cell_x,
                    "y": building.cell_y,
                    "hp": round(building.hp_percent, 2),
                    "powered": building.powered,
                    "repairing": building.repairing,
                    "power_amount": building.power_amount,
                    "producing": building.producing_item,
                    "production_progress": round(building.production_progress, 3),
                    "rally": [building.rally_x, building.rally_y],
                    "can_produce": list(building.can_produce),
                    "armor_type": building.armor_type,
                    "target_types": list(building.target_types),
                    "cost": building.cost,
                    "attack_range": building.attack_range,
                    "minimum_attack_range": building.minimum_attack_range,
                    "reload_remaining_ticks": building.reload_remaining_ticks,
                    "reload_total_ticks": building.reload_total_ticks,
                    "weapon": building.weapon,
                    "can_target_air": building.can_target_air,
                    "can_target_ground": building.can_target_ground,
                }
                for building in buildings
            ],
            "visible_enemies": [
                {
                    "actor_id": unit.actor_id,
                    "type": unit.kind,
                    "display_name": self.actor_name(unit.kind),
                    "x": unit.cell_x,
                    "y": unit.cell_y,
                    "hp": round(unit.hp_percent, 2),
                    "detects_disguise": unit.detects_disguise,
                    "armor_type": unit.armor_type,
                    "target_types": list(unit.target_types),
                    "cost": unit.cost,
                    "attack_range": unit.attack_range,
                    "minimum_attack_range": unit.minimum_attack_range,
                    "reload_remaining_ticks": unit.reload_remaining_ticks,
                    "reload_total_ticks": unit.reload_total_ticks,
                    "weapon": unit.weapon,
                    "burst": unit.burst,
                    "current_target_actor_id": unit.current_target_actor_id,
                    "can_target_air": unit.can_target_air,
                    "can_target_ground": unit.can_target_ground,
                    "last_seen_tick": unit.last_seen_tick,
                }
                for unit in self.visible_enemies[:24]
            ],
            "visible_enemy_buildings": [
                {
                    "actor_id": building.actor_id,
                    "type": building.kind,
                    "display_name": self.actor_name(building.kind),
                    "x": building.cell_x,
                    "y": building.cell_y,
                    "hp": round(building.hp_percent, 2),
                    "armor_type": building.armor_type,
                    "cost": building.cost,
                    "attack_range": building.attack_range,
                    "minimum_attack_range": building.minimum_attack_range,
                    "reload_remaining_ticks": building.reload_remaining_ticks,
                    "reload_total_ticks": building.reload_total_ticks,
                    "weapon": building.weapon,
                    "can_target_air": building.can_target_air,
                    "can_target_ground": building.can_target_ground,
                    "last_seen_tick": building.last_seen_tick,
                }
                for building in self.visible_enemy_buildings[:16]
            ],
            "remembered_enemy_buildings": [
                {
                    "type": building.kind,
                    "display_name": self.actor_name(building.kind),
                    "x": building.cell_x,
                    "y": building.cell_y,
                    "hp_last_seen": round(building.hp_percent, 2),
                    "last_seen_tick": building.last_seen_tick,
                }
                for building in self.remembered_enemy_buildings[:16]
            ],
            "available_production": list(self.available_production[:64]),
            "available_production_names": [
                {"id": item, "name": self.actor_name(item)}
                for item in self.available_production[:64]
            ],
            "production": [
                {**item, "display_name": self.actor_name(str(item.get("item", "")))}
                for item in self.production[:12]
            ],
            "support_powers": [dict(power) for power in self.support_powers],
            "military": {
                "army_value": self.army_value,
                "assets_value": self.assets_value,
                "units_killed": self.units_killed,
                "units_lost": self.units_lost,
                "buildings_killed": self.buildings_killed,
                "buildings_lost": self.buildings_lost,
                "kills_cost": self.kills_cost,
                "deaths_cost": self.deaths_cost,
                "orders": self.order_count,
            },
            "done": self.done,
            "result": self.result,
            "interrupt": self.interrupt_reason if self.interrupted else "",
        }


@dataclass(frozen=True)
class ActionCommand:
    action: str
    actor_id: int = 0
    target_actor_id: int = 0
    target_x: int = 0
    target_y: int = 0
    item_type: str = ""
    queued: bool = False
    ticks: int = 0

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ActionCommand":
        action = str(value.get("action", "")).strip().lower()
        if action not in SAFE_ACTIONS:
            raise ValueError(f"action '{action}' is not allowed")
        return cls(
            action=action,
            actor_id=int(value.get("actor_id", 0)),
            target_actor_id=int(value.get("target_actor_id", 0)),
            target_x=int(value.get("target_x", 0)),
            target_y=int(value.get("target_y", 0)),
            item_type=str(value.get("item_type", "")).strip().lower(),
            queued=bool(value.get("queued", False)),
            ticks=int(value.get("ticks", 0)),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionProposal:
    proposal_id: str
    instruction: str
    summary: str
    expected_tick: int
    commands: tuple[ActionCommand, ...]
    created_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "instruction": self.instruction,
            "summary": self.summary,
            "expected_tick": self.expected_tick,
            "commands": [command.as_dict() for command in self.commands],
        }


@dataclass(frozen=True)
class ActionReceipt:
    request_id: str
    accepted: bool
    game_tick: int
    detail: str
    results: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ActionReceipt":
        return cls(
            request_id=str(value.get("request_id", "")),
            accepted=bool(value.get("accepted", False)),
            game_tick=int(value.get("game_tick", 0)),
            detail=str(value.get("detail", "")),
            results=tuple(dict(result) for result in value.get("results", [])),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "accepted": self.accepted,
            "game_tick": self.game_tick,
            "detail": self.detail,
            "results": list(self.results),
        }


@dataclass(frozen=True)
class ThreatAssessment:
    score: int = 0
    level: str = "calm"
    reason: str = "No immediate visible threat"

    @property
    def heated(self) -> bool:
        return self.level in {"high", "critical"}

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VisionFrame:
    png: bytes
    tick: int
    width: int
    height: int
    scope: str = "rendered-player-viewport-fog-respecting"

    def metadata(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "width": self.width,
            "height": self.height,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class Insight:
    key: str
    score: int
    fact: str
    fallback_text: str
    tick: int
    importance: str = "routine"

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
