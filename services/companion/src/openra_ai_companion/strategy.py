from __future__ import annotations

import math
import struct
from heapq import heappop, heappush
from collections import Counter, deque
from typing import Any

from .models import GameSnapshot, Unit
from .labels import building_name, unit_name
from .mission_goals import compile_mission_goal_graph


FACTION_DOCTRINES: dict[str, dict[str, Any]] = {
    "england": {
        "side": "allies",
        "identity": "counterintelligence",
        "signature_units": ["spy", "mgg"],
        "priorities": ["early vision", "British Spies", "Mobile Gap Generators", "mobile combined arms"],
        "base_guidance": "Preserve open lanes for mobile armor and stage the Mobile Gap Generator behind the main force.",
    },
    "france": {
        "side": "allies",
        "identity": "deception",
        "signature_units": ["pt"],
        "priorities": ["map control", "fake structures", "Phase Transports", "mobile combined arms"],
        "base_guidance": "Keep naval access clear when water is reachable; use fake structures only after the real economy is safe.",
    },
    "germany": {
        "side": "allies",
        "identity": "chronoshift mobility",
        "signature_units": ["ctnk"],
        "priorities": ["map control", "advanced Chronoshift", "Chrono Tanks", "mobile combined arms"],
        "base_guidance": "Favor a spacious vehicle staging area so Chrono Tanks and conventional armor can mass without blocking production.",
    },
    "russia": {
        "side": "soviet",
        "identity": "tesla weapons",
        "signature_units": ["ttnk", "shok"],
        "priorities": ["Grenadier screen against early infantry", "power headroom", "Tesla Tanks", "Shock Troopers", "armored pressure"],
        "base_guidance": "Reserve extra power headroom and keep staging lanes clear. Radar Dome unlocks V2 siege; Service Depot unlocks Heavy Tanks; Airfield does not unlock armor.",
    },
    "ukraine": {
        "side": "soviet",
        "identity": "demolitions",
        "signature_units": ["dtrk"],
        "priorities": ["airfield timing", "Parabombs", "Demolition Trucks", "armored pressure"],
        "base_guidance": "Leave wide vehicle lanes for Demolition Trucks. Radar Dome unlocks V2 siege; Service Depot unlocks Heavy Tanks; Airfield unlocks aircraft only.",
    },
}


MAP_DOCTRINES: dict[str, dict[str, Any]] = {
    "small": {
        "harvesters": 2,
        "scouts": 2,
        "base_shape": "compact with one clear production avenue",
        "tempo": "expect early contact; defend the first refinery and pressure after the first armor group",
    },
    "medium": {
        "harvesters": 3,
        "scouts": 3,
        "base_shape": "two production lanes with economy on the ore-facing edge",
        "tempo": "secure nearby ore, reveal three approaches, then establish combined-arms map control",
    },
    "large": {
        "harvesters": 4,
        "scouts": 4,
        "base_shape": "distributed economy and production with room for a forward expansion",
        "tempo": "prioritize vision, mobility, a second income line, and forward staging before a decisive attack",
    },
    "huge": {
        "harvesters": 5,
        "scouts": 4,
        "base_shape": "multiple separated production and economy clusters linked by open routes",
        "tempo": "expand deliberately, maintain mobile reserves, and scout repeatedly as fronts move",
    },
}


def map_scale(width: int, height: int) -> str:
    area = max(0, width) * max(0, height)
    if area <= 4_096:
        return "small"
    if area <= 9_216:
        return "medium"
    if area <= 16_384:
        return "large"
    return "huge"


def opening_scout_count(snapshot: GameSnapshot) -> int:
    return MAP_DOCTRINES[map_scale(snapshot.map_width, snapshot.map_height)]["scouts"]


def desired_harvester_count(snapshot: GameSnapshot) -> int:
    return MAP_DOCTRINES[map_scale(snapshot.map_width, snapshot.map_height)]["harvesters"]


def maximum_silo_count(snapshot: GameSnapshot) -> int:
    """Bound passive storage so surplus income is converted into map control."""
    return desired_harvester_count(snapshot)


# These are the relative production shares shipped by OpenRA's Red Alert
# UnitBuilderBotModule (the medium/normal profiles), with the same hard caps for
# specialist units.  The local commander uses the engine's proven
# under-representation rule, then adds fog-respecting counter weights.
OPENRA_COMBAT_WEIGHTS: dict[str, int] = {
    "e1": 55,
    "e2": 15,
    "e3": 25,
    "e4": 10,
    "e7": 1,
    "dog": 10,
    "shok": 15,
    "apc": 20,
    "jeep": 15,
    "arty": 10,
    "v2rl": 25,
    "ftrk": 20,
    "1tnk": 35,
    "2tnk": 40,
    "3tnk": 40,
    "4tnk": 15,
    "ttnk": 25,
    "stnk": 5,
    "ctnk": 20,
    "yak": 30,
    "mig": 30,
    "heli": 30,
    "mh60": 30,
    "hind": 30,
    "ss": 10,
    "msub": 10,
    "dd": 10,
    "ca": 10,
    "pt": 10,
}

OPENRA_COMBAT_LIMITS: dict[str, int] = {
    "e7": 1,
    "dog": 4,
    "jeep": 4,
    "ftrk": 4,
    "4tnk": 2,
    "arty": 3,
    "v2rl": 3,
}

UNIT_CATEGORIES: dict[str, frozenset[str]] = {
    "infantry": frozenset({"e1", "e2", "e3", "e4", "e7", "dog", "shok"}),
    "vehicle": frozenset({
        "apc", "jeep", "arty", "v2rl", "ftrk", "1tnk", "2tnk", "3tnk", "4tnk", "ttnk", "stnk", "ctnk",
    }),
    "aircraft": frozenset({"yak", "mig", "heli", "mh60", "hind"}),
    "naval": frozenset({"ss", "msub", "dd", "ca", "pt"}),
}


def _unit_category(kind: str) -> str:
    for category, kinds in UNIT_CATEGORIES.items():
        if kind in kinds:
            return category
    return ""


def _combat_counts(snapshot: GameSnapshot) -> Counter[str]:
    counts = Counter(
        _actor_type(unit)
        for unit in snapshot.units
        if ".husk" not in unit.kind.lower() and unit.hp_percent > 0 and _unit_category(_actor_type(unit))
    )
    counts.update(
        str(item.get("item", "")).lower().split(".", 1)[0]
        for item in snapshot.production
        if _unit_category(str(item.get("item", "")).lower().split(".", 1)[0])
    )
    return counts


def _enemy_composition(snapshot: GameSnapshot) -> dict[str, int]:
    infantry = {"e1", "e2", "e3", "e4", "e7", "dog", "shok", "spy", "engi", "medi", "mech"}
    armor = {"apc", "jeep", "ftrk", "1tnk", "2tnk", "3tnk", "4tnk", "ttnk", "stnk", "ctnk", "harv"}
    aircraft = UNIT_CATEGORIES["aircraft"] | {"tran", "badr", "u2"}
    kinds = [_actor_type(unit) for unit in snapshot.visible_enemies]
    return {
        "infantry": sum(kind in infantry for kind in kinds),
        "armor": sum(kind in armor for kind in kinds),
        "aircraft": sum(kind in aircraft for kind in kinds),
        "structures": len(snapshot.visible_enemy_buildings),
    }


