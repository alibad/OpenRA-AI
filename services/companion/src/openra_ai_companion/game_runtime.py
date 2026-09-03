from __future__ import annotations

import json
import struct
import threading
import time
from collections import Counter, deque
from pathlib import Path
from typing import Any

from .bridge import DEFAULT_INTERRUPTS, OpenRABridge
from .labels import building_name, unit_name
from .models import ActionCommand, GameSnapshot
from .settings import Settings
from .strategy import (
    desired_harvester_count,
    hybrid_force_plan,
    maximum_queued_unit_count,
    maximum_silo_count,
    mission_plan,
    strategic_profile,
    tactical_plan,
)
from .strategy_contracts import strategy_state
from .tactical_vision import tactical_overview_png


class GameRuntime:
    """Stateful, fog-respecting action boundary shared by MCP gameplay tools."""

    _NOISY_INTERRUPTS = frozenset({"enemy_spotted", "under_attack", "unit_destroyed", "production_complete"})
    _INTERRUPT_COOLDOWN_TICKS = 100
    _TACTICAL_CAPTURE_INTERVAL_TICKS = 125

    def __init__(
        self,
        address: str,
        session_id: str,
        *,
        evidence_log: Path | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.bridge = OpenRABridge(address, session_id=session_id, timeout=timeout)
        self.evidence_log = evidence_log
        self._snapshot: GameSnapshot | None = None
        self._lock = threading.Lock()
        self._last_interrupt_ticks: dict[str, int] = {}
        self._silo_episode_active = False
        self._silo_episode_capacity = 0
        self._last_tactical_capture_tick = -self._TACTICAL_CAPTURE_INTERVAL_TICKS
        self._tactical_capture_sequence = 0
        self._last_command_fingerprint = ""
        self._last_command_tick = -25

    @property
    def session_id(self) -> str:
        return self.bridge.session_id

    def close(self) -> None:
        self.bridge.close()

    def _write_evidence(self, event: str, payload: dict[str, Any]) -> None:
        if self.evidence_log is None:
            return
        self.evidence_log.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "time": time.time(),
            "session_id": self.session_id,
            "event": event,
            **payload,
        }
        with self.evidence_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")

    def _capture_tactical_evidence(
        self,
        snapshot: GameSnapshot,
        reason: str,
        *,
        force: bool = False,
    ) -> dict[str, Any] | None:
        """Persist a fog-respecting tactical frame, never hidden engine state."""
        if self.evidence_log is None:
            return None
        last_tick = getattr(self, "_last_tactical_capture_tick", -self._TACTICAL_CAPTURE_INTERVAL_TICKS)
        if not force and snapshot.tick - last_tick < self._TACTICAL_CAPTURE_INTERVAL_TICKS:
            return None
        png = tactical_overview_png(snapshot)
        if png is None:
            return None

        sequence = getattr(self, "_tactical_capture_sequence", 0) + 1
        self._tactical_capture_sequence = sequence
        self._last_tactical_capture_tick = snapshot.tick
        frames_dir = self.evidence_log.parent / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        safe_reason = "".join(character if character.isalnum() else "-" for character in reason.lower()).strip("-")
        filename = f"{snapshot.tick:07d}-{sequence:05d}-{safe_reason or 'periodic'}.png"
        (frames_dir / filename).write_bytes(png)
        metadata = {
            "time": time.time(),
            "session_id": self.session_id,
            "tick": snapshot.tick,
            "reason": reason,
            "scope": "full-map-tactical-overview-fog-respecting",
            "file": f"frames/{filename}",
            "bytes": len(png),
        }
        with (self.evidence_log.parent / "frames.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(metadata, separators=(",", ":")) + "\n")
        return metadata

    def observe(self) -> GameSnapshot:
        with self._lock:
            self._snapshot = self.bridge.observe()
            self._refresh_silo_episode(self._snapshot)
            return self._snapshot

    def capture_tactical_evidence(self, reason: str = "periodic", *, force: bool = False) -> dict[str, Any] | None:
        """Capture a fog-respecting frame for evaluators and other non-MCP callers."""
        snapshot = self._snapshot or self.observe()
        return self._capture_tactical_evidence(snapshot, reason, force=force)

    def _refresh_silo_episode(self, snapshot: GameSnapshot) -> None:
        if not self._silo_episode_active:
            return
        storage_percent = (
            snapshot.ore / snapshot.resource_capacity * 100
            if snapshot.resource_capacity else 0
        )
        if snapshot.resource_capacity > self._silo_episode_capacity and storage_percent <= 80:
            self._silo_episode_active = False
            self._silo_episode_capacity = snapshot.resource_capacity

    def state(self) -> dict[str, Any]:
        return self.bridge.state()

    @staticmethod
    def _early_structure_block(snapshot: GameSnapshot, item: str) -> str:
        item = item.lower().split(".", 1)[0]
        building_kinds = [building.kind.lower().split(".", 1)[0] for building in snapshot.buildings]
        power_balance = snapshot.power_provided - snapshot.power_drained
        if item in {"powr", "apwr"} and sum(kind in {"powr", "apwr"} for kind in building_kinds) >= 2 and power_balance >= 50:
            return "two power plants already provide safe headroom"
        if item in {"tent", "barr"} and sum(kind in {"tent", "barr"} for kind in building_kinds) >= 1 and snapshot.tick < 8_000:
            return "the opening barracks is sufficient before tick 8000"
        if item == "proc" and building_kinds.count("proc") >= 1 and snapshot.harvester_count >= 2 and snapshot.tick < 6_000:
            return "the opening refinery and two harvesters are sufficient before tick 6000"
        if item == "weap" and building_kinds.count("weap") >= 1 and snapshot.tick < 8_000:
            return "the opening war factory is sufficient before tick 8000"
        return ""

    @staticmethod
    def _display_type_counts(actors: tuple[Any, ...], *, buildings: bool = False,
                             snapshot: GameSnapshot | None = None) -> dict[str, int]:
        label = snapshot.actor_name if snapshot is not None else building_name if buildings else unit_name
        return dict(sorted(Counter(label(actor.kind) for actor in actors).items()))

    @staticmethod
    def _reachable_cells(snapshot: GameSnapshot) -> set[int]:
        width = snapshot.map_width
        height = snapshot.map_height
        channels = snapshot.spatial_channels
        expected = width * height * channels * 4
        if width <= 0 or height <= 0 or channels < 5 or len(snapshot.spatial_map) != expected:
            return set()

        passable = [False] * (width * height)
        for y in range(height):
            for x in range(width):
                cell_offset = (y * width + x) * channels * 4
                passable[y * width + x] = struct.unpack_from(
                    "<f", snapshot.spatial_map, cell_offset + 3 * 4
                )[0] > 0

        starts = {
            actor.cell_y * width + actor.cell_x
            for actor in (*snapshot.units, *snapshot.buildings)
            if 0 <= actor.cell_x < width
            and 0 <= actor.cell_y < height
            and passable[actor.cell_y * width + actor.cell_x]
        }
        reachable = set(starts)
        frontier = deque(starts)
        while frontier:
            cell = frontier.popleft()
            x = cell % width
            y = cell // width
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx = x + dx
                    ny = y + dy
                    if not (0 <= nx < width and 0 <= ny < height):
                        continue
                    neighbor = ny * width + nx
                    if passable[neighbor] and neighbor not in reachable:
                        reachable.add(neighbor)
                        frontier.append(neighbor)

        # Synthetic/unit-test snapshots may omit actors. In that case passability
        # is still a useful, conservative fallback.
        if not starts:
            reachable = {index for index, cell_passable in enumerate(passable) if cell_passable}
        return reachable

    @staticmethod
    def _exploration_sectors(snapshot: GameSnapshot, columns: int = 4, rows: int = 3) -> list[dict[str, Any]]:
        width = snapshot.map_width
        height = snapshot.map_height
        channels = snapshot.spatial_channels
        reachable = GameRuntime._reachable_cells(snapshot)
        if not reachable:
            return []

        sectors: list[dict[str, Any]] = []
        for row in range(rows):
            y0 = row * height // rows
            y1 = (row + 1) * height // rows
            for column in range(columns):
                x0 = column * width // columns
                x1 = (column + 1) * width // columns
                explored = 0
                traversable = 0
                for y in range(y0, y1):
                    for x in range(x0, x1):
                        cell_offset = (y * width + x) * channels * 4
                        if y * width + x not in reachable:
                            continue
                        traversable += 1
                        if struct.unpack_from("<f", snapshot.spatial_map, cell_offset + 4 * 4)[0] > 0:
                            explored += 1
                if traversable == 0:
                    continue
                sectors.append({
                    "center": [(x0 + x1 - 1) // 2, (y0 + y1 - 1) // 2],
                    "explored_percent": round(explored / traversable * 100, 1),
                })
        return sorted(sectors, key=lambda sector: sector["explored_percent"])

    @staticmethod
    def _exploration_targets(snapshot: GameSnapshot, limit: int = 12) -> list[dict[str, Any]]:
        width = snapshot.map_width
        height = snapshot.map_height
        channels = snapshot.spatial_channels
        reachable = GameRuntime._reachable_cells(snapshot)
        hidden = set()
        for cell in reachable:
            cell_offset = cell * channels * 4
            if struct.unpack_from("<f", snapshot.spatial_map, cell_offset + 4 * 4)[0] <= 0:
                hidden.add(cell)

        components: list[set[int]] = []
        while hidden:
            seed = hidden.pop()
            component = {seed}
            frontier = deque((seed,))
            while frontier:
                cell = frontier.popleft()
                x = cell % width
                y = cell // width
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx = x + dx
                        ny = y + dy
                        if not (0 <= nx < width and 0 <= ny < height):
                            continue
                        neighbor = ny * width + nx
                        if neighbor in hidden:
                            hidden.remove(neighbor)
                            component.add(neighbor)
                            frontier.append(neighbor)
            components.append(component)

        targets: list[dict[str, Any]] = []
        for component in sorted(components, key=len, reverse=True)[:limit]:
            mean_x = sum(cell % width for cell in component) / len(component)
            mean_y = sum(cell // width for cell in component) / len(component)
            target = min(
                component,
                key=lambda cell: ((cell % width - mean_x) ** 2 + (cell // width - mean_y) ** 2, cell),
            )
            targets.append({
                "target": [target % width, target // width],
                "hidden_cells": len(component),
            })
        return targets

    def battlefield(self) -> dict[str, Any]:
        snapshot = self.observe()
        match_state = self.state()
        result = snapshot.action_context()
        safe_production = [
            item for item in snapshot.available_production
            if not item.lower().endswith("f") and not self._early_structure_block(snapshot, item)
        ]
        result["available_production"] = safe_production[:64]
        result["available_production_names"] = [
            {"id": item, "name": snapshot.actor_name(item)} for item in safe_production[:64]
        ]
        for building in result["own_buildings"]:
            building["can_produce"] = [
                item for item in building["can_produce"] if not item.lower().endswith("f")
            ]
        result["counts"] = {
            "own_units": self._display_type_counts(snapshot.units, snapshot=snapshot),
            "own_buildings": self._display_type_counts(snapshot.buildings, buildings=True, snapshot=snapshot),
            "visible_enemy_units": self._display_type_counts(snapshot.visible_enemies, snapshot=snapshot),
            "visible_enemy_buildings": self._display_type_counts(snapshot.visible_enemy_buildings, buildings=True, snapshot=snapshot),
        }
        result["harvesters"] = snapshot.harvester_count
        result["explored_percent"] = round(snapshot.explored_percent, 1)
        result["storage_policy"] = {
            "current_silos": sum(
                building.kind.lower().split(".", 1)[0] == "silo"
                for building in snapshot.buildings
            ),
            "maximum_silos": maximum_silo_count(snapshot),
            "overflow_action": "spend on combat production and map control after the silo limit",
        }
        result["exploration_sectors"] = self._exploration_sectors(snapshot)
        result["exploration_targets"] = self._exploration_targets(snapshot)
        result["strategy_profile"] = strategic_profile(snapshot, match_state)
        settings = Settings.from_env()
        result["assistant_strategy"] = strategy_state(
            snapshot,
            settings.native_strategy,
            native_active=settings.auto_act_enabled and not snapshot.mission_mode,
        )
        result["force_plan"] = hybrid_force_plan(snapshot)
        result["tactical_plan"] = tactical_plan(snapshot)
        result["mission_plan"] = mission_plan(snapshot)
        result["reward"] = round(snapshot.reward, 3)
        self._write_evidence("battlefield", {
            "tick": snapshot.tick,
            "phase": match_state.get("phase", ""),
            "factions": {
                "player": match_state.get("player_faction", ""),
                "enemy": match_state.get("enemy_faction", ""),
            },
            "economy": {
                "cash": snapshot.cash,
                "ore": snapshot.ore,
                "resource_capacity": snapshot.resource_capacity,
                "storage_percent": round(snapshot.ore / snapshot.resource_capacity * 100, 1)
                if snapshot.resource_capacity else 0,
                "power_balance": snapshot.power_provided - snapshot.power_drained,
                "harvesters": snapshot.harvester_count,
            },
            "military": {
                "army_value": snapshot.army_value,
                "assets_value": snapshot.assets_value,
                "units_killed": snapshot.units_killed,
                "units_lost": snapshot.units_lost,
                "buildings_killed": snapshot.buildings_killed,
                "buildings_lost": snapshot.buildings_lost,
            },
            "explored_percent": round(snapshot.explored_percent, 1),
            "counts": result["counts"],
        })
        self._capture_tactical_evidence(snapshot, "periodic")
        return result

    def log_decision(self, decision: str, evidence: str, expected_result: str) -> dict[str, Any]:
        values = {
            "decision": decision.strip(),
            "evidence": evidence.strip(),
            "expected_result": expected_result.strip(),
        }
        if any(not value or len(value) > 500 for value in values.values()):
            raise ValueError("decision, evidence, and expected_result must each contain 1-500 characters")
        snapshot = self._snapshot or self.observe()
        payload = {"tick": snapshot.tick, **values}
        self._write_evidence("decision", payload)
        frame = self._capture_tactical_evidence(snapshot, "decision", force=True)
        if frame is not None:
            payload["tactical_frame"] = frame["file"]
        return {"logged": True, **payload}

    @staticmethod
    def _validate(snapshot: GameSnapshot, commands: tuple[ActionCommand, ...]) -> None:
        if not 1 <= len(commands) <= 32:
            raise ValueError("a tool call must issue between 1 and 32 commands")

        units = {unit.actor_id: unit for unit in snapshot.units}
        buildings = {building.actor_id: building for building in snapshot.buildings}
        owned = units | buildings
        visible_enemies = {unit.actor_id for unit in snapshot.visible_enemies}
        visible_enemies.update(building.actor_id for building in snapshot.visible_enemy_buildings)
        available = {item.lower() for item in snapshot.available_production}
        queued_counts = Counter(str(item.get("item", "")).lower() for item in snapshot.production)
        queued = set(queued_counts)
        support_powers = {
            str(power.get("key", "")).lower(): power
            for power in snapshot.support_powers
            if str(power.get("key", "")).strip()
        }
        queued_buildings = {
            str(item.get("item", "")).lower()
            for item in snapshot.production
            if str(item.get("queue_type", "")).lower() in {"building", "defense"}
        }
        queued_harvesters = sum(
            str(item.get("item", "")).lower().split(".", 1)[0] == "harv"
            for item in snapshot.production
        )
        planned_harvesters = 0
        planned_units: Counter[str] = Counter()

        unit_actions = {
            "move",
            "attack_move",
            "attack",
            "stop",
            "harvest",
            "guard",
            "set_stance",
            "enter_transport",
            "disguise",
            "infiltrate",
            "demolish",
            "capture",
            "unload",
        }
        building_actions = {"sell", "repair", "set_rally_point", "power_down", "set_primary"}

        for command in commands:
            if command.action in unit_actions and command.actor_id not in units:
                raise ValueError(f"actor {command.actor_id} is not an owned unit")
            if command.action == "deploy" and command.actor_id not in units:
                raise ValueError(f"actor {command.actor_id} is not an owned deployable unit")
            if command.action in building_actions and command.actor_id not in buildings:
                raise ValueError(f"actor {command.actor_id} is not an owned building")
            if command.action in {"attack", "attack_move", "guard", "set_stance"}:
                if not units[command.actor_id].can_attack:
                    raise ValueError(f"actor {command.actor_id} cannot attack")
            if command.action == "attack" and command.target_actor_id not in visible_enemies:
                raise ValueError(f"target {command.target_actor_id} is not a visible enemy")
            if command.action == "guard" and command.target_actor_id not in owned:
                raise ValueError(f"target {command.target_actor_id} is not owned")
            if command.action == "enter_transport":
                transport = units.get(command.target_actor_id)
                transport_kind = transport.kind.lower().split("@", 1)[0].split(".", 1)[0] if transport else ""
                if transport is None or (
                    transport.passenger_count < 0
                    and transport_kind not in {"tran", "lst", "apc", "hind"}
                ):
                    raise ValueError(f"target {command.target_actor_id} is not an owned transport")
            if command.action == "disguise" and command.target_actor_id not in units[command.actor_id].valid_disguise_targets:
                raise ValueError(f"target {command.target_actor_id} is not a valid visible disguise target")
            if command.action == "infiltrate" and command.target_actor_id not in units[command.actor_id].valid_infiltration_targets:
                raise ValueError(f"target {command.target_actor_id} is not a valid visible infiltration target")
            if command.action == "demolish" and command.target_actor_id not in units[command.actor_id].valid_demolition_targets:
                raise ValueError(f"target {command.target_actor_id} is not a valid visible demolition target")
            if command.action == "capture" and command.target_actor_id not in units[command.actor_id].valid_capture_targets:
                raise ValueError(f"target {command.target_actor_id} is not a valid visible capture target")
            if command.action == "unload" and units[command.actor_id].passenger_count <= 0:
                raise ValueError(f"transport {command.actor_id} has no passengers")
            if command.action == "repair" and buildings[command.actor_id].hp_percent >= 0.999:
                raise ValueError(f"building {command.actor_id} is not damaged")
            if command.action == "sell":
                kind = buildings[command.actor_id].kind.lower().split(".", 1)[0]
                if kind == "fact":
                    raise ValueError("the Construction Yard cannot be sold by autonomous tools")
                production_kinds = {"tent", "barr", "weap", "afld", "spen", "syrd"}
                same_kind = sum(
                    building.kind.lower().split(".", 1)[0] == kind
                    for building in buildings.values()
                )
                if kind in production_kinds and same_kind <= 1:
                    raise ValueError(f"the last {kind} production building cannot be sold")
            if command.action == "power_down":
                kind = buildings[command.actor_id].kind.lower().split(".", 1)[0]
                essential = {"fact", "powr", "apwr", "proc", "tent", "barr", "weap"}
                if kind in essential:
                    raise ValueError(f"essential building {command.actor_id} cannot be powered down")
            if command.action == "set_stance" and not 0 <= command.target_x <= 3:
                raise ValueError("stance must be between 0 and 3")

            required_position = command.action in {"move", "attack_move", "set_rally_point", "use_support_power"}
            supplied_position = command.target_x != 0 or command.target_y != 0
            if required_position or (command.action in {"harvest", "place_building"} and supplied_position):
                if not snapshot.contains_cell(command.target_x, command.target_y):
                    raise ValueError(f"target ({command.target_x},{command.target_y}) is outside the map")

            if command.action in {"build", "train"} and command.item_type not in available:
                raise ValueError(f"'{command.item_type}' is not currently available")
            if command.action == "build" and command.item_type.split(".", 1)[0] == "silo":
                silo_count = sum(
                    building.kind.lower().split(".", 1)[0] == "silo"
                    for building in snapshot.buildings
                )
                limit = maximum_silo_count(snapshot)
                if silo_count >= limit:
                    raise ValueError(f"the map-scaled silo limit of {limit} is already reached")
                if (
                    snapshot.resource_capacity > 0
                    and snapshot.ore * 100 <= snapshot.resource_capacity * 80
                ):
                    raise ValueError("a silo is only needed above 80% storage")
            if command.action == "train" and command.item_type.split(".", 1)[0] == "harv":
                target = desired_harvester_count(snapshot)
                if snapshot.harvester_count + queued_harvesters + planned_harvesters >= target:
                    raise ValueError(f"the map-scaled harvester target of {target} is already covered")
                planned_harvesters += 1
            elif command.action == "train":
                limit = maximum_queued_unit_count(command.item_type)
                if queued_counts[command.item_type] + planned_units[command.item_type] >= limit:
                    raise ValueError(
                        f"'{command.item_type}' already reaches its rolling queue limit of {limit}; "
                        "choose a complementary unit or wait for production"
                    )
                planned_units[command.item_type] += 1
            if command.action == "build" and command.item_type.endswith("f"):
                raise ValueError(f"'{command.item_type}' is a decoy building and cannot be built")
            if command.action == "build":
                reason = GameRuntime._early_structure_block(snapshot, command.item_type)
                if reason:
                    raise ValueError(f"'{command.item_type}' is blocked: {reason}")
            if command.action == "build" and command.item_type in queued_buildings:
                raise ValueError(f"'{command.item_type}' is already queued for construction")
            if command.action == "build" and sum(
                other.action == "build" and other.item_type == command.item_type
                for other in commands
            ) > 1:
                raise ValueError(f"only one '{command.item_type}' building may be queued at a time")
            if command.action == "cancel_production" and command.item_type not in queued:
                raise ValueError(f"'{command.item_type}' is not currently queued")
            if command.action == "place_building":
                matching = next((
                    item for item in snapshot.production
                    if str(item.get("item", "")).lower() == command.item_type
                ), None)
                complete = matching is not None and (
                    float(matching.get("progress", 0)) >= 0.999
                    or int(matching.get("remaining_ticks", 1)) <= 0
                )
                if not complete:
                    raise ValueError(f"'{command.item_type}' has not completed production")
            if command.action == "use_support_power":
                power = support_powers.get(command.item_type.lower())
                if power is None or not bool(power.get("active", False)) or not bool(power.get("ready", False)):
                    raise ValueError(f"support power '{command.item_type}' is not ready")
                descriptor = " ".join((command.item_type, str(power.get("name", "")), str(power.get("description", "")))).lower()
                if any(term in descriptor for term in ("nuke", "atomic", "parabomb")):
                    if any(
                        (actor.cell_x - command.target_x) ** 2 + (actor.cell_y - command.target_y) ** 2 <= 15 ** 2
                        for actor in (*snapshot.units, *snapshot.buildings)
                    ):
                        raise ValueError("destructive support power target violates the 15-cell friendly-fire exclusion zone")
                    if not any(
                        (actor.cell_x - command.target_x) ** 2 + (actor.cell_y - command.target_y) ** 2 <= 6 ** 2
                        for actor in (*snapshot.visible_enemies, *snapshot.visible_enemy_buildings)
                    ):
                        raise ValueError("destructive support powers require a currently visible enemy concentration")

    def issue(self, commands: tuple[ActionCommand, ...], *, ticks: int = 1) -> dict[str, Any]:
        with self._lock:
            snapshot = self._snapshot or self.bridge.observe()
            fingerprint = json.dumps([command.as_dict() for command in commands], sort_keys=True, separators=(",", ":"))
            self._refresh_silo_episode(snapshot)
            silo_builds = sum(
                command.action == "build" and command.item_type == "silo"
                for command in commands
            )
            silo_queued = any(
                str(item.get("item", "")).lower() == "silo"
                for item in snapshot.production
            )
            if silo_builds > 1 or (silo_builds and (self._silo_episode_active or silo_queued)):
                raise ValueError("one silo is already queued for the current storage episode")
            self._validate(snapshot, commands)
            if (
                fingerprint == getattr(self, "_last_command_fingerprint", "")
                and snapshot.tick - getattr(self, "_last_command_tick", -25) < 25
            ):
                raise ValueError("an identical command was already issued in the last 25 ticks")
            self._snapshot = self.bridge.fast_advance(
                ticks,
                commands,
                check_events_every=0,
                enabled_interrupts=(),
            )
            self._last_command_fingerprint = fingerprint
            self._last_command_tick = self._snapshot.tick
            if silo_builds:
                self._silo_episode_active = True
                self._silo_episode_capacity = snapshot.resource_capacity
            if any(
                command.action == "cancel_production" and command.item_type == "silo"
                for command in commands
            ):
                self._silo_episode_active = False
            payload = {
                "queued": [command.as_dict() for command in commands],
                "tick": self._snapshot.tick,
                "done": self._snapshot.done,
                "result": self._snapshot.result,
                "economy": {
                    "cash": self._snapshot.cash,
                    "ore": self._snapshot.ore,
                    "resource_capacity": self._snapshot.resource_capacity,
                    "storage_percent": round(self._snapshot.ore / self._snapshot.resource_capacity * 100, 1)
                    if self._snapshot.resource_capacity else 0,
                    "power_balance": self._snapshot.power_provided - self._snapshot.power_drained,
                    "harvesters": self._snapshot.harvester_count,
                },
                "production": list(self._snapshot.production[:12]),
                "counts": {
                    "own_units": self._display_type_counts(self._snapshot.units, snapshot=self._snapshot),
                    "own_buildings": self._display_type_counts(self._snapshot.buildings, buildings=True, snapshot=self._snapshot),
                },
            }
            self._write_evidence("commands", payload)
            return payload

    def propose(self, commands: tuple[ActionCommand, ...]) -> dict[str, Any]:
        """Validate commands against live state without sending them to OpenRA."""
        with self._lock:
            snapshot = self.bridge.observe()
            self._snapshot = snapshot
            self._validate(snapshot, commands)
            return {
                "proposal_mode": True,
                "requires_confirmation": True,
                "proposed": [command.as_dict() for command in commands],
                "tick": snapshot.tick,
                "done": snapshot.done,
                "result": snapshot.result,
            }

    def advance(self, ticks: int) -> dict[str, Any]:
        if not 1 <= ticks <= 1_500:
            raise ValueError("ticks must be between 1 and 1500")
        with self._lock:
            previous = self._snapshot
            requested_ticks = ticks
            if (
                previous is not None
                and not previous.done
                and not previous.mission_mode
                and previous.harvester_count == 0
            ):
                building_types = {
                    building.kind.lower().split(".", 1)[0]
                    for building in previous.buildings
                }
                if "proc" not in building_types:
                    # Do not let a small local model burn several simulated
                    # minutes while the opening economy is still incomplete.
                    # It must build/deploy between these short waits.
                    ticks = min(ticks, 200 if previous.production else 50)
            current_tick = self._snapshot.tick if self._snapshot is not None else 0
            enabled_interrupts = tuple(
                reason
                for reason in DEFAULT_INTERRUPTS
                if reason not in self._NOISY_INTERRUPTS
                or current_tick - self._last_interrupt_ticks.get(reason, -self._INTERRUPT_COOLDOWN_TICKS)
                >= self._INTERRUPT_COOLDOWN_TICKS
            )
            self._snapshot = self.bridge.fast_advance(
                ticks,
                check_events_every=min(25, ticks),
                enabled_interrupts=enabled_interrupts,
            )
            if self._snapshot.interrupt_reason in self._NOISY_INTERRUPTS:
                self._last_interrupt_ticks[self._snapshot.interrupt_reason] = self._snapshot.tick
            payload = {
                "tick": self._snapshot.tick,
                "requested_ticks": requested_ticks,
                "applied_tick_cap": ticks,
                "actual_ticks": self._snapshot.actual_ticks_advanced,
                "interrupted": self._snapshot.interrupted,
                "interrupt_reason": self._snapshot.interrupt_reason,
                "done": self._snapshot.done,
                "result": self._snapshot.result,
                "reward": round(self._snapshot.reward, 3),
                "economy": {
                    "cash": self._snapshot.cash,
                    "ore": self._snapshot.ore,
                    "resource_capacity": self._snapshot.resource_capacity,
                    "storage_percent": round(self._snapshot.ore / self._snapshot.resource_capacity * 100, 1)
                    if self._snapshot.resource_capacity else 0,
                    "power_balance": self._snapshot.power_provided - self._snapshot.power_drained,
                    "harvesters": self._snapshot.harvester_count,
                },
                "military": {
                    "army_value": self._snapshot.army_value,
                    "assets_value": self._snapshot.assets_value,
                    "units_killed": self._snapshot.units_killed,
                    "units_lost": self._snapshot.units_lost,
                    "buildings_killed": self._snapshot.buildings_killed,
                    "buildings_lost": self._snapshot.buildings_lost,
                },
            }
            self._write_evidence("advance", payload)
            loss_increased = previous is not None and (
                self._snapshot.units_lost > previous.units_lost
                or self._snapshot.buildings_lost > previous.buildings_lost
            )
            critical_interrupt = self._snapshot.interrupt_reason in {
                "under_attack",
                "unit_destroyed",
                "building_destroyed",
                "game_over",
            }
            if loss_increased or critical_interrupt or self._snapshot.done:
                self._capture_tactical_evidence(
                    self._snapshot,
                    self._snapshot.interrupt_reason or "loss-or-game-over",
                    force=True,
                )
            return payload
