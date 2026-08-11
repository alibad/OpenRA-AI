from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from .models import ActionCommand, ActionProposal, ActionReceipt, GameSnapshot


class BrainOwner(str, Enum):
    """The one brain currently responsible for an action or control scope."""

    USER = "user"
    SAFETY = "safety"
    MISSION = "mission"
    NATIVE = "native"
    OPERATIONAL = "operational"
    LLM = "llm"


class GoalStatus(str, Enum):
    PROPOSED = "proposed"
    DISPATCHED = "dispatched"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    RETRY_READY = "retry_ready"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


TERMINAL_GOAL_STATES = frozenset({
    GoalStatus.SUCCEEDED,
    GoalStatus.FAILED,
    GoalStatus.CANCELLED,
    GoalStatus.SUPERSEDED,
})


OWNER_PRIORITY = {
    BrainOwner.LLM: 10,
    BrainOwner.NATIVE: 20,
    BrainOwner.OPERATIONAL: 30,
    BrainOwner.MISSION: 40,
    BrainOwner.SAFETY: 50,
    BrainOwner.USER: 60,
}


def default_blackboard_path() -> Path:
    configured = os.getenv("OPENRA_AI_BRAIN_STATE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[4] / ".artifacts" / "runtime" / "brain-blackboard.jsonl"


def command_fingerprint(commands: Iterable[ActionCommand]) -> str:
    encoded = json.dumps(
        [command.as_dict() for command in commands],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def command_scope(commands: Iterable[ActionCommand]) -> str:
    actions = {command.action for command in commands}
    if actions & {"build", "train", "place_building", "cancel_production", "set_primary"}:
        return "production"
    if actions & {"repair", "sell", "power_down", "set_rally_point"}:
        return "base"
    if actions & {"capture", "disguise", "infiltrate", "demolish", "enter_transport", "unload"}:
        return "mission-specialists"
    return "combat"


def _kind(value: str) -> str:
    return value.lower().split(".", 1)[0]


def _snapshot_baseline(snapshot: GameSnapshot, commands: tuple[ActionCommand, ...]) -> dict[str, Any]:
    actors = {
        actor.actor_id: actor
        for actor in (
            *snapshot.units,
            *snapshot.buildings,
            *snapshot.visible_enemies,
            *snapshot.visible_enemy_buildings,
        )
    }
    relevant_ids = {
        value
        for command in commands
        for value in (command.actor_id, command.target_actor_id)
        if value > 0
    }
    return {
        "tick": snapshot.tick,
        "order_count": snapshot.order_count,
        "production": sorted(_kind(str(item.get("item", ""))) for item in snapshot.production),
        "support_powers": {
            str(power.get("key", "")).lower(): bool(power.get("ready", False))
            for power in snapshot.support_powers
        },
        "unit_counts": dict(Counter(_kind(actor.kind) for actor in snapshot.units)),
        "building_counts": dict(Counter(_kind(actor.kind) for actor in snapshot.buildings)),
        "actors": {
            str(actor_id): {
                "cell": [actor.cell_x, actor.cell_y],
                "hp": actor.hp_percent,
                "idle": actor.idle,
                "activity": actor.current_activity,
                "stance": actor.stance,
                "current_target_actor_id": actor.current_target_actor_id,
                "passengers": actor.passenger_count,
                "powered": actor.powered,
                "rally": [actor.rally_x, actor.rally_y],
            }
            for actor_id in relevant_ids
            if (actor := actors.get(actor_id)) is not None
        },
    }


@dataclass
class ControlLease:
    scope: str
    owner: BrainOwner
    acquired_tick: int
    expires_tick: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "owner": self.owner.value,
            "acquired_tick": self.acquired_tick,
            "expires_tick": self.expires_tick,
            "reason": self.reason,
        }


class BrainArbiter:
    """Deterministic ownership boundary between user, safety, mission, and native brains."""

    def __init__(self) -> None:
        self._leases: dict[str, ControlLease] = {}
        self._lock = threading.Lock()

    @staticmethod
    def owner_for(
        instruction: str,
        snapshot: GameSnapshot,
        *,
        auto_act: bool,
        native_brain_available: bool,
        commands: Iterable[ActionCommand] = (),
    ) -> BrainOwner:
        normalized = instruction.strip().lower()
        action_names = {command.action for command in commands}
        if normalized.startswith("safety:"):
            return BrainOwner.SAFETY
        if normalized.startswith("mission:") or (auto_act and snapshot.mission_mode):
            return BrainOwner.MISSION
        if normalized.startswith("contextual:") and action_names & {"stop", "move", "repair", "power_down"}:
            return BrainOwner.SAFETY
        if normalized.startswith("autonomous commander mode") or normalized.startswith("auto:"):
            return BrainOwner.OPERATIONAL
        if auto_act and native_brain_available:
            return BrainOwner.NATIVE
        if normalized.startswith("llm:"):
            return BrainOwner.LLM
        return BrainOwner.USER

    def claim(self, scope: str, owner: BrainOwner, tick: int, *, ttl_ticks: int, reason: str) -> bool:
        with self._lock:
            current = self._leases.get(scope)
            if (
                current is not None
                and current.expires_tick >= tick
                and OWNER_PRIORITY[current.owner] > OWNER_PRIORITY[owner]
            ):
                return False
            self._leases[scope] = ControlLease(
                scope=scope,
                owner=owner,
                acquired_tick=tick,
                expires_tick=tick + max(1, ttl_ticks),
                reason=reason,
            )
            return True

    def release(self, scope: str, owner: BrainOwner | None = None) -> None:
        with self._lock:
            current = self._leases.get(scope)
            if current is not None and (owner is None or current.owner == owner):
                self._leases.pop(scope, None)

    def state(self, tick: int) -> list[dict[str, Any]]:
        with self._lock:
            expired = [scope for scope, lease in self._leases.items() if lease.expires_tick < tick]
            for scope in expired:
                self._leases.pop(scope, None)
            return [lease.as_dict() for lease in sorted(self._leases.values(), key=lambda item: item.scope)]


@dataclass
class ActionGoal:
    goal_id: str
    proposal_id: str
    instruction: str
    summary: str
    owner: BrainOwner
    scope: str
    commands: tuple[ActionCommand, ...]
    fingerprint: str
    created_tick: int
    baseline: dict[str, Any]
    automatic: bool
    status: GoalStatus = GoalStatus.PROPOSED
    attempts: int = 0
    accepted_tick: int = 0
    updated_tick: int = 0
    verify_deadline_tick: int = 0
    last_error: str = ""
    verification: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "proposal_id": self.proposal_id,
            "instruction": self.instruction,
            "summary": self.summary,
            "owner": self.owner.value,
            "scope": self.scope,
            "commands": [command.as_dict() for command in self.commands],
            "fingerprint": self.fingerprint,
            "created_tick": self.created_tick,
            "updated_tick": self.updated_tick,
            "accepted_tick": self.accepted_tick,
            "verify_deadline_tick": self.verify_deadline_tick,
            "automatic": self.automatic,
            "status": self.status.value,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "verification": self.verification,
            "created_at": self.created_at,
            "baseline": self.baseline,
        }