def _counter_weight(kind: str, base_weight: int, enemy: dict[str, int]) -> int:
    """Bias OpenRA's base mix only from current fog-respecting contacts."""
    weight = base_weight
    if enemy["infantry"] > enemy["armor"]:
        if kind in {"e2", "e4", "jeep", "yak", "arty"}:
            weight += 30
    if enemy["armor"] > enemy["infantry"]:
        if kind in {"e3", "shok", "2tnk", "3tnk", "4tnk", "ttnk"}:
            weight += 35
    if enemy["aircraft"]:
        if kind in {"e3", "ftrk", "4tnk", "mig"}:
            weight += 60
    if enemy["structures"]:
        if kind in {"arty", "v2rl"}:
            weight += 25
    return max(1, weight)


def hybrid_force_plan(snapshot: GameSnapshot, batch_size: int = 3) -> dict[str, Any]:
    """Blend OpenRA's production/squad heuristics with local counter intelligence.

    OpenRA chooses units that are most under-represented against configured
    relative shares, rotates free queues, applies specialist limits, and waits
    for a squad threshold before attacking.  This deterministic variant also
    reacts to only the enemy contacts visible in the supplied snapshot.
    """
    available_by_kind = {
        item.lower().split(".", 1)[0]: item.lower()
        for item in snapshot.available_production
        if item.lower().split(".", 1)[0] in OPENRA_COMBAT_WEIGHTS
        and not item.lower().endswith("f")
    }
    counts = _combat_counts(snapshot)
    observed_counts = counts.copy()
    enemy = _enemy_composition(snapshot)
    adjusted_weights = {
        kind: _counter_weight(kind, OPENRA_COMBAT_WEIGHTS[kind], enemy)
        for kind in available_by_kind
    }
    busy_categories = {
        str(item.get("queue_type", "")).lower()
        for item in snapshot.production
        if str(item.get("queue_type", "")).lower() in UNIT_CATEGORIES
    }
    # Some bridge versions omit queue_type. Infer it from the queued item.
    busy_categories.update(
        _unit_category(str(item.get("item", "")).lower().split(".", 1)[0])
        for item in snapshot.production
        if _unit_category(str(item.get("item", "")).lower().split(".", 1)[0])
    )

    def eligible(category: str, used_in_batch: set[str]) -> list[str]:
        choices = []
        building_counts = Counter(_actor_type(building) for building in snapshot.buildings)
        airfield_capacity = building_counts["afld"] + building_counts["afld.ukraine"]
        helipad_capacity = building_counts["hpad"]
        for kind in UNIT_CATEGORIES[category]:
            if kind not in available_by_kind:
                continue
            limit = OPENRA_COMBAT_LIMITS.get(kind)
            if limit is not None and counts[kind] >= limit:
                continue
            # Match OpenRA's HasAdequateAirUnitReloadBuildings guard: each
            # aircraft must have a rearm building instead of piling aircraft
            # onto one unusable pad.
            if kind in {"yak", "mig"} and counts["yak"] + counts["mig"] >= airfield_capacity:
                continue
            if kind in {"heli", "mh60", "hind"} and counts["heli"] + counts["mh60"] + counts["hind"] >= helipad_capacity:
                continue
            choices.append(kind)
        unused = [kind for kind in choices if kind not in used_in_batch]
        return unused or choices

    commands: list[dict[str, Any]] = []
    selected: list[str] = []
    used_in_batch: set[str] = set()
    # Fill independent production queues like OpenRA. Two infantry slots are
    # allowed, but a second type is preferred so one overflow event cannot make
    # another monoculture batch.
    pattern = ("vehicle", "infantry", "infantry", "aircraft", "naval")
    if batch_size == 1:
        category_priority = {"vehicle": 0, "infantry": 1, "aircraft": 2, "naval": 3}
        free_categories = [category for category in UNIT_CATEGORIES if category not in busy_categories]
        ranked_categories = []
        for category in free_categories:
            choices = eligible(category, used_in_batch)
            if choices:
                best = min(counts[kind] / adjusted_weights[kind] for kind in choices)
                ranked_categories.append((best, category_priority[category], category))
        pattern = tuple(category for _, _, category in sorted(ranked_categories))
    for category in pattern:
        if len(commands) >= max(0, batch_size) or category in busy_categories:
            continue
        choices = eligible(category, used_in_batch)
        if not choices:
            continue
        kind = min(
            choices,
            key=lambda candidate: (
                counts[candidate] / adjusted_weights[candidate],
                -adjusted_weights[candidate],
                candidate,
            ),
        )
        commands.append({"action": "train", "item_type": available_by_kind[kind]})
        selected.append(kind)
        used_in_batch.add(kind)
        counts[kind] += 1

    scale = map_scale(snapshot.map_width, snapshot.map_height)
    squad_size = {"small": 6, "medium": 8, "large": 10, "huge": 12}[scale]
    reserve_size = {"small": 2, "medium": 3, "large": 4, "huge": 5}[scale]
    excluded = {"harv", "mcv", "dog", "spy", "engi", "medi", "mech", "badr", "u2"}
    idle_ground = [
        unit for unit in snapshot.units
        if unit.idle and unit.can_attack and _actor_type(unit) not in excluded
        and _unit_category(_actor_type(unit)) in {"infantry", "vehicle"}
    ]
    role_counts = Counter(
        "siege" if _actor_type(unit) in {"arty", "v2rl"}
        else "armor" if _actor_type(unit) in UNIT_CATEGORIES["vehicle"]
        else "screen"
        for unit in idle_ground
    )
    attack_ready = len(idle_ground) >= squad_size + reserve_size and len(role_counts) >= 2

    target_priority = {
        "weap": 0,
        "barr": 1,
        "tent": 1,
        "fact": 2,
        "proc": 3,
        "afld": 4,
        "hpad": 4,
        "powr": 5,
        "apwr": 5,
    }
    building_targets = [*snapshot.visible_enemy_buildings, *snapshot.remembered_enemy_buildings]
    target_actor = min(
        building_targets,
        key=lambda actor: (target_priority.get(_actor_type(actor), 10), actor.hp_percent, actor.actor_id),
        default=None,
    )
    if target_actor is None and snapshot.visible_enemies:
        home = base_center(snapshot)
        target_actor = min(
            snapshot.visible_enemies,
            key=lambda actor: (actor.cell_x - home[0]) ** 2 + (actor.cell_y - home[1]) ** 2,
        )

    assault_commands: list[dict[str, Any]] = []
    assault_target: list[int] | None = None
    if attack_ready and target_actor is not None:
        screens = sorted(
            (unit for unit in idle_ground if _unit_category(_actor_type(unit)) == "infantry"),
            key=lambda unit: (-unit.hp_percent, unit.actor_id),
        )
        armor = sorted(
            (
                unit for unit in idle_ground
                if _unit_category(_actor_type(unit)) == "vehicle" and _actor_type(unit) not in {"arty", "v2rl"}
            ),
            key=lambda unit: (-unit.hp_percent, unit.actor_id),
        )
        siege = sorted(
            (unit for unit in idle_ground if _actor_type(unit) in {"arty", "v2rl"}),
            key=lambda unit: (-unit.hp_percent, unit.actor_id),
        )
        group_limit = min(12, len(idle_ground) - reserve_size)
        siege_quota = min(2, len(siege), group_limit)
        armor_quota = min(4, len(armor), group_limit - siege_quota)
        screen_quota = min(6, len(screens), group_limit - siege_quota - armor_quota)
        selected_units = [*screens[:screen_quota], *armor[:armor_quota], *siege[:siege_quota]]
        if len(selected_units) < squad_size:
            selected_ids = {unit.actor_id for unit in selected_units}
            selected_units.extend(
                unit for unit in idle_ground
                if unit.actor_id not in selected_ids
            )
        selected_units = selected_units[:group_limit]
        target = (target_actor.cell_x, target_actor.cell_y)
        assault_target = list(target)
        home = base_center(snapshot)
        dx = target[0] - home[0]
        dy = target[1] - home[1]
        distance = max(1.0, math.hypot(dx, dy))
        siege_staging = _nearby_passable(snapshot, (
            round(target[0] - dx / distance * 9),
            round(target[1] - dy / distance * 9),
        ))
        assault_commands = [
            {
                "action": "attack_move",
                "actor_id": unit.actor_id,
                "target_x": siege_staging[0] if _actor_type(unit) in {"arty", "v2rl"} else target[0],
                "target_y": siege_staging[1] if _actor_type(unit) in {"arty", "v2rl"} else target[1],
            }
            for unit in selected_units
        ]

    recon_commands: list[dict[str, Any]] = []
    if target_actor is None and snapshot.explored_percent < 90:
        recon_units = sorted(
            (
                unit for unit in snapshot.units
                if unit.idle and _actor_type(unit) in {"e1", "jeep", "dog", "e2"}
            ),
            key=lambda unit: (
                {"e1": 0, "jeep": 1, "dog": 2, "e2": 3}[_actor_type(unit)],
                -unit.hp_percent,
                unit.actor_id,
            ),
        )[:3]
        targets = scout_targets(snapshot, base_center(snapshot), len(recon_units))
        recon_commands = [
            {
                "action": "attack_move",
                "actor_id": unit.actor_id,
                "target_x": target[0],
                "target_y": target[1],
            }
            for unit, target in zip(recon_units, targets)
        ]
    return {
        "source": "OpenRA UnitBuilderBotModule and SquadManagerBotModule hybrid",
        "selection_rule": "produce the available type most under-represented against its weighted share",
        "visible_enemy_composition": enemy,
        "current_and_queued_composition": dict(sorted(observed_counts.items())),
        "adjusted_available_weights": dict(sorted(adjusted_weights.items())),
        "next_production": commands,
        "next_production_types": selected,
        "queue_policy": "rotate free infantry, vehicle, aircraft, and naval queues; do not stack a busy queue",
        "squad": {
            "idle_eligible_units": len(idle_ground),
            "roles": dict(role_counts),
            "attack_threshold": squad_size,
            "defense_reserve": reserve_size,
            "attack_ready": attack_ready,
            "rules": [
                "keep the defense reserve near harvesters and production",
                "attack as a mixed group rather than feeding new units individually",
                "reassess local strength and flee or fall back when the visible enemy is stronger",
            ],
        },
        "recon": {
            "needed": target_actor is None and snapshot.explored_percent < 90,
            "commands": recon_commands,
            "rule": "fan cheap idle scouts toward distinct reachable hidden regions until an enemy position is known",
        },
        "assault": {
            "target": assault_target,
            "commands": assault_commands,
            "rule": "send a mixed squad together; keep siege at the nine-cell staging line and retain the defense reserve",
        },
    }


def strategic_profile(snapshot: GameSnapshot, state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = state or {}
    faction = str(state.get("player_faction", "")).lower()
    doctrine = FACTION_DOCTRINES.get(faction, {
        "side": "unknown",
        "identity": "adaptive combined arms",
        "signature_units": [],
        "priorities": ["economy", "vision", "production", "counter the visible enemy"],
        "base_guidance": "Keep ore traffic and production exits clear, then adapt to visible enemy composition.",
    })
    scale = map_scale(snapshot.map_width, snapshot.map_height)
    map_doctrine = MAP_DOCTRINES[scale]
    return {
        "player_faction": faction or "unknown",
        "enemy_faction": str(state.get("enemy_faction", "unknown")).lower(),
        "map_scale": scale,
        "map_cells": snapshot.map_width * snapshot.map_height,
        "opening_scouts": opening_scout_count(snapshot),
        "target_harvesters": desired_harvester_count(snapshot),
        "maximum_silos": maximum_silo_count(snapshot),
        "opening_order": [
            "deploy Construction Yard",
            "power",
            "barracks",
            "train and fan out Rifle Infantry scouts",
            "refinery close to explored ore",
            "war factory with a clear vehicle exit",
        ],
        "placement_policy": [
            "omit coordinates when placing structures so the engine placement optimizer can score legal sites",
            "put refineries near explored dense resources",
            "reserve a three-cell-wide production lane beyond barracks and war-factory doors",
            "keep service space between structures and point rally paths away from base congestion",
        ],
        "doctrine": doctrine,
        "map_doctrine": map_doctrine,
    }


def _actor_type(actor: Unit) -> str:
    return actor.kind.lower().split("@", 1)[0].split(".", 1)[0]


def _is_wall(actor: Unit) -> bool:
    return _actor_type(actor) in {"barb", "brik", "cycl", "fenc", "sbag", "wood"}


def _live(actors: tuple[Unit, ...]) -> list[Unit]:
    return [actor for actor in actors if ".husk" not in actor.kind.lower() and actor.hp_percent > 0]


def _mean_cell(actors: list[Unit], fallback: tuple[int, int]) -> tuple[int, int]:
    if not actors:
        return fallback
    return (
        round(sum(actor.cell_x for actor in actors) / len(actors)),
        round(sum(actor.cell_y for actor in actors) / len(actors)),
    )


def _nearby_passable(snapshot: GameSnapshot, desired: tuple[int, int]) -> tuple[int, int]:
    x = min(max(desired[0], 0), max(0, snapshot.map_width - 1))
    y = min(max(desired[1], 0), max(0, snapshot.map_height - 1))
    if not _valid_spatial(snapshot):
        return x, y
    candidates = [
        (cx, cy)
        for radius in range(0, 7)
        for cy in range(max(0, y - radius), min(snapshot.map_height, y + radius + 1))
        for cx in range(max(0, x - radius), min(snapshot.map_width, x + radius + 1))
        if _spatial_value(snapshot, cx, cy, 3) > 0 and _spatial_value(snapshot, cx, cy, 4) > 0
    ]
    return min(candidates, key=lambda cell: ((cell[0] - x) ** 2 + (cell[1] - y) ** 2, cell)) if candidates else (x, y)


def tactical_plan(snapshot: GameSnapshot) -> dict[str, Any]:
    """Return deterministic micro constraints and formation anchors from visible state only."""
    own = _live(snapshot.units)
    enemies = _live(snapshot.visible_enemies)
    tanks = [unit for unit in own if _actor_type(unit) in {"1tnk", "2tnk", "3tnk", "4tnk", "ctnk", "ttnk"}]
    siege = [unit for unit in own if _actor_type(unit) in {"v2rl", "arty"}]
    screen = [unit for unit in own if _actor_type(unit) in {"e1", "e2", "e3", "e4", "shok", "jeep"}]
    spies = [unit for unit in own if _actor_type(unit) == "spy"]
    dogs = [unit for unit in enemies if _actor_type(unit) == "dog"]
    depot = next((building for building in snapshot.buildings if _actor_type(building) == "fix"), None)
    home = (depot.cell_x, depot.cell_y) if depot is not None else base_center(snapshot)
    frontline = _mean_cell(tanks or screen, home)
    enemy_center = _mean_cell(enemies, frontline)
    direction_x = enemy_center[0] - frontline[0]
    direction_y = enemy_center[1] - frontline[1]
    length = max(1.0, math.hypot(direction_x, direction_y))
    siege_anchor = _nearby_passable(snapshot, (
        round(frontline[0] - direction_x / length * 5),
        round(frontline[1] - direction_y / length * 5),
    ))
    screen_anchor = _nearby_passable(snapshot, (
        round(frontline[0] + direction_x / length * 2),
        round(frontline[1] + direction_y / length * 2),
    ))

    siege_threats = []
    for unit in siege:
        close = sorted(
            (
                (math.hypot(enemy.cell_x - unit.cell_x, enemy.cell_y - unit.cell_y), enemy)
                for enemy in enemies
            ),
            key=lambda pair: pair[0],
        )
        if close and close[0][0] <= 8:
            distance, enemy = close[0]
            siege_threats.append({
                "siege_actor_id": unit.actor_id,
                "threat_actor_id": enemy.actor_id,
                "threat_type": _actor_type(enemy),
                "distance_cells": round(distance, 1),
                "retreat_to": list(siege_anchor),
            })

    spy_escapes = []
    for spy in spies:
        nearby_dogs = [
            dog for dog in dogs
            if math.hypot(dog.cell_x - spy.cell_x, dog.cell_y - spy.cell_y) <= 12
        ]
        if nearby_dogs:
            spy_escapes.append({
                "spy_actor_id": spy.actor_id,
                "dog_actor_ids": [dog.actor_id for dog in nearby_dogs],
                "immediate_move_to": list(_nearby_passable(snapshot, home)),
                "rule": "flee immediately; do not infiltrate until every nearby dog is dead or out of vision",
            })

    damaged_armor = [
        {
            "actor_id": unit.actor_id,
            "type": _actor_type(unit),
            "hp_percent": round(unit.hp_percent * 100, 1),
            "retreat_to": list(home),
        }
        for unit in (*tanks, *siege)
        if unit.hp_percent < 0.35
    ]
    anti_armor = [
        enemy.actor_id for enemy in enemies
        if _actor_type(enemy) in {"e3", "shok", "1tnk", "2tnk", "3tnk", "4tnk", "ttnk", "ctnk"}
    ]
    anti_siege = [
        enemy.actor_id for enemy in enemies
        if any(math.hypot(enemy.cell_x - unit.cell_x, enemy.cell_y - unit.cell_y) <= 10 for unit in siege)
    ]
    tank_center = _mean_cell(tanks, home)
    tank_spacing = {
        unit.actor_id: round(math.hypot(unit.cell_x - tank_center[0], unit.cell_y - tank_center[1]), 1)
        for unit in tanks
    }
    tank_stragglers = [actor_id for actor_id, distance in tank_spacing.items() if distance > 6]

    def range_cells(unit: Unit) -> float:
        return round(max(0, unit.attack_range) / 1024, 1)

    enemy_firing_zones = [
        {
            "actor_id": enemy.actor_id,
            "type": _actor_type(enemy),
            "center": [enemy.cell_x, enemy.cell_y],
            "range_cells": range_cells(enemy),
            "facing": enemy.facing,
        }
        for enemy in enemies
        if enemy.can_attack and enemy.attack_range > 0
    ]
    range_edges = []
    for tank in tanks:
        if not enemies or tank.attack_range <= 0:
            continue
        enemy = min(enemies, key=lambda actor: (actor.cell_x - tank.cell_x) ** 2 + (actor.cell_y - tank.cell_y) ** 2)
        distance = math.hypot(tank.cell_x - enemy.cell_x, tank.cell_y - enemy.cell_y)
        enemy_range = max(0.0, enemy.attack_range / 1024)
        own_range = max(0.0, tank.attack_range / 1024)
        dx = tank.cell_x - enemy.cell_x
        dy = tank.cell_y - enemy.cell_y
        length_to_enemy = max(1.0, math.hypot(dx, dy))
        desired_distance = enemy_range + 1 if own_range > enemy_range else max(enemy_range + 1, own_range)
        hold = _nearby_passable(snapshot, (
            round(enemy.cell_x + dx / length_to_enemy * desired_distance),
            round(enemy.cell_y + dy / length_to_enemy * desired_distance),
        ))
        range_edges.append({
            "tank_actor_id": tank.actor_id,
            "enemy_actor_id": enemy.actor_id,
            "distance_cells": round(distance, 1),
            "own_range_cells": round(own_range, 1),
            "enemy_range_cells": round(enemy_range, 1),
            "can_outrange": own_range > enemy_range,
            "standoff_or_safe_hold": list(hold),
        })

    heavy_types = {"2tnk", "3tnk", "4tnk", "ttnk", "ctnk"}
    light_types = {"1tnk", "jeep", "apc", "ftrk", "v2rl", "arty", "harv"}
    air_types = {"yak", "mig", "heli", "hind", "tran", "badr", "u2"}

    def armor_groups(actors: list[Unit]) -> dict[str, list[int]]:
        return {
            "heavy": [actor.actor_id for actor in actors if _actor_type(actor) in heavy_types],
            "light": [actor.actor_id for actor in actors if _actor_type(actor) in light_types],
            "air": [actor.actor_id for actor in actors if _actor_type(actor) in air_types],
            "unarmored": [
                actor.actor_id for actor in actors
                if _actor_type(actor) not in heavy_types | light_types | air_types
            ],
        }

    defense_ranges = {"tsla": 8, "ftur": 4, "pbox": 5, "gun": 6, "sam": 8, "agun": 8}
    defenses = [
        building for building in snapshot.buildings
        if _actor_type(building) in defense_ranges and building.powered
    ]
    defensive_lure: dict[str, Any] = {"available": False, "defenses": []}
    if defenses:
        defense = min(defenses, key=lambda actor: (actor.cell_x - enemy_center[0]) ** 2 + (actor.cell_y - enemy_center[1]) ** 2)
        dx = enemy_center[0] - defense.cell_x
        dy = enemy_center[1] - defense.cell_y
        defense_to_enemy = max(1.0, math.hypot(dx, dy))
        fallback = _nearby_passable(snapshot, (
            round(defense.cell_x - dx / defense_to_enemy * 2),
            round(defense.cell_y - dy / defense_to_enemy * 2),
        ))
        defensive_lure = {
            "available": bool(enemies),
            "defenses": [
                {
                    "actor_id": building.actor_id,
                    "type": _actor_type(building),
                    "cell": [building.cell_x, building.cell_y],
                    "range_cells": defense_ranges[_actor_type(building)],
                }
                for building in defenses
            ],
            "fallback_anchor_behind_defense": list(fallback),
            "rule": "fall back behind powered defense coverage and force pursuers to enter its range before counterattacking",
        }

    aircraft = [enemy for enemy in enemies if _actor_type(enemy) in air_types]
    anti_air_types = {"e3", "ftrk", "4tnk", "sam", "agun"}
    anti_air_actors = [
        actor.actor_id for actor in (*snapshot.units, *snapshot.buildings)
        if _actor_type(actor) in anti_air_types and ".husk" not in actor.kind.lower()
    ]
    anti_air_production = [
        item for item in snapshot.available_production
        if item.lower().split(".", 1)[0] in anti_air_types
    ]
    return {
        "formation": {
            "frontline_anchor": list(frontline),
            "screen_anchor": list(screen_anchor),
            "siege_anchor": list(siege_anchor),
            "minimum_siege_standoff_cells": 4,
            "live_counts": {"tanks": len(tanks), "screen": len(screen), "siege": len(siege)},
            "tank_cohesion": {
                "center": list(tank_center),
                "status": "tight" if not tank_stragglers else "dispersed",
                "straggler_actor_ids": tank_stragglers,
                "maximum_spacing_cells": max(tank_spacing.values(), default=0),
            },
        },
        "immediate_safety": {
            "spy_dog_escapes": spy_escapes,
            "damaged_armor_retreats": damaged_armor,
            "siege_threats": siege_threats,
        },
        "focus_priorities": {
            "anti_armor_enemy_ids": anti_armor,
            "enemies_threatening_siege_ids": anti_siege,
            "dog_ids_when_spy_active": [dog.actor_id for dog in dogs] if spies else [],
        },
        "range_control": {
            "enemy_firing_zones": enemy_firing_zones,
            "tank_engagement_edges": range_edges,
            "rule": "keep the tank group outside hostile range until the screen/counter is ready; exploit longer range from the supplied standoff anchor",
        },
        "armor_assessment": {
            "own": armor_groups(own),
            "visible_enemy": armor_groups(enemies),
            "counter_rules": [
                "use rockets and durable tanks against heavy armor",
                "use Grenadiers/flame/splash against unarmored infantry",
                "do not expose light siege or transports to direct tank fire",
            ],
        },
        "defensive_lure": defensive_lure,
        "air_response": {
            "visible_aircraft_ids": [aircraft_unit.actor_id for aircraft_unit in aircraft],
            "ready_anti_air_actor_ids": anti_air_actors,
            "available_counter_production": anti_air_production,
            "action": (
                "focus aircraft with ready anti-air and queue an available counter immediately"
                if aircraft else "no visible aircraft"
            ),
        },
        "micro_rules": [
            "keep spies outside a 12-cell dog danger radius and behind the friendly screen",
            "keep V2/artillery 4-6 cells behind the tank and anti-infantry screen",
            "focus anti-armor infantry before tanks enter its firing pocket",
            "retreat armor/siege below 35% health to the Service Depot or base anchor",
            "never count husks as live formation strength",
            "keep tanks within six cells of the tank-group center unless explicitly flanking",
            "use powered Tesla/Flame/Pillbox/Turret coverage as a fallback trap when outnumbered",
            "answer aircraft with Rocket Soldiers, Mobile Flak, Mammoth missiles, SAM, or AA Guns according to availability",
        ],
    }


def _spatial_value(snapshot: GameSnapshot, x: int, y: int, channel: int) -> float:
    offset = ((y * snapshot.map_width + x) * snapshot.spatial_channels + channel) * 4
    return struct.unpack_from("<f", snapshot.spatial_map, offset)[0]


def _valid_spatial(snapshot: GameSnapshot) -> bool:
    expected = snapshot.map_width * snapshot.map_height * snapshot.spatial_channels * 4
    return (
        snapshot.map_width > 0
        and snapshot.map_height > 0
        and snapshot.spatial_channels >= 9
        and len(snapshot.spatial_map) == expected
    )


def _stealth_route(
    snapshot: GameSnapshot,
    origin: tuple[int, int],
    target: tuple[int, int],
    dogs: list[Unit],
) -> list[tuple[int, int]]:
    """Find a route that keeps the spy clear of the current dog patrol positions."""
    if not _valid_spatial(snapshot):
        return []

    def inside(cell: tuple[int, int]) -> bool:
        x, y = cell
        return snapshot.contains_cell(x, y)

    def danger(cell: tuple[int, int]) -> float:
        x, y = cell
        if not dogs:
            return 0
        distance = min(math.hypot(x - dog.cell_x, y - dog.cell_y) for dog in dogs)
        # Dogs are faster than spies, so pathing just outside their melee reach is
        # not safe. Keep a hard eight-cell bubble and strongly prefer twelve cells.
        # The route is only consumed a few cells at a time and recalculated after
        # each order, because patrol positions can change while the spy is moving.
        if distance <= 8 and cell != origin:
            return math.inf
        return max(0.0, 12.0 - distance) * 24.0

    def passable(cell: tuple[int, int]) -> bool:
        if not inside(cell):
            return False
        x, y = cell
        explored = _spatial_value(snapshot, x, y, 4) > 0
        # Unknown fog is legal to explore, but do not read its hidden terrain
        # value. Treat it as provisional ground and let OpenRA's pathfinder
        # resolve the actual route when the waypoint order is issued.
        if explored and _spatial_value(snapshot, x, y, 3) <= 0:
            return False
        if cell != origin and (_spatial_value(snapshot, x, y, 5) > 0 or _spatial_value(snapshot, x, y, 7) > 0):
            return False
        return not math.isinf(danger(cell))

    goals = {
        (x, y)
        for radius in range(1, 5)
        for y in range(target[1] - radius, target[1] + radius + 1)
        for x in range(target[0] - radius, target[0] + radius + 1)
        if max(abs(x - target[0]), abs(y - target[1])) == radius and passable((x, y))
    }
    if not goals or not inside(origin):
        return []

    frontier: list[tuple[float, float, tuple[int, int]]] = []
    heappush(frontier, (0.0, 0.0, origin))
    cost = {origin: 0.0}
    previous: dict[tuple[int, int], tuple[int, int]] = {}
    reached: tuple[int, int] | None = None
    while frontier:
        _, current_cost, current = heappop(frontier)
        if current_cost != cost.get(current):
            continue
        if current in goals:
            reached = current
            break
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (current[0] + dx, current[1] + dy)
            if not passable(neighbor):
                continue
            candidate = current_cost + 1.0 + danger(neighbor)
            if candidate >= cost.get(neighbor, math.inf):
                continue
            cost[neighbor] = candidate
            previous[neighbor] = current
            heuristic = min(abs(neighbor[0] - goal[0]) + abs(neighbor[1] - goal[1]) for goal in goals)
            heappush(frontier, (candidate + heuristic, candidate, neighbor))

    if reached is None:
        return []
    path = [reached]
    while path[-1] != origin:
        path.append(previous[path[-1]])
    path.reverse()
    return path


def mission_plan(snapshot: GameSnapshot) -> dict[str, Any]:
    """Translate scripted objectives and special-unit capabilities into a concrete next step."""
    if not snapshot.mission_mode:
        return {"active": False}

    incomplete = [objective for objective in snapshot.objectives if objective.state == "incomplete"]
    spies = [unit for unit in _live(snapshot.units) if unit.can_disguise or unit.can_infiltrate or _actor_type(unit) == "spy"]
    dogs = [unit for unit in _live(snapshot.visible_enemies) if unit.detects_disguise or _actor_type(unit) == "dog"]
    actor_lookup = {
        actor.actor_id: actor
        for actor in (*snapshot.visible_enemies, *snapshot.visible_enemy_buildings, *snapshot.units, *snapshot.buildings)
    }
    goal_graph = compile_mission_goal_graph(snapshot)
    mission_preserve_ids = {
        actor_id
        for node in goal_graph.get("nodes", [])
        if node.get("status") == "incomplete"
        for actor_id in node.get("preserve_actor_ids", [])
    }
    mission_preserve_ids.update(
        actor_id
        for directive in goal_graph.get("briefing_directives", [])
        for actor_id in directive.get("preserve_actor_ids", [])
    )
    result: dict[str, Any] = {
        "active": True,
        "briefing": snapshot.mission_briefing,
        "incomplete_objectives": [objective.as_dict() for objective in incomplete],
        "native_skirmish_brain_active": False,
        "hazards": {
            "disguise_detectors": [
                {"actor_id": dog.actor_id, "name": unit_name(dog.kind), "cell": [dog.cell_x, dog.cell_y]}
                for dog in dogs
            ],
            "rule": "Keep spies outside visible dog detection zones; ordinary enemy units are safe only while disguise remains intact.",
        },
        "recommended_commands": [],
        "goal_graph": goal_graph,
    }

    # Campaign maps can expose the normal construction queues alongside their
    # scripted objectives. A completed structure blocks that queue until it is
    # placed, so this is an urgent economy action in mission mode too. Placement
    # coordinates are deliberately omitted: ActionHandler's native optimizer
    # chooses a legal explored cell with resource, spacing, and exit-lane scoring.
    completed_structure = next((
        item for item in snapshot.production
        if str(item.get("queue_type", "")).lower() in {"building", "defense"}
        and str(item.get("item", "")).strip()
        and (
            float(item.get("progress", 0)) >= 0.999
            or int(item.get("remaining_ticks", 1)) <= 0
        )
    ), None)
    if completed_structure is not None:
        item = str(completed_structure["item"]).strip().lower()
        name = building_name(item)
        result["phase"] = "place-completed-structure"
        result["next_step"] = f"Place the completed {name} now so construction can continue."
        result["recommended_commands"] = [{
            "action": "place_building",
            "item_type": item,
        }]
        return result

    incomplete_text = " ".join(objective.description.lower() for objective in incomplete)
    objective_text = " ".join((
        incomplete_text,
        snapshot.mission_briefing.lower(),
    ))
    engineers = [unit for unit in _live(snapshot.units) if unit.can_capture]
    if "capture" in objective_text:
        for engineer in engineers:
            if not engineer.valid_capture_targets:
                continue
            if not engineer.idle:
                result["phase"] = "mission-order-in-progress"
                result["next_step"] = "Let the engineer finish the current capture approach, then re-check the objective."
                return result
            result["phase"] = "capture-mission-objective"
            result["next_step"] = "Capture the nearest currently legal objective with the engineer."
            result["recommended_commands"] = [{
                "action": "capture",
                "actor_id": engineer.actor_id,
                "target_actor_id": engineer.valid_capture_targets[0],
            }]
            return result

    for spy in spies:
        legal_disguises = [actor_lookup[target] for target in spy.valid_disguise_targets if target in actor_lookup]
        legal_disguises = [target for target in legal_disguises if not target.detects_disguise]
        if not spy.is_disguised and legal_disguises:
            target = min(
                legal_disguises,
                key=lambda actor: (actor.cell_x - spy.cell_x) ** 2 + (actor.cell_y - spy.cell_y) ** 2,
            )
            result["phase"] = "establish-disguise"
            result["next_step"] = f"Disguise the Spy as the visible {unit_name(target.kind)}, then re-evaluate dog patrol positions."
            result["recommended_commands"] = [{
                "action": "disguise",
                "actor_id": spy.actor_id,
                "target_actor_id": target.actor_id,
            }]
            return result

        legal_targets = [actor_lookup[target] for target in spy.valid_infiltration_targets if target in actor_lookup]
        if spy.is_disguised and legal_targets:
            if not spy.idle:
                result["phase"] = "mission-order-in-progress"
                result["next_step"] = "Let the Spy finish the current stealth step, then re-check the dog patrols."
                return result
            target = min(
                legal_targets,
                key=lambda actor: (actor.cell_x - spy.cell_x) ** 2 + (actor.cell_y - spy.cell_y) ** 2,
            )
            route = _stealth_route(
                snapshot,
                (spy.cell_x, spy.cell_y),
                (target.cell_x, target.cell_y),
                dogs,
            )
            if dogs and not route:
                result["phase"] = "hold-for-safe-stealth-route"
                result["next_step"] = "Hold the disguised Spy; no dog-safe route to the infiltration target is currently available."
                return result
            if not route:
                result["phase"] = "hold-for-safe-stealth-route"
                result["next_step"] = "Hold the disguised Spy until a legal route to the infiltration target is visible."
                return result

            # Never queue a long stealth route. A moving dog can invalidate it in
            # seconds. Issue one three-cell hop, then let the observation/event loop
            # re-plan from the resulting live state. Only infiltrate once the spy is
            # already at the safe approach cell selected by the route search.
            if len(route) <= 1:
                approach_clearance = min(
                    (math.hypot(spy.cell_x - dog.cell_x, spy.cell_y - dog.cell_y) for dog in dogs),
                    default=math.inf,
                )
                entrance_clearance = min(
                    (math.hypot(target.cell_x - dog.cell_x, target.cell_y - dog.cell_y) for dog in dogs),
                    default=math.inf,
                )
                if approach_clearance <= 12 or entrance_clearance <= 10:
                    result["phase"] = "hold-for-infiltration-window"
                    result["next_step"] = (
                        "Hold at the safe staging cell until the dog patrol clears both the Spy and "
                        "the War Factory entrance."
                    )
                    return result
                commands = [{
                    "action": "infiltrate",
                    "actor_id": spy.actor_id,
                    "target_actor_id": target.actor_id,
                }]
                route_step: list[tuple[int, int]] = []
                next_step = f"Infiltrate the {building_name(target.kind)} now; the current approach is dog-safe."
            else:
                hop = route[min(3, len(route) - 1)]
                commands = [{
                    "action": "move",
                    "actor_id": spy.actor_id,
                    "target_x": hop[0],
                    "target_y": hop[1],
                }]
                route_step = [hop]
                next_step = (
                    f"Move the disguised Spy one short dog-safe step toward the {building_name(target.kind)}, "
                    "then re-evaluate the patrols."
                )
            result["phase"] = "stealth-infiltration"
            result["next_step"] = next_step
            result["route"] = [list(cell) for cell in route_step]
            result["recommended_commands"] = commands
            return result

    demolitionists = [unit for unit in _live(snapshot.units) if unit.can_demolish]
    if "sam" in objective_text and "destroy" in objective_text:
        for demolitionist in demolitionists:
            legal_targets = [
                actor_lookup[target_id]
                for target_id in demolitionist.valid_demolition_targets
                if target_id in actor_lookup and _actor_type(actor_lookup[target_id]) == "sam"
            ]
            if not legal_targets:
                continue
            if not demolitionist.idle:
                result["phase"] = "mission-order-in-progress"
                result["next_step"] = "Let Tanya finish planting the current charge, then select the next live SAM Site."
                return result
            target = min(
                legal_targets,
                key=lambda actor: (actor.cell_x - demolitionist.cell_x) ** 2 + (actor.cell_y - demolitionist.cell_y) ** 2,
            )
            result["phase"] = "destroy-mission-blockers"
            result["next_step"] = "Use Tanya's C4 on the nearest live SAM Site, preserving her for extraction."
            result["recommended_commands"] = [{
                "action": "demolish",
                "actor_id": demolitionist.actor_id,
                "target_actor_id": target.actor_id,
            }]
            return result

    if demolitionists and any(term in objective_text for term in ("destroy", "offline", "demolish", "power plant")):
        mentioned_priorities = []
        if any(term in objective_text for term in ("power plant", "power plants", "offline")):
            mentioned_priorities.extend(("powr", "apwr"))
        if "tesla" in objective_text:
            mentioned_priorities.append("tsla")
        if "sam" in objective_text:
            mentioned_priorities.append("sam")
        priority = {kind: index for index, kind in enumerate(mentioned_priorities)}
        one_western_target_completed = "westmost" in objective_text and snapshot.buildings_killed >= 1
        for demolitionist in demolitionists:
            legal_targets = [
                actor_lookup[target_id]
                for target_id in demolitionist.valid_demolition_targets
                if target_id in actor_lookup
            ]
            preferred = [target for target in legal_targets if _actor_type(target) in priority]
            if "westmost" in objective_text and preferred:
                west_x = min(target.cell_x for target in preferred)
                preferred = [target for target in preferred if target.cell_x == west_x]
            if one_western_target_completed:
                preferred = []
            if not preferred:
                continue
            if not demolitionist.idle:
                result["phase"] = "mission-order-in-progress"
                result["next_step"] = "Let the demolition specialist finish the current charge, then re-evaluate the mission blocker."
                return result
            target = min(
                preferred,
                key=lambda actor: (
                    priority[_actor_type(actor)],
                    (actor.cell_x - demolitionist.cell_x) ** 2 + (actor.cell_y - demolitionist.cell_y) ** 2,
                ),
            )
            result["phase"] = "demolish-briefed-blocker"
            result["next_step"] = f"Use the demolition specialist on the briefed {building_name(target.kind)} target."
            result["recommended_commands"] = [{
                "action": "demolish",
                "actor_id": demolitionist.actor_id,
                "target_actor_id": target.actor_id,
            }]
            return result

    heroes = [
        unit for unit in _live(snapshot.units)
        if _actor_type(unit) in {"e7", "e7.noautotarget", "tanya"}
    ]
    transports = [
        unit for unit in _live(snapshot.units)
        if (
            unit.passenger_count >= 0
            or _actor_type(unit) in {"tran", "lst", "apc", "hind"}
        )
        and unit.actor_id not in {hero.actor_id for hero in heroes}
    ]
    evacuees = [unit for unit in _live(snapshot.units) if _actor_type(unit) in {"einstein", "scientist"}]
    if any(term in objective_text for term in ("extract", "evacuate")) and evacuees and transports:
        ready_transports = [unit for unit in transports if unit.idle]
        if not ready_transports:
            result["phase"] = "wait-for-extraction-transport"
            result["next_step"] = "Hold the required evacuee safely until the extraction transport has landed."
            return result
        evacuee = evacuees[0]
        if not evacuee.idle:
            result["phase"] = "mission-order-in-progress"
            result["next_step"] = "Let the required evacuee finish moving, then board the extraction transport."
            return result
        transport = min(
            ready_transports,
            key=lambda unit: (unit.cell_x - evacuee.cell_x) ** 2 + (unit.cell_y - evacuee.cell_y) ** 2,
        )
        result["phase"] = "extract-required-evacuee"
        result["next_step"] = "Board the required evacuee into the extraction transport."
        result["recommended_commands"] = [{
            "action": "enter_transport",
            "actor_id": evacuee.actor_id,
            "target_actor_id": transport.actor_id,
        }]
        return result
    if "rescue tanya" in objective_text and heroes and transports:
        hero = heroes[0]
        if not hero.idle:
            result["phase"] = "mission-order-in-progress"
            result["next_step"] = "Let Tanya finish her current action, then board the extraction transport."
            return result
        transport = min(
            transports,
            key=lambda unit: (unit.cell_x - hero.cell_x) ** 2 + (unit.cell_y - hero.cell_y) ** 2,
        )
        result["phase"] = "extract-required-hero"
        result["next_step"] = "Board Tanya into the extraction transport now."
        result["recommended_commands"] = [{
            "action": "enter_transport",
            "actor_id": hero.actor_id,
            "target_actor_id": transport.actor_id,
        }]
        return result

    # Once scripted blockers and hero objectives are resolved, execute the live
    # elimination objective with short group advances and re-plan on each contact.
    if any(term in incomplete_text for term in ("eliminate", "destroy", "wipe out", "kill all")):
        contacts = [*_live(snapshot.visible_enemies), *_live(snapshot.visible_enemy_buildings)]
        combat_units = [
            unit for unit in _live(snapshot.units)
            if unit.can_attack and unit.idle and _actor_type(unit) not in {"camera", "tran"}
            and unit.actor_id not in mission_preserve_ids
        ][:8]
        if contacts and combat_units:
            center_x = round(sum(unit.cell_x for unit in combat_units) / len(combat_units))
            center_y = round(sum(unit.cell_y for unit in combat_units) / len(combat_units))
            target = min(
                contacts,
                key=lambda actor: (actor.cell_x - center_x) ** 2 + (actor.cell_y - center_y) ** 2,
            )
            result["phase"] = "eliminate-mission-opposition"
            result["next_step"] = f"Advance the ready mission force together on the visible {unit_name(target.kind)} contact."
            result["recommended_commands"] = [
                {
                    "action": "attack_move",
                    "actor_id": unit.actor_id,
                    "target_x": target.cell_x,
                    "target_y": target.cell_y,
                }
                for unit in combat_units
            ]
            return result

    ready_primitives = set(goal_graph.get("ready_primitives", []))
    preserve_ids = mission_preserve_ids
    vulnerable = [
        unit for unit in _live(snapshot.units)
        if unit.actor_id in preserve_ids and unit.hp_percent < 0.55 and not unit.idle
    ]
    if vulnerable and ready_primitives & {"defend", "escort", "extract"}:
        home = base_center(snapshot)
        result["phase"] = "preserve-required-actors"
        result["next_step"] = "Pull the damaged required unit behind the friendly formation before continuing the objective."
        result["recommended_commands"] = [
            {"action": "move", "actor_id": unit.actor_id, "target_x": home[0], "target_y": home[1]}
            for unit in vulnerable[:4]
        ]
        return result

    contacts = [*_live(snapshot.visible_enemies), *_live(snapshot.visible_enemy_buildings)]
    if contacts and ready_primitives & {"explore", "defend", "escort", "scripted-trigger"}:
        # Static walls frequently remain visible forever and are often not the
        # route that reveals a scripted trigger.  They must not starve scouting
        # or repeatedly reset the same units onto an unreachable fence cell.
        meaningful_contacts = [actor for actor in contacts if not _is_wall(actor)]
        ready_combat = [
            unit for unit in _live(snapshot.units)
            if unit.can_attack and unit.idle and unit.actor_id not in preserve_ids
        ]
        if not ready_combat:
            ready_combat = [
                unit for unit in _live(snapshot.units)
                if unit.can_attack and unit.idle and unit.hp_percent >= 0.75
            ]
        if ready_combat and meaningful_contacts:
            center = _mean_cell(ready_combat, base_center(snapshot))
            target = min(
                meaningful_contacts,
                key=lambda actor: (
                    0 if actor.can_attack else 1,
                    0 if actor in snapshot.visible_enemies else 1,
                    (actor.cell_x - center[0]) ** 2 + (actor.cell_y - center[1]) ** 2,
                ),
            )
            result["phase"] = "clear-objective-route"
            result["next_step"] = f"Clear the visible {unit_name(target.kind)} blocking the objective route with a cohesive group."
            result["recommended_commands"] = [
                {
                    "action": "attack_move",
                    "actor_id": unit.actor_id,
                    "target_x": target.cell_x,
                    "target_y": target.cell_y,
                }
                for unit in ready_combat[:8]
            ]
            return result

    if ready_primitives & {"explore", "destroy", "scripted-trigger"} and snapshot.explored_percent < 95:
        scouts = sorted(
            (
                unit for unit in snapshot.units
                if unit.idle and _actor_type(unit) in {"e1", "e2", "dog", "jeep"}
                and unit.actor_id not in preserve_ids
            ),
            key=lambda unit: ({"e1": 0, "jeep": 1, "dog": 2, "e2": 3}[_actor_type(unit)], unit.actor_id),
        )[:3]
        targets = scout_targets(snapshot, base_center(snapshot), len(scouts))
        if targets:
            result["phase"] = "reveal-scripted-trigger"
            result["next_step"] = "Reveal separate reachable sectors to find the next scripted contact or trigger."
            result["recommended_commands"] = [
                {
                    "action": "attack_move",
                    "actor_id": unit.actor_id,
                    "target_x": target[0],
                    "target_y": target[1],
                }
                for unit, target in zip(scouts, targets)
            ]
            return result

    result["phase"] = "follow-live-objectives"
    result["next_step"] = incomplete[0].description if incomplete else "Preserve required units and complete the remaining scripted sequence."
    return result


def _reachable(snapshot: GameSnapshot, origin: tuple[int, int]) -> set[tuple[int, int]]:
    if not _valid_spatial(snapshot):
        return set()
    ox, oy = origin
    if not (0 <= ox < snapshot.map_width and 0 <= oy < snapshot.map_height):
        return set()

    def passable(x: int, y: int) -> bool:
        return _spatial_value(snapshot, x, y, 3) > 0

    if not passable(ox, oy):
        nearby = [
            (x, y)
            for y in range(max(0, oy - 3), min(snapshot.map_height, oy + 4))
            for x in range(max(0, ox - 3), min(snapshot.map_width, ox + 4))
            if passable(x, y)
        ]
        if not nearby:
            return set()
        ox, oy = min(nearby, key=lambda cell: (cell[0] - ox) ** 2 + (cell[1] - oy) ** 2)

    reached = {(ox, oy)}
    frontier = deque(((ox, oy),))
    while frontier:
        x, y = frontier.popleft()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
            cell = (x + dx, y + dy)
            if (
                0 <= cell[0] < snapshot.map_width
                and 0 <= cell[1] < snapshot.map_height
                and cell not in reached
                and passable(*cell)
            ):
                reached.add(cell)
                frontier.append(cell)
    return reached


def scout_targets(snapshot: GameSnapshot, origin: tuple[int, int], count: int) -> list[tuple[int, int]]:
    """Choose reachable hidden cells in evenly separated directions from the base."""
    count = max(0, min(4, count))
    reached = _reachable(snapshot, origin)
    if count == 0 or not reached:
        return []
    ox, oy = origin
    long_axis = 0.0 if snapshot.map_width >= snapshot.map_height else math.pi / 2
    angles = [long_axis + 2 * math.pi * index / count for index in range(count)]
    hidden = [cell for cell in reached if _spatial_value(snapshot, cell[0], cell[1], 4) <= 0]
    candidates = hidden or list(reached)
    chosen: list[tuple[int, int]] = []
    minimum_separation = max(6, min(snapshot.map_width, snapshot.map_height) // 4)

    for angle in angles:
        dx = math.cos(angle)
        dy = math.sin(angle)
        ranked = sorted(
            candidates,
            key=lambda cell: (
                -((cell[0] - ox) * dx + (cell[1] - oy) * dy) * 4
                - math.hypot(cell[0] - ox, cell[1] - oy),
                cell[1],
                cell[0],
            ),
        )
        target = next((
            cell for cell in ranked
            if all(math.hypot(cell[0] - other[0], cell[1] - other[1]) >= minimum_separation for other in chosen)
        ), None)
        if target is not None:
            chosen.append(target)
    return chosen


def base_center(snapshot: GameSnapshot) -> tuple[int, int]:
    construction_yard = next(
        (building for building in snapshot.buildings if building.kind.lower().split(".", 1)[0] == "fact"),
        None,
    )
    if construction_yard is not None:
        return construction_yard.cell_x, construction_yard.cell_y
    assets: tuple[Unit, ...] = (*snapshot.buildings, *snapshot.units)
    if assets:
        return (
            round(sum(asset.cell_x for asset in assets) / len(assets)),
            round(sum(asset.cell_y for asset in assets) / len(assets)),
        )
    return snapshot.map_width // 2, snapshot.map_height // 2


def rally_target(snapshot: GameSnapshot, building: Unit) -> tuple[int, int] | None:
    """Choose an explored, uncluttered staging point beyond the south-facing RA production doors."""
    if not _valid_spatial(snapshot):
        return None
    radius = {"small": 5, "medium": 7, "large": 9, "huge": 10}[map_scale(snapshot.map_width, snapshot.map_height)]
    desired = (building.cell_x + 1, building.cell_y + radius)
    candidates: list[tuple[float, int, int]] = []
    for y in range(max(0, building.cell_y + 3), min(snapshot.map_height, building.cell_y + radius + 4)):
        for x in range(max(0, building.cell_x - radius), min(snapshot.map_width, building.cell_x + radius + 2)):
            if _spatial_value(snapshot, x, y, 3) <= 0 or _spatial_value(snapshot, x, y, 4) <= 0:
                continue
            if any((x - other.cell_x) ** 2 + (y - other.cell_y) ** 2 <= 9 for other in snapshot.buildings):
                continue
            resource = _spatial_value(snapshot, x, y, 2)
            actor_density = sum(_spatial_value(snapshot, x, y, channel) for channel in range(5, 9))
            clearance = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < snapshot.map_width and 0 <= ny < snapshot.map_height:
                        clearance += int(_spatial_value(snapshot, nx, ny, 3) > 0)
            score = (x - desired[0]) ** 2 + (y - desired[1]) ** 2 + resource * 12 + actor_density * 80 - clearance * 3
            candidates.append((score, x, y))
    if not candidates:
        return None
    _, x, y = min(candidates)
    return x, y