class GoalBlackboard:
    """Tracks accepted action intent until a later snapshot proves its effect."""

    def __init__(
        self,
        *,
        verify_timeout_ticks: int = 250,
        max_attempts: int = 3,
        journal_path: Path | None = None,
    ) -> None:
        self.verify_timeout_ticks = max(25, verify_timeout_ticks)
        self.max_attempts = max(1, max_attempts)
        self._goals: dict[str, ActionGoal] = {}
        self._proposal_goals: dict[str, str] = {}
        self._recent: deque[str] = deque(maxlen=80)
        self._match_key: tuple[str, int, int] | None = None
        self._lock = threading.Lock()
        self.journal_path = journal_path
        if self.journal_path is not None:
            self._restore_journal()

    def _restore_journal(self) -> None:
        if self.journal_path is None or not self.journal_path.exists():
            return
        latest: dict[str, dict[str, Any]] = {}
        try:
            for line in self.journal_path.read_text(encoding="utf-8").splitlines()[-1000:]:
                value = json.loads(line)
                goal = value.get("goal")
                if isinstance(goal, dict) and goal.get("goal_id"):
                    latest[str(goal["goal_id"])] = goal
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return
        for value in latest.values():
            try:
                status = GoalStatus(str(value.get("status", GoalStatus.FAILED.value)))
                last_error = str(value.get("last_error", ""))
                if status not in TERMINAL_GOAL_STATES:
                    status = GoalStatus.FAILED
                    last_error = "companion restarted before this action was verified"
                commands = tuple(ActionCommand.from_dict(item) for item in value.get("commands", []))
                goal = ActionGoal(
                    goal_id=str(value["goal_id"]),
                    proposal_id=str(value.get("proposal_id", "")),
                    instruction=str(value.get("instruction", "")),
                    summary=str(value.get("summary", "")),
                    owner=BrainOwner(str(value.get("owner", BrainOwner.USER.value))),
                    scope=str(value.get("scope", command_scope(commands))),
                    commands=commands,
                    fingerprint=str(value.get("fingerprint", command_fingerprint(commands))),
                    created_tick=int(value.get("created_tick", 0)),
                    baseline=dict(value.get("baseline", {})),
                    automatic=bool(value.get("automatic", False)),
                    status=status,
                    attempts=int(value.get("attempts", 0)),
                    accepted_tick=int(value.get("accepted_tick", 0)),
                    updated_tick=int(value.get("updated_tick", 0)),
                    verify_deadline_tick=int(value.get("verify_deadline_tick", 0)),
                    last_error=last_error,
                    verification=list(value.get("verification", [])),
                    created_at=float(value.get("created_at", time.time())),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._goals[goal.goal_id] = goal
            if goal.proposal_id:
                self._proposal_goals[goal.proposal_id] = goal.goal_id
            self._recent.append(goal.goal_id)

    def _persist(self, goal: ActionGoal, event: str) -> None:
        if self.journal_path is None:
            return
        try:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "event": event,
                "recorded_at": time.time(),
                "goal": goal.as_dict(),
            }
            with self.journal_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, separators=(",", ":")) + "\n")
        except OSError:
            pass

    @staticmethod
    def _match(snapshot: GameSnapshot) -> tuple[str, int, int]:
        return snapshot.map_name, snapshot.map_width, snapshot.map_height

    def reset_for(self, snapshot: GameSnapshot) -> None:
        match = self._match(snapshot)
        with self._lock:
            if self._match_key is None:
                self._match_key = match
                return
            if match == self._match_key:
                return
            for goal in self._goals.values():
                if goal.status not in TERMINAL_GOAL_STATES:
                    goal.status = GoalStatus.SUPERSEDED
                    goal.last_error = "match changed before the action effect was verified"
                    self._persist(goal, "match-superseded")
            self._match_key = match

    def register(
        self,
        proposal: ActionProposal,
        snapshot: GameSnapshot,
        owner: BrainOwner,
        *,
        automatic: bool,
    ) -> ActionGoal:
        fingerprint = command_fingerprint(proposal.commands)
        with self._lock:
            existing_id = self._proposal_goals.get(proposal.proposal_id)
            if existing_id is not None:
                return self._goals[existing_id]
            goal = ActionGoal(
                goal_id=str(uuid.uuid4()),
                proposal_id=proposal.proposal_id,
                instruction=proposal.instruction,
                summary=proposal.summary,
                owner=owner,
                scope=command_scope(proposal.commands),
                commands=proposal.commands,
                fingerprint=fingerprint,
                created_tick=snapshot.tick,
                updated_tick=snapshot.tick,
                baseline=_snapshot_baseline(snapshot, proposal.commands),
                automatic=automatic,
            )
            self._goals[goal.goal_id] = goal
            self._proposal_goals[proposal.proposal_id] = goal.goal_id
            self._recent.append(goal.goal_id)
            self._persist(goal, "registered")
            return goal

    def mark_dispatched(self, proposal_id: str, tick: int) -> None:
        with self._lock:
            goal = self._by_proposal(proposal_id)
            if goal is None:
                return
            goal.status = GoalStatus.DISPATCHED
            goal.attempts += 1
            goal.updated_tick = tick
            self._persist(goal, "dispatched")

    def apply_receipt(self, receipt: ActionReceipt) -> None:
        with self._lock:
            goal = self._by_proposal(receipt.request_id)
            if goal is None:
                return
            goal.updated_tick = receipt.game_tick
            if receipt.accepted:
                goal.status = GoalStatus.VERIFYING
                goal.accepted_tick = receipt.game_tick
                goal.verify_deadline_tick = receipt.game_tick + self.verify_timeout_ticks
                goal.last_error = ""
                self._persist(goal, "receipt-accepted")
            else:
                self._retry_or_fail(goal, receipt.game_tick, receipt.detail or "engine rejected the action")

    def cancel(self, proposal_id: str, tick: int, reason: str = "cancelled by player") -> None:
        with self._lock:
            goal = self._by_proposal(proposal_id)
            if goal is None:
                return
            goal.status = GoalStatus.CANCELLED
            goal.updated_tick = tick
            goal.last_error = reason
            self._persist(goal, "cancelled")

    def fail(self, proposal_id: str, tick: int, reason: str) -> None:
        with self._lock:
            goal = self._by_proposal(proposal_id)
            if goal is not None:
                self._retry_or_fail(goal, tick, reason)

    def _by_proposal(self, proposal_id: str) -> ActionGoal | None:
        goal_id = self._proposal_goals.get(proposal_id)
        return self._goals.get(goal_id) if goal_id is not None else None

    def _retry_or_fail(self, goal: ActionGoal, tick: int, reason: str) -> None:
        goal.updated_tick = tick
        goal.last_error = reason
        goal.status = (
            GoalStatus.RETRY_READY
            if goal.automatic and goal.attempts < self.max_attempts
            else GoalStatus.FAILED
        )
        self._persist(goal, "retry-ready" if goal.status == GoalStatus.RETRY_READY else "failed")

    def has_active_commands(self, commands: Iterable[ActionCommand]) -> bool:
        fingerprint = command_fingerprint(commands)
        with self._lock:
            return any(
                goal.fingerprint == fingerprint
                and goal.status in {GoalStatus.DISPATCHED, GoalStatus.VERIFYING, GoalStatus.RETRY_READY}
                for goal in self._goals.values()
            )

    def next_retry(self) -> ActionGoal | None:
        with self._lock:
            candidates = [
                goal for goal in self._goals.values()
                if goal.status == GoalStatus.RETRY_READY and goal.automatic
            ]
            return min(candidates, key=lambda goal: (-OWNER_PRIORITY[goal.owner], goal.updated_tick), default=None)

    def bind_retry(self, goal_id: str, proposal: ActionProposal, snapshot: GameSnapshot) -> ActionGoal | None:
        with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None or goal.status != GoalStatus.RETRY_READY:
                return None
            self._proposal_goals.pop(goal.proposal_id, None)
            goal.proposal_id = proposal.proposal_id
            goal.baseline = _snapshot_baseline(snapshot, proposal.commands)
            goal.updated_tick = snapshot.tick
            goal.status = GoalStatus.PROPOSED
            self._proposal_goals[proposal.proposal_id] = goal.goal_id
            self._persist(goal, "retry-bound")
            return goal

    def reconcile(self, snapshot: GameSnapshot) -> list[ActionGoal]:
        self.reset_for(snapshot)
        changed: list[ActionGoal] = []
        with self._lock:
            for goal in self._goals.values():
                if goal.status != GoalStatus.VERIFYING:
                    continue
                checks = [self._command_satisfied(command, goal.baseline, snapshot) for command in goal.commands]
                goal.verification = [
                    {"command": command.action, "satisfied": satisfied, "evidence": evidence}
                    for command, (satisfied, evidence) in zip(goal.commands, checks)
                ]
                goal.updated_tick = snapshot.tick
                if all(satisfied for satisfied, _ in checks):
                    goal.status = GoalStatus.SUCCEEDED
                    self._persist(goal, "verified-succeeded")
                    changed.append(goal)
                elif snapshot.done:
                    goal.status = GoalStatus.FAILED
                    goal.last_error = "match ended before the action effect was verified"
                    self._persist(goal, "match-ended-failed")
                    changed.append(goal)
                elif snapshot.tick >= goal.verify_deadline_tick:
                    self._retry_or_fail(goal, snapshot.tick, "no observable effect before verification deadline")
                    changed.append(goal)
        return changed

    @staticmethod
    def _command_satisfied(
        command: ActionCommand,
        baseline: dict[str, Any],
        snapshot: GameSnapshot,
    ) -> tuple[bool, str]:
        units = {actor.actor_id: actor for actor in snapshot.units}
        buildings = {actor.actor_id: actor for actor in snapshot.buildings}
        actors = units | buildings
        observable_targets = actors | {
            actor.actor_id: actor
            for actor in (*snapshot.visible_enemies, *snapshot.visible_enemy_buildings)
        }
        actor = actors.get(command.actor_id)
        target = observable_targets.get(command.target_actor_id)
        before_actor = baseline.get("actors", {}).get(str(command.actor_id), {})
        production = [_kind(str(item.get("item", ""))) for item in snapshot.production]
        item = _kind(command.item_type)
        unit_counts = Counter(_kind(value.kind) for value in snapshot.units)
        building_counts = Counter(_kind(value.kind) for value in snapshot.buildings)
        before_units = baseline.get("unit_counts", {})
        before_buildings = baseline.get("building_counts", {})

        if command.action == "build":
            ok = item in production or building_counts[item] > int(before_buildings.get(item, 0))
            return ok, "construction entered the queue or completed" if ok else "construction is not visible"
        if command.action == "train":
            ok = item in production or unit_counts[item] > int(before_units.get(item, 0))
            return ok, "training entered the queue or completed" if ok else "training is not visible"
        if command.action == "place_building":
            ok = building_counts[item] > int(before_buildings.get(item, 0)) or item not in production
            return ok, "completed structure left the queue or appeared on the map" if ok else "structure remains unplaced"
        if command.action == "cancel_production":
            ok = item not in production
            return ok, "production item is absent" if ok else "production item remains queued"
        if command.action == "use_support_power":
            ready = {
                str(power.get("key", "")).lower(): bool(power.get("ready", False))
                for power in snapshot.support_powers
            }
            was_ready = bool(baseline.get("support_powers", {}).get(command.item_type.lower(), False))
            ok = was_ready and not ready.get(command.item_type.lower(), False)
            return ok, "support power entered its recharge cycle" if ok else "support power remains ready"
        if command.action == "sell":
            return actor is None, "actor left the battlefield" if actor is None else "actor still exists"
        if command.action == "repair":
            before_hp = float(before_actor.get("hp", 0))
            ok = actor is not None and (actor.repairing or actor.hp_percent > before_hp)
            return ok, "repair state or health increased" if ok else "repair has not started"
        if command.action == "power_down":
            ok = actor is not None and actor.powered != bool(before_actor.get("powered", True))
            return ok, "power state changed" if ok else "power state is unchanged"
        if command.action == "set_rally_point":
            ok = actor is not None and (actor.rally_x, actor.rally_y) == (command.target_x, command.target_y)
            return ok, "rally point matches the requested cell" if ok else "rally point is unchanged"
        if command.action == "disguise":
            ok = actor is not None and actor.is_disguised
            return ok, "unit is disguised" if ok else "unit is not disguised"
        if command.action == "enter_transport":
            before = baseline.get("actors", {}).get(str(command.target_actor_id), {})
            ok = target is not None and target.passenger_count > int(before.get("passengers", -1))
            return ok, "transport passenger count increased" if ok else "passenger has not entered"
        if command.action == "unload":
            ok = actor is not None and actor.passenger_count < int(before_actor.get("passengers", actor.passenger_count))
            return ok, "transport passenger count decreased" if ok else "transport remains loaded"
        if command.action == "deploy":
            ok = actor is None or building_counts["fact"] > int(before_buildings.get("fact", 0))
            return ok, "deployable transformed into a structure" if ok else "deployable has not transformed"
        if command.action == "capture":
            ok = command.target_actor_id in buildings or command.target_actor_id in units
            return ok, "capture target is now owned by the player" if ok else "capture target is not yet owned"
        if command.action == "infiltrate":
            ok = actor is None or target is None
            return ok, "infiltration consumed the infiltrator or target" if ok else "infiltration is not yet complete"
        if command.action == "demolish":
            before_target = baseline.get("actors", {}).get(str(command.target_actor_id), {})
            ok = target is None or target.hp_percent < float(before_target.get("hp", target.hp_percent))
            return ok, "demolition damaged or removed the target" if ok else "demolition has no visible effect"
        if command.action == "stop":
            ok = actor is not None and actor.idle
            return ok, "unit is idle" if ok else "unit is still active"
        if command.action == "set_stance":
            ok = actor is not None and actor.stance == command.target_x
            return ok, "unit stance matches the requested setting" if ok else "unit stance is unchanged"
        if command.action == "attack":
            before_target = baseline.get("actors", {}).get(str(command.target_actor_id), {})
            ok = actor is not None and actor.current_target_actor_id == command.target_actor_id
            ok = ok or (
                target is not None and target.hp_percent < float(before_target.get("hp", target.hp_percent))
            )
            return ok, "attacker acquired or damaged the requested target" if ok else "attack target is not acquired"
        if actor is None:
            return False, "command actor no longer exists"
        moved = [actor.cell_x, actor.cell_y] != before_actor.get("cell")
        has_requested_move_target = (
            command.action in {"move", "attack_move", "harvest"}
            and (actor.move_target_x, actor.move_target_y) == (command.target_x, command.target_y)
        )
        activity_changed = actor.current_activity != str(before_actor.get("activity", ""))
        idle_changed = actor.idle != bool(before_actor.get("idle", actor.idle))
        ok = moved or has_requested_move_target or activity_changed or idle_changed
        return ok, "the commanded actor changed state" if ok else "no actor-specific command effect is visible"

    def state(self, snapshot: GameSnapshot | None = None) -> dict[str, Any]:
        tick = snapshot.tick if snapshot is not None else 0
        with self._lock:
            active = [
                goal.as_dict() for goal in self._goals.values()
                if goal.status not in TERMINAL_GOAL_STATES
            ]
            recent = [self._goals[goal_id].as_dict() for goal_id in self._recent if goal_id in self._goals][-20:]
        counts = Counter(item["status"] for item in recent)
        return {
            "tick": tick,
            "active": active,
            "recent": recent,
            "status_counts": dict(sorted(counts.items())),
            "verification_timeout_ticks": self.verify_timeout_ticks,
            "max_attempts": self.max_attempts,
        }
