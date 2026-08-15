from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections.abc import Callable

from .brain import BrainArbiter, BrainOwner, GoalBlackboard, default_blackboard_path
from .controller import TacticalController, controller_state
from .insights import InsightEngine
from .labels import building_name, humanize_text, production_name, unit_name
from .models import (
    ACTOR_ACTIONS,
    ITEM_ACTIONS,
    POSITION_ACTIONS,
    TARGET_ACTOR_ACTIONS,
    ActionCommand,
    ActionProposal,
    ActionReceipt,
    CompanionResponse,
    GameSnapshot,
    Insight,
    ThreatAssessment,
    VisionFrame,
)
from .router import AIRouter, RouterError, RouterResult
from .strategy import (
    base_center,
    desired_harvester_count,
    hybrid_force_plan,
    map_scale,
    maximum_queued_unit_count,
    maximum_silo_count,
    mission_plan,
    opening_scout_count,
    rally_target,
    scout_targets,
    tactical_plan,
)
from .strategy_contracts import (
    STRATEGY_CONTRACTS,
    detect_strategy_intent,
    strategy_answer,
    strategy_contract,
    strategy_state,
)
from .tactical_vision import tactical_overview_png
from .threats import assess_threat

SYSTEM_PROMPT = """You are a calm battlefield companion inside OpenRA, a classic RTS.
Speak in one short sentence, under 22 words. Mention only facts in the supplied fog-respecting snapshot.
Visible enemies are current contacts. Remembered enemy buildings are last-known structures under fog; never claim they are unknown or currently visible.
Explored percent is cumulative map knowledge. Power balance is the same net value shown beside the lightning icon; never invent or quote supply/usage totals.
Treat production countdowns as transient: never quote raw tick counts or imply that an old countdown is still current.
Never expose internal actor type IDs such as e1, proc, or 2tnk; use player-facing unit and building names.
Prioritize an actionable observation. Never say you are assessing or analyzing; answer directly from the supplied state.
Never claim to control units. Never use markdown, greetings, or filler."""

MISSION_DESIGN_PROMPT = """You are an expert OpenRA mission designer working inside the native map editor.
Return one vivid, playable mission direction under 34 words. Ground it in the supplied Earth location, map metrics, and requested archetype.
Include a concrete objective and one tactical twist. Keep real places fictionalized and avoid claims about real people or current events.
Do not use markdown, labels, greetings, or quotation marks."""

TERRAIN_ANALYSIS_PROMPT = """You are the terrain intelligence layer for an Earth-to-OpenRA map generator.
The attached image is the exact satellite or terrain reconnaissance view selected by the player. Treat visible relief, water,
vegetation, settlement texture, and major corridors as evidence. Reconcile it with the supplied OpenStreetMap
feature counts. Never invent water or landmarks. Return only one compact JSON object with these keys:
biome (desert|temperate|snow), relief (flat|rolling|mountainous), vegetation_density (0..1),
urban_density (0..1), water_confidence (0..1), fidelity_notes (array of at most 3 short strings),
summary (one short sentence), confidence (0..1)."""

ACTION_PROMPT = """You are a safe command interpreter for a human playing OpenRA.
Return exactly one compact JSON object and no markdown.

For questions, advice, observations, ambiguous requests, or anything outside the allowlist, return:
{"mode":"answer","answer":"one short sentence under 22 words"}

For a clear request to control the player's army, return:
{"mode":"action","summary":"short description","commands":[...]}

Allowed command objects:
- {"action":"train"|"build","item_type":"exact available_production id"}
- {"action":"stop"|"harvest"|"deploy"|"unload"|"set_stance","actor_id":owned_unit_id}
- {"action":"repair"|"sell"|"power_down"|"set_primary","actor_id":owned_building_id}
- {"action":"move"|"attack_move","actor_id":owned_unit_id,"target_x":int,"target_y":int,"queued":false}
- {"action":"attack","actor_id":owned_attacker_id,"target_actor_id":visible_enemy_actor_id}
- {"action":"guard","actor_id":owned_unit_id,"target_actor_id":owned_actor_id}
- {"action":"enter_transport","actor_id":owned_passenger_id,"target_actor_id":owned_transport_id}
- {"action":"disguise","actor_id":owned_spy_id,"target_actor_id":valid_disguise_target_id}
- {"action":"infiltrate","actor_id":owned_spy_id,"target_actor_id":valid_infiltration_target_id,"queued":false}
- {"action":"demolish","actor_id":owned_demolition_unit_id,"target_actor_id":valid_demolition_target_id}
- {"action":"capture","actor_id":owned_engineer_id,"target_actor_id":valid_capture_target_id}
- {"action":"set_rally_point","actor_id":owned_building_id,"target_x":int,"target_y":int}
- {"action":"place_building","item_type":"exact completed production id","target_x":optional_int,"target_y":optional_int}
- {"action":"cancel_production","item_type":"exact queued production id"}
- {"action":"use_support_power","item_type":"exact ready support_powers key","target_x":int,"target_y":int}

Use only actor ids and facts supplied in the snapshot. Coordinates must be inside the map. Never target remembered or hidden enemies.
Create one command per actor or production item, with at most 12 commands. Never sell, surrender, cancel production, power down,
attack a specific actor, spend resources speculatively, or invent an actor or item id. Use support powers only when explicitly requested by the player.
An action is only a proposal; never say it already happened. Never expose internal type IDs in the answer or summary.
Use player-facing `display_name` values. If the requested target or units are unclear, ask one concise question."""

CONFIRM_WORDS = frozenset({"confirm", "confirmed", "yes", "do it", "execute", "go ahead", "proceed"})
CANCEL_WORDS = frozenset({"cancel", "never mind", "nevermind", "stop", "discard"})
ACTION_EXPIRY_SECONDS = 300.0
AUTO_ACTION_INSTRUCTION = """Autonomous commander mode is enabled. Inspect the battlefield with MCP tools and issue one immediately useful batch of legal orders toward winning. In scripted missions, follow mission_plan and the live objectives before skirmish economy logic; preserve required heroes, avoid dog detectors, and restrict disguise, infiltration, capture, and C4 to listed valid targets. Otherwise prioritize completed building placement, economy, production, scouting, defense, then concentrated attacks. Act instead of merely advising; return no commands only when no useful legal order exists."""


def _normalized_action_intent(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _is_cancel_intent(text: str) -> bool:
    normalized = _normalized_action_intent(text)
    if normalized in CANCEL_WORDS or normalized in {"no", "nope", "don t", "do not"}:
        return True
    return any(phrase in f" {normalized} " for phrase in (
        " cancel ",
        " never mind ",
        " do not confirm ",
        " don t confirm ",
        " do not execute ",
        " don t execute ",
    ))


def _is_confirm_intent(text: str) -> bool:
    normalized = _normalized_action_intent(text)
    if _is_cancel_intent(normalized):
        return False
    if normalized in CONFIRM_WORDS or normalized in {
        "ok", "okay", "sure", "yep", "yeah", "confirm it", "execute it", "please do it",
    }:
        return True
    words = set(normalized.split())
    return bool(words & {"confirm", "confirmed", "execute", "proceed"}) or any(
        phrase in f" {normalized} " for phrase in (" do it ", " go ahead ")
    )


def _is_scout_request(text: str) -> bool:
    normalized = _normalized_action_intent(text)
    return (
        any(word in normalized.split() for word in ("scout", "scouts", "recon", "reconnaissance"))
        and any(word in normalized.split() for word in (
            "can", "create", "build", "make", "send", "move", "order", "train", "use", "please",
        ))
    )


def _is_action_failure_followup(text: str) -> bool:
    normalized = _normalized_action_intent(text)
    return any(phrase in normalized for phrase in (
        "couldn t form a safe action",
        "could not form a safe action",
        "what do you mean you couldn t",
        "what do you mean you could not",
        "why couldn t you do",
        "why could not you do",
    ))


def _is_unhelpful_player_answer(text: str) -> bool:
    normalized = _normalized_action_intent(text)
    return not normalized or any(phrase in normalized for phrase in (
        "i am assessing",
        "i m assessing",
        "analyzing battlefield",
        "analysing battlefield",
        "i need more information",
        "i need a more specific objective",
        "couldn t form a safe action",
        "could not form a safe action",
    ))

FULL_VISION_PROMPT = """Use the supplied visual views together with the structured snapshot.
The rendered viewport is exactly what the player can currently see, including fog and UI.
The tactical overview covers the entire map: dark cells are hidden, cyan/blue are owned assets, red/orange are currently visible enemies, and gold is explored ore.
Never infer enemies, resources, or targets in dark cells. For actions, actor ids and coordinates must come from the structured snapshot, never pixels alone."""

# These alerts are complete factual sentences generated from local game state.
# Model paraphrasing adds cost without adding information.
LOCAL_ALERT_KEYS = {
    "critical_damage",
    "economy_idle",
    "economy_recovered",
    "game_over",
    "low_power",
    "mission_objective_updated",
    "mission_started",
    "mission_step_ready",
    "no_harvester",
    "opening_deploy",
    "power_restored",
    "situation_update",
    "storage_pressure",
}


def _storage_needs_silo(snapshot: GameSnapshot) -> bool:
    if snapshot.resource_capacity <= 0 or snapshot.ore * 100 <= snapshot.resource_capacity * 80:
        return False
    silo_count = sum(
        building.kind.lower().split(".", 1)[0] == "silo"
        for building in snapshot.buildings
    )
    return silo_count < maximum_silo_count(snapshot) and not any(
        str(item.get("item", "")).lower().split(".", 1)[0] == "silo"
        for item in snapshot.production
    )


class Companion:
    def __init__(
        self,
        router: AIRouter | None = None,
        insights: InsightEngine | None = None,
        action_executor: Callable[[str, int, tuple[ActionCommand, ...]], ActionReceipt] | None = None,
    ):
        self.router = router or AIRouter()
        self.insights = insights or InsightEngine()
        if insights is None:
            self.insights.configure_pace(self.router.settings.notification_pace)
        self.latest_snapshot: GameSnapshot | None = None
        self.enabled = self.router.settings.companion_enabled
        self.muted = not self.router.settings.voice_enabled
        self.auto_act_enabled = self.router.settings.auto_act_enabled
        self.native_strategy = self.router.settings.native_strategy
        self.native_profile = strategy_contract(self.native_strategy)["native_profile"]
        self._generation = 0
        self._lock = threading.Lock()
        self._action_lock = threading.Lock()
        self._pending_action: ActionProposal | None = None
        self._action_executor = action_executor
        self._action_planner: Callable[[str], dict] | None = None
        self._strategy_controller: Callable[[str], bool] | None = None
        self.native_brain_available = False
        self._snapshot_provider: Callable[[], GameSnapshot] | None = None
        self._frame_provider: Callable[[], VisionFrame] | None = None
        self._vision_lock = threading.Lock()
        self._event_lock = threading.Lock()
        self._pending_event_context: dict | None = None
        self._user_turn_lock = threading.Lock()
        self._user_turn_depth = 0
        self._user_reply_protected_until = 0.0
        self._last_vision_error = ""
        self._display_enemy_signature: tuple[tuple[int, ...], tuple[int, ...]] | None = None
        self.current_threat = ThreatAssessment()
        self._opening_scout_ids: set[int] = set()
        self._opening_scout_targets: set[tuple[int, int]] = set()
        self._opening_scouts_committed = 0
        self.brain_arbiter = BrainArbiter()
        self.goal_blackboard = GoalBlackboard(journal_path=default_blackboard_path())
        self.tactical_controller = TacticalController()
        self._goal_updates: list[dict] = []

    def _begin(self) -> int:
        with self._lock:
            self._generation += 1
            return self._generation

    def interrupt(self) -> int:
        """Invalidate in-flight speech/text immediately; provider work may finish but is discarded."""
        with self._lock:
            self._generation += 1
            return self._generation

    def _interrupted(self, generation: int) -> bool:
        with self._lock:
            return generation != self._generation

    def begin_user_turn(self) -> None:
        """Give a player prompt priority over every automatic battlefield response."""
        with self._user_turn_lock:
            self._user_turn_depth += 1
            self._user_reply_protected_until = 0.0
        # Cancel event/model work that may already be in flight before the player spoke.
        self.interrupt()

    def end_user_turn(self, *, grace_seconds: float = 0.75) -> None:
        """Release the player lane after its answer has finished displaying/speaking."""
        with self._user_turn_lock:
            self._user_turn_depth = max(0, self._user_turn_depth - 1)
            if self._user_turn_depth == 0:
                self._user_reply_protected_until = max(
                    self._user_reply_protected_until,
                    time.monotonic() + max(0.0, grace_seconds),
                )

    @property
    def user_turn_active(self) -> bool:
        with self._user_turn_lock:
            return (
                self._user_turn_depth > 0
                or time.monotonic() < self._user_reply_protected_until
            )

    def configure(
        self,
        *,
        enabled: bool | None = None,
        muted: bool | None = None,
        auto_act: bool | None = None,
        native_strategy: str | None = None,
        persist: bool = False,
    ) -> dict[str, bool | str]:
        if enabled is not None:
            self.enabled = enabled
            if not enabled:
                self.interrupt()
                with self._action_lock:
                    self._pending_action = None
        if muted is not None:
            self.muted = muted
            if muted:
                self.interrupt()
        if auto_act is not None:
            self.auto_act_enabled = bool(auto_act)
            if not self.auto_act_enabled:
                self.interrupt()
        if native_strategy is not None:
            strategy = native_strategy.strip().lower()
            if strategy not in STRATEGY_CONTRACTS:
                raise ValueError("native strategy must be adaptive, normal, rush, turtle, naval, or medium")
            self.native_strategy = strategy
            self.native_profile = strategy_contract(strategy)["native_profile"]
        if persist:
            self.router.configure({
                "companion_enabled": self.enabled,
                "voice_enabled": not self.muted,
                "auto_act_enabled": self.auto_act_enabled,
                "native_strategy": self.native_strategy,
            })
        return {
            "enabled": self.enabled,
            "muted": self.muted,
            "auto_act": self.auto_act_enabled,
            "native_strategy": self.native_strategy,
        }

    def apply_settings(self) -> None:
        settings = self.router.settings
        self.configure(
            enabled=settings.companion_enabled,
            muted=not settings.voice_enabled,
            auto_act=settings.auto_act_enabled,
            native_strategy=settings.native_strategy,
        )
        self.insights.configure_pace(settings.notification_pace)

    def should_speak(self, insight: Insight | None) -> bool:
        if not insight or self.muted or not self.enabled:
            return False
        threshold = self.router.settings.voice_priority
        if threshold == "off":
            return False
        if threshold == "important":
            return insight.importance in {"important", "critical"}
        return insight.importance == "critical"

    @staticmethod
    def _enemy_signature(snapshot: GameSnapshot) -> tuple[tuple[int, ...], tuple[int, ...]]:
        return (
            tuple(sorted(unit.actor_id for unit in snapshot.visible_enemies)),
            tuple(sorted(building.actor_id for building in snapshot.visible_enemy_buildings)),
        )

    def idle_status(self, snapshot: GameSnapshot | None = None) -> tuple[str, str]:
        if not self.enabled:
            return "disabled", "AI OFF  •  ENABLE THE COMPANION IN SETTINGS"
        if self.auto_act_enabled:
            active_snapshot = snapshot or self.latest_snapshot
            if active_snapshot is not None and active_snapshot.mission_mode:
                return f"auto-active:{self.native_profile}", "AUTO ASSISTANT ON  •  SCRIPTED MISSION BRAIN"
            name = strategy_contract(self.native_strategy)["name"].upper()
            profile = self.native_profile.upper()
            return f"auto-active:{self.native_profile}", f"AUTO ASSISTANT ON  •  {name}  •  {profile} NATIVE BRAIN"
        if self.muted:
            return "muted", "AI VOICE OFF  •  TEXT INSIGHTS STAY ON"
        return f"ready:{self.native_profile}", "AI READY  •  HOLD ASK KEY TO SPEAK OR SET STRATEGY"

    def update_snapshot(self, snapshot: GameSnapshot) -> ThreatAssessment:
        previous = self.latest_snapshot
        match_changed = previous is not None and (
            snapshot.tick < previous.tick
            or snapshot.map_name != previous.map_name
            or snapshot.map_width != previous.map_width
            or snapshot.map_height != previous.map_height
        )
        if match_changed:
            self._opening_scout_ids.clear()
            self._opening_scout_targets.clear()
            self._opening_scouts_committed = 0
            self.brain_arbiter = BrainArbiter()
        self.latest_snapshot = snapshot
        updates = self.goal_blackboard.reconcile(snapshot)
        self._goal_updates = [goal.as_dict() for goal in updates]
        for goal in updates:
            if goal.status.value in {"succeeded", "failed", "cancelled", "superseded"}:
                self.brain_arbiter.release(goal.scope, goal.owner)
        self.current_threat = assess_threat(snapshot)
        return self.current_threat

    def brain_state(self) -> dict:
        snapshot = self.latest_snapshot
        tick = snapshot.tick if snapshot is not None else 0
        return {
            "owner": (
                "mission" if snapshot is not None and snapshot.mission_mode and self.auto_act_enabled
                else "native" if self.auto_act_enabled and self.native_brain_available
                else "user"
            ),
            "goals": self.goal_blackboard.state(snapshot),
            "leases": self.brain_arbiter.state(tick),
            "latest_goal_updates": self._goal_updates,
            "controller": controller_state(snapshot, self.native_profile) if snapshot is not None else None,
        }

    def threat_status(self) -> dict:
        return self.current_threat.as_dict()

    def set_frame_provider(self, provider: Callable[[], VisionFrame] | None) -> None:
        with self._vision_lock:
            self._frame_provider = provider

    def _vision_inputs(self, snapshot: GameSnapshot) -> tuple[list[tuple[bytes, str]], list[dict]]:
        images: list[tuple[bytes, str]] = []
        views: list[dict] = []
        with self._vision_lock:
            provider = self._frame_provider
            if provider is not None:
                try:
                    frame = provider()
                    images.append((frame.png, "image/png"))
                    views.append({"order": len(images), **frame.metadata()})
                    self._last_vision_error = ""
                except RuntimeError as exc:
                    self._last_vision_error = str(exc)

        overview = tactical_overview_png(snapshot)
        if overview is not None:
            images.append((overview, "image/png"))
            views.append({
                "order": len(images),
                "tick": snapshot.tick,
                "width": snapshot.map_width,
                "height": snapshot.map_height,
                "scope": "full-map-tactical-overview-fog-respecting",
            })
        return images, views

    def _render_insight(
        self,
        snapshot: GameSnapshot,
        insight: Insight,
        threat: ThreatAssessment,
        generation: int,
    ) -> CompanionResponse:
        started = time.perf_counter()
        if not self.enabled:
            return CompanionResponse("", "disabled", utterance_id=generation, insight=insight)
        if insight.key in LOCAL_ALERT_KEYS or insight.key.startswith("production_complete:"):
            return CompanionResponse(
                insight.fallback_text,
                "deterministic-local",
                utterance_id=generation,
                insight=insight,
                latency_ms=round((time.perf_counter() - started) * 1000),
                metadata={"model": "none", "local": True},
            )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps({"reason_to_speak": insight.fact, "snapshot": snapshot.compact()}, separators=(",", ":")),
            },
        ]
        try:
            images, views = self._vision_inputs(snapshot) if threat.heated else ([], [])
            if images:
                result = self.router.vision_many(
                    SYSTEM_PROMPT + "\n" + FULL_VISION_PROMPT + "\nCONTEXT:\n" +
                    json.dumps({"reason_to_speak": insight.fact, "snapshot": snapshot.compact(), "vision_views": views}, separators=(",", ":")),
                    images,
                )
            else:
                result = self.router.chat(messages)
            metadata = {"model": result.model}
            if views:
                metadata["vision"] = {
                    "used": result.vision_used,
                    "views": views,
                    "fallback": None if result.vision_used else "structured-context",
                }
            response = CompanionResponse(humanize_text(result.text), "ai-layer", utterance_id=generation, insight=insight, latency_ms=result.latency_ms, metadata=metadata)
        except RouterError as exc:
            response = CompanionResponse(insight.fallback_text, "deterministic-fallback", utterance_id=generation, insight=insight, latency_ms=round((time.perf_counter() - started) * 1000), metadata={"degraded": True, "reason": str(exc)})
        if self._interrupted(generation):
            response.text = ""
            response.interrupted = True
        return response

    def observe(self, snapshot: GameSnapshot) -> CompanionResponse | None:
        threat = self.update_snapshot(snapshot)
        insight = self.insights.select(snapshot, threat=threat)
        event_insight = self.insights.last_event
        event_context = self._event_context(snapshot, event_insight, threat) if event_insight else None
        if event_context is not None:
            with self._event_lock:
                self._pending_event_context = event_context
        # Events are still detected and retained, but cannot start a generation or
        # replace the HUD while a player question or its answer owns the conversation.
        if self.user_turn_active:
            return None
        if not insight:
            if self._display_enemy_signature is not None and self._display_enemy_signature != self._enemy_signature(snapshot):
                self._display_enemy_signature = None
                self.interrupt()
                return CompanionResponse("", "state-refresh", metadata={"clear": True})
            return None
        generation = self._begin()
        response = self._render_insight(snapshot, insight, threat, generation)
        if event_context is not None and event_insight == insight:
            response.metadata["event"] = event_context
        if not (self.native_brain_available and self.auto_act_enabled):
            self._attach_contextual_suggestion(response, snapshot, insight, threat)
        action = response.metadata.get("action")
        if action and "event" in response.metadata:
            response.metadata["event"]["direct_action"] = action
        self._display_enemy_signature = self._enemy_signature(snapshot)
        return response

    def take_event_context(self) -> dict | None:
        """Consume the newest event wake-up independently of the UI message budget."""
        if self.user_turn_active:
            return None
        with self._event_lock:
            event = self._pending_event_context
            self._pending_event_context = None
        return event

    def _event_context(
        self,
        snapshot: GameSnapshot,
        insight: Insight,
        threat: ThreatAssessment,
    ) -> dict:
        """Package a priority event with the fresh state needed to act on it."""
        return {
            "type": insight.key,
            "tick": snapshot.tick,
            "fact": insight.fact,
            "importance": insight.importance,
            "threat": threat.as_dict(),
            "battlefield": snapshot.action_context(),
            "assistant_strategy": {
                **strategy_state(snapshot, self.native_strategy, native_active=self.auto_act_enabled),
                "active_native_profile": self.native_profile,
            },
            "force_plan": hybrid_force_plan(snapshot),
            "tactical_plan": tactical_plan(snapshot),
            "controller": controller_state(snapshot, self.native_profile),
            "planner_instruction": "Re-read the live battlefield through MCP immediately before issuing orders.",
            **({
                "storage": {
                    "percent": round(snapshot.ore / snapshot.resource_capacity * 100, 1)
                    if snapshot.resource_capacity else 0,
                    "ore": snapshot.ore,
                    "capacity": snapshot.resource_capacity,
                    "current_silos": sum(
                        building.kind.lower().split(".", 1)[0] == "silo"
                        for building in snapshot.buildings
                    ),
                    "maximum_silos": maximum_silo_count(snapshot),
                    "silo_queued": any(
                        str(item.get("item", "")).lower().split(".", 1)[0] == "silo"
                        for item in snapshot.production
                    ),
                    "policy": "Queue one silo if below the silo limit; otherwise spend reserves on combat production and map control.",
                },
            } if insight.key == "storage_pressure" else {}),
        }

    def ask(self, question: str) -> CompanionResponse:
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        generation = self._begin()
        if not self.enabled:
            return CompanionResponse("", "disabled", utterance_id=generation)
        snapshot = self.latest_snapshot
        if snapshot is None:
            return CompanionResponse("I don't have a live game snapshot yet.", "deterministic-fallback", utterance_id=generation, metadata={"degraded": True})
        started = time.perf_counter()
        try:
            images, views = self._vision_inputs(snapshot)
            if images:
                result = self.router.vision_many(
                    SYSTEM_PROMPT + "\n" + FULL_VISION_PROMPT + "\nCONTEXT:\n" +
                    json.dumps({"player_question": question, "snapshot": snapshot.compact(), "vision_views": views}, separators=(",", ":")),
                    images,
                )
            else:
                result = self.router.chat([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"player_question": question, "snapshot": snapshot.compact()}, separators=(",", ":"))},
                ])
            metadata = {"model": result.model}
            if views:
                metadata["vision"] = {
                    "used": result.vision_used,
                    "views": views,
                    "fallback": None if result.vision_used else "structured-context",
                }
            response = CompanionResponse(humanize_text(result.text), "ai-layer", utterance_id=generation, latency_ms=result.latency_ms, metadata=metadata)
        except RouterError as exc:
            response = CompanionResponse("The AI router is unavailable; I can still watch for critical deterministic alerts.", "deterministic-fallback", utterance_id=generation, latency_ms=round((time.perf_counter() - started) * 1000), metadata={"degraded": True, "reason": str(exc)})
        if self._interrupted(generation):
            response.text = ""
            response.interrupted = True
        return response

    def set_action_executor(
        self,
        executor: Callable[[str, int, tuple[ActionCommand, ...]], ActionReceipt] | None,
    ) -> None:
        with self._action_lock:
            self._action_executor = executor

    def set_action_planner(self, planner: Callable[[str], dict] | None) -> None:
        """Attach the interactive MCP planner; its action tools are proposal-only."""
        with self._action_lock:
            self._action_planner = planner

    def set_strategy_controller(self, controller: Callable[[str], bool] | None) -> None:
        """Attach the native OpenRA strategy switch owned by the live watcher."""
        with self._action_lock:
            self._strategy_controller = controller
            self.native_brain_available = controller is not None

    def select_strategy(self, profile: str, *, persist: bool = True) -> bool:
        profile = profile.strip().lower()
        if profile not in STRATEGY_CONTRACTS:
            raise ValueError("unknown OpenRA strategy")
        previous = self.native_strategy
        previous_profile = self.native_profile
        self.native_strategy = profile
        self.native_profile = strategy_contract(profile)["native_profile"]
        with self._action_lock:
            controller = self._strategy_controller
        accepted = controller(self.native_profile) if controller is not None else True
        if not accepted:
            self.native_strategy = previous
            self.native_profile = previous_profile
            return False
        if persist:
            self.router.configure({"native_strategy": profile})
        return True

    def apply_adaptive_profile(self, profile: str) -> bool:
        """Let the slow strategy director switch native doctrine without leaving Adaptive mode."""
        profile = profile.strip().lower()
        if self.native_strategy != "adaptive" or profile not in {"normal", "rush", "turtle", "naval", "medium"}:
            return False
        previous = self.native_profile
        self.native_profile = profile
        with self._action_lock:
            controller = self._strategy_controller
        accepted = controller(profile) if controller is not None else True
        if not accepted:
            self.native_profile = previous
            return False
        return True

    def set_snapshot_provider(self, provider: Callable[[], GameSnapshot] | None) -> None:
        """Attach a live refresh used immediately before confirmed dispatch."""
        with self._action_lock:
            self._snapshot_provider = provider

    @staticmethod
    def _json_object(text: str) -> dict | None:
        value = text.strip()
        if value.startswith("```"):
            value = value.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            decoded = json.loads(value[start : end + 1])
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None

    @staticmethod
    def _validate_action_commands(snapshot: GameSnapshot, values: object) -> tuple[ActionCommand, ...]:
        if not isinstance(values, list) or not 1 <= len(values) <= 12:
            raise ValueError("an action proposal must contain 1 to 12 commands")

        owned_units = {unit.actor_id: unit for unit in snapshot.units}
        owned_buildings = {building.actor_id: building for building in snapshot.buildings}
        owned_actors = owned_units | owned_buildings
        visible_enemies = {unit.actor_id for unit in snapshot.visible_enemies}
        visible_enemies.update(building.actor_id for building in snapshot.visible_enemy_buildings)
        available = {item.lower() for item in snapshot.available_production}
        in_production = {str(item.get("item", "")).lower() for item in snapshot.production}
        support_powers = {
            str(power.get("key", "")).lower(): power
            for power in snapshot.support_powers
            if str(power.get("key", "")).strip()
        }
        queued_harvesters = sum(
            str(item.get("item", "")).lower().split(".", 1)[0] == "harv"
            for item in snapshot.production
        )
        planned_harvesters = 0
        planned_units: dict[str, int] = {}
        commands: list[ActionCommand] = []

        for raw in values:
            if not isinstance(raw, dict):
                raise ValueError("every command must be an object")
            command = ActionCommand.from_dict(raw)
            if command.action in ACTOR_ACTIONS and command.actor_id not in owned_actors:
                raise ValueError(f"actor {command.actor_id} is not owned by the player")
            if command.action in {
                "move",
                "attack_move",
                "attack",
                "stop",
                "harvest",
                "deploy",
                "guard",
                "set_stance",
                "enter_transport",
                "disguise",
                "infiltrate",
                "demolish",
                "capture",
                "unload",
            } and command.actor_id not in owned_units:
                raise ValueError(f"actor {command.actor_id} is not a controllable unit")
            if command.action in {"attack", "attack_move", "guard", "set_stance"} and not owned_units[command.actor_id].can_attack:
                raise ValueError(f"actor {command.actor_id} cannot attack")
            if command.action in {"repair", "sell", "power_down", "set_primary", "set_rally_point"} and command.actor_id not in owned_buildings:
                raise ValueError(f"actor {command.actor_id} is not an owned building")
            if command.action == "repair" and owned_buildings[command.actor_id].hp_percent >= 0.999:
                raise ValueError(f"building {command.actor_id} is not damaged")
            if command.action in TARGET_ACTOR_ACTIONS and command.target_actor_id <= 0:
                raise ValueError(f"{command.action} requires a target actor")
            if command.action == "attack" and command.target_actor_id not in visible_enemies:
                raise ValueError(f"target {command.target_actor_id} is not a visible enemy")
            if command.action == "guard" and command.target_actor_id not in owned_actors:
                raise ValueError(f"target {command.target_actor_id} is not an owned actor")
            if command.action == "enter_transport":
                transport = owned_units.get(command.target_actor_id)
                transport_kind = transport.kind.lower().split("@", 1)[0].split(".", 1)[0] if transport else ""
                if transport is None or (
                    transport.passenger_count < 0
                    and transport_kind not in {"tran", "lst", "apc", "hind"}
                ):
                    raise ValueError(f"target {command.target_actor_id} is not an owned transport")
            if command.action == "disguise" and command.target_actor_id not in owned_units[command.actor_id].valid_disguise_targets:
                raise ValueError(f"target {command.target_actor_id} is not a valid visible disguise target")
            if command.action == "infiltrate" and command.target_actor_id not in owned_units[command.actor_id].valid_infiltration_targets:
                raise ValueError(f"target {command.target_actor_id} is not a valid visible infiltration target")
            if command.action == "demolish" and command.target_actor_id not in owned_units[command.actor_id].valid_demolition_targets:
                raise ValueError(f"target {command.target_actor_id} is not a valid visible demolition target")
            if command.action == "capture" and command.target_actor_id not in owned_units[command.actor_id].valid_capture_targets:
                raise ValueError(f"target {command.target_actor_id} is not a valid visible capture target")
            if command.action == "unload" and owned_units[command.actor_id].passenger_count <= 0:
                raise ValueError(f"transport {command.actor_id} has no passengers")
            if command.action == "set_stance" and not 0 <= command.target_x <= 3:
                raise ValueError("stance must be between 0 and 3")
            position_required = command.action in {"move", "attack_move", "set_rally_point", "use_support_power"}
            position_supplied = command.target_x != 0 or command.target_y != 0
            if command.action in POSITION_ACTIONS and (position_required or position_supplied):
                if snapshot.map_width <= 0 or snapshot.map_height <= 0:
                    raise ValueError("the snapshot does not include map bounds")
                if not snapshot.contains_cell(command.target_x, command.target_y):
                    raise ValueError("a target cell is outside the map")
            if command.action in ITEM_ACTIONS and not command.item_type:
                raise ValueError("a production item is missing")
            if command.action in {"build", "train"} and command.item_type not in available:
                raise ValueError(f"'{command.item_type}' is not currently available for production")
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
                queued_count = sum(
                    str(item.get("item", "")).lower() == command.item_type
                    for item in snapshot.production
                )
                planned_count = planned_units.get(command.item_type, 0)
                limit = maximum_queued_unit_count(command.item_type)
                if queued_count + planned_count >= limit:
                    raise ValueError(
                        f"'{command.item_type}' already reaches its rolling queue limit of {limit}; "
                        "choose a complementary unit or wait for production"
                    )
                planned_units[command.item_type] = planned_count + 1
            if command.action == "place_building" and command.item_type not in in_production:
                raise ValueError(f"'{command.item_type}' is not in a production queue")
            if command.action == "cancel_production" and command.item_type not in in_production:
                raise ValueError(f"'{command.item_type}' is not in a production queue")
            if command.action == "use_support_power":
                power = support_powers.get(command.item_type.lower())
                if power is None or not bool(power.get("active", False)) or not bool(power.get("ready", False)):
                    raise ValueError(f"support power '{command.item_type}' is not ready")
                power_text = " ".join((
                    command.item_type,
                    str(power.get("name", "")),
                    str(power.get("description", "")),
                )).lower()
                if any(term in power_text for term in ("nuke", "atomic", "parabomb")):
                    friendlies = (*snapshot.units, *snapshot.buildings)
                    if any(
                        (actor.cell_x - command.target_x) ** 2 + (actor.cell_y - command.target_y) ** 2 <= 15 ** 2
                        for actor in friendlies
                    ):
                        raise ValueError("destructive support power target violates the 15-cell friendly-fire exclusion zone")
                    if not any(
                        (actor.cell_x - command.target_x) ** 2 + (actor.cell_y - command.target_y) ** 2 <= 6 ** 2
                        for actor in (*snapshot.visible_enemies, *snapshot.visible_enemy_buildings)
                    ):
                        raise ValueError("destructive support powers require a currently visible enemy concentration")
            commands.append(command)

        return tuple(commands)

    def pending_action(self) -> dict | None:
        with self._action_lock:
            proposal = self._pending_action
            if proposal is not None and time.monotonic() - proposal.created_at > ACTION_EXPIRY_SECONDS:
                self._pending_action = None
                proposal = None
        if proposal is None:
            return None
        return proposal.as_dict()

    def _contextual_action(
        self,
        snapshot: GameSnapshot,
        insight: Insight,
        threat: ThreatAssessment,
    ) -> tuple[str, str, list[dict]] | None:
        if snapshot.mission_mode:
            plan = mission_plan(snapshot)
            commands = plan.get("recommended_commands") or []
            next_step = str(plan.get("next_step") or "Follow the live mission objective.")
            if commands:
                return next_step, f"Mission suggestion: {next_step}", commands
            return None

        available = [item.lower() for item in snapshot.available_production]
        completed_building = next((
            item for item in snapshot.production
            if str(item.get("queue_type", "")).lower() in {"building", "defense"}
            and (
                float(item.get("progress", 0)) >= 0.999
                or int(item.get("remaining_ticks", 1)) <= 0
            )
        ), None)
        if completed_building is not None:
            item = str(completed_building.get("item", "")).strip().lower()
            if item:
                name = production_name(item)
                return (
                    f"Place the completed {name}",
                    f"The {name} is ready; I can place it near the base. Say confirm.",
                    [{"action": "place_building", "item_type": item}],
                )

        if insight.key == "opening_deploy":
            mcv = next((unit for unit in snapshot.units if unit.kind.split(".", 1)[0] == "mcv"), None)
            if mcv:
                name = unit_name(mcv.kind)
                return (
                    f"Deploy the starting {name}",
                    f"I suggest deploying your {name} now. Say confirm to establish the base.",
                    [{"action": "deploy", "actor_id": mcv.actor_id}],
                )

        if insight.key == "low_power":
            item = next((item for item in available if item == "powr"), None)
            item = item or next((item for item in available if item == "apwr"), None)
            if item:
                return (
                    "Queue a power plant",
                    "Power is low; I can queue a power plant. Say confirm.",
                    [{"action": "build", "item_type": item}],
                )

        if insight.key == "storage_pressure":
            item = next((item for item in available if item.split(".", 1)[0] == "silo"), None)
            if item and _storage_needs_silo(snapshot):
                percent = round(snapshot.ore / snapshot.resource_capacity * 100)
                return (
                    "Queue a silo",
                    f"Ore storage is {percent}% full; I can build a silo so harvesters keep unloading. Say confirm.",
                    [{"action": "build", "item_type": item}],
                )
            if snapshot.resource_capacity > 0 and snapshot.ore * 100 > snapshot.resource_capacity * 80:
                force_plan = hybrid_force_plan(snapshot, batch_size=3)
                assault_commands = force_plan["assault"]["commands"]
                if assault_commands:
                    return (
                        "Commit a mixed squad while retaining the base reserve",
                        "The mixed squad is ready; I can move it together while keeping siege behind the screen. Say confirm.",
                        assault_commands,
                    )
                production_commands = force_plan["next_production"]
                recon_commands = force_plan["recon"]["commands"]
                commands = [*production_commands, *recon_commands]
                if commands:
                    labels = [production_name(command["item_type"]) for command in production_commands]
                    force = ", ".join(labels)
                    if production_commands and recon_commands:
                        title = f"Produce a mixed batch and fan out {len(recon_commands)} scouts"
                        message = f"Storage is saturated; I can build {force} and resume reconnaissance. Say confirm."
                    elif production_commands:
                        title = f"Convert saturated reserves into a mixed batch: {force}"
                        message = f"Storage is saturated; I can spend the overflow on a balanced {force} batch. Say confirm."
                    else:
                        title = f"Fan out {len(recon_commands)} cheap scouts"
                        message = "The force is large but enemy positions are unknown; I can resume reconnaissance. Say confirm."
                    return (
                        title,
                        message,
                        commands,
                    )

        if insight.key == "no_harvester":
            item = next((item for item in available if item.split(".", 1)[0] == "harv"), None)
            if item:
                return (
                    "Queue a harvester",
                    "Your economy has no harvester; I can queue one. Say confirm.",
                    [{"action": "train", "item_type": item}],
                )

        if insight.key == "critical_damage":
            building = next((building for building in snapshot.buildings if building.hp_percent <= 0.22), None)
            if building:
                name = building_name(building.kind)
                return (
                    f"Repair the damaged {name}",
                    f"Your {name} is critically damaged; I can start repairs. Say confirm.",
                    [{"action": "repair", "actor_id": building.actor_id}],
                )

        if insight.key == "production_rally":
            producer = next((
                building for building in snapshot.buildings
                if building.kind.lower().split(".", 1)[0] in {"weap", "barr", "tent"}
                and building.rally_x < 0
                and building.rally_y < 0
            ), None)
            target = rally_target(snapshot, producer) if producer is not None else None
            if producer is not None and target is not None:
                name = building_name(producer.kind)
                return (
                    f"Set a clear outward rally point for the {name}",
                    f"I can route new units from the {name} into open staging space. Say confirm.",
                    [{
                        "action": "set_rally_point",
                        "actor_id": producer.actor_id,
                        "target_x": target[0],
                        "target_y": target[1],
                    }],
                )

        if insight.key == "opening_scout":
            quota = opening_scout_count(snapshot)
            riflemen = [unit for unit in snapshot.units if unit.kind.lower().split(".", 1)[0] == "e1"]
            unassigned = [
                unit for unit in riflemen
                if unit.idle and unit.actor_id not in self._opening_scout_ids
            ]
            targets = [
                target for target in scout_targets(snapshot, base_center(snapshot), quota)
                if target not in self._opening_scout_targets
            ]
            assignments = list(zip(unassigned, targets))
            if assignments:
                count = len(assignments)
                return (
                    f"Send {count} Rifle Infantry scout{'s' if count != 1 else ''} in different directions",
                    f"I can fan {count} Rifle Infantry scout{'s' if count != 1 else ''} across unexplored approaches. Say confirm.",
                    [
                        {
                            "action": "attack_move",
                            "actor_id": scout.actor_id,
                            "target_x": target[0],
                            "target_y": target[1],
                        }
                        for scout, target in assignments
                    ],
                )

            queued_riflemen = sum(
                str(item.get("item", "")).lower().split(".", 1)[0] == "e1"
                for item in snapshot.production
            )
            accounted = max(self._opening_scouts_committed, len(riflemen) + queued_riflemen)
            rifle_item = next((item for item in available if item.split(".", 1)[0] == "e1"), None)
            if rifle_item and accounted < quota and queued_riflemen == 0:
                count = quota - accounted
                return (
                    f"Train {count} Rifle Infantry scout{'s' if count != 1 else ''}",
                    f"This {snapshot.map_width}×{snapshot.map_height} map calls for {quota} opening scouts. Say confirm to train them.",
                    [{"action": "train", "item_type": rifle_item} for _ in range(count)],
                )

        if insight.key == "situation_update":
            building_kinds = {building.kind.split(".", 1)[0] for building in snapshot.buildings}
            queued_items = {str(item.get("item", "")).lower().split(".", 1)[0] for item in snapshot.production}
            building_queue_busy = any(
                str(item.get("queue_type", "")).lower() == "building"
                for item in snapshot.production
            )
            silo_item = next((item for item in available if item.split(".", 1)[0] == "silo"), None)
            if silo_item and _storage_needs_silo(snapshot):
                return (
                    "Queue a silo",
                    "Storage is above OpenRA's warning threshold; I can add a silo before harvesters stall. Say confirm.",
                    [{"action": "build", "item_type": silo_item}],
                )
            opening_builds = (
                (("powr", "apwr"), "power plant"),
                (("tent", "barr"), "barracks"),
                (("proc",), "refinery"),
                (("weap",), "war factory"),
            )
            if not building_queue_busy:
                for kinds, label in opening_builds:
                    if any(kind in building_kinds or kind in queued_items for kind in kinds):
                        continue
                    item = next((candidate for candidate in available if candidate.split(".", 1)[0] in kinds), None)
                    if item:
                        return (
                            f"Queue a {label}",
                            f"I suggest building a {label} next. Say confirm to queue it.",
                            [{"action": "build", "item_type": item}],
                        )

            harvester_target = desired_harvester_count(snapshot)
            if snapshot.harvester_count < harvester_target:
                harvester_queued = any(
                    str(queued.get("item", "")).lower().split(".", 1)[0] == "harv"
                    for queued in snapshot.production
                )
                item = next((item for item in available if item.split(".", 1)[0] == "harv"), None)
                if item and not harvester_queued:
                    return (
                        f"Train harvester {snapshot.harvester_count + 1} of {harvester_target}",
                        f"This map calls for {harvester_target} harvesters; I can train the next one. Say confirm.",
                        [{"action": "train", "item_type": item}],
                    )

                # Bank cash for the economy target instead of consuming it with a stream of
                # cheap combat units while the harvester is temporarily unaffordable or busy.
                return None

            combat_cap = {"small": 6, "medium": 10, "large": 14, "huge": 18}[
                map_scale(snapshot.map_width, snapshot.map_height)
            ]
            combat_count = sum(unit.can_attack for unit in snapshot.units)
            force_plan = hybrid_force_plan(snapshot, batch_size=1)
            next_production = force_plan["next_production"]
            if next_production and combat_count < combat_cap:
                item = next_production[0]["item_type"]
                label = production_name(item)
                return (
                    f"Train one {label} for the mixed force",
                    f"OpenRA's weighted mix currently needs one {label}. Say confirm to train it.",
                    next_production,
                )

            assault_commands = force_plan["assault"]["commands"]
            if assault_commands:
                return (
                    "Commit the ready mixed squad",
                    "The mixed squad is above its attack threshold; I can advance it together and retain a base reserve. Say confirm.",
                    assault_commands,
                )

            recon_commands = force_plan["recon"]["commands"]
            if recon_commands:
                count = len(recon_commands)
                return (
                    f"Resume reconnaissance with {count} cheap scouts",
                    f"Enemy positions are still unknown; I can fan {count} cheap scouts toward separate hidden regions. Say confirm.",
                    recon_commands,
                )

        force_plan = hybrid_force_plan(snapshot, batch_size=1)
        assault_commands = force_plan["assault"]["commands"]
        if assault_commands:
            return (
                "Respond with a concentrated mixed squad",
                "A valid target is known and the mixed squad is ready; I can move it together while retaining defenders. Say confirm.",
                assault_commands,
            )

        if threat.heated and snapshot.visible_enemies:
            assets = (*snapshot.buildings, *snapshot.units)
            contact = min(
                snapshot.visible_enemies,
                key=lambda enemy: min(
                    (
                        (enemy.cell_x - asset.cell_x) ** 2 + (enemy.cell_y - asset.cell_y) ** 2
                        for asset in assets
                    ),
                    default=0,
                ),
            )
            defenders = sorted(
                (unit for unit in snapshot.units if unit.idle and unit.can_attack),
                key=lambda unit: (unit.cell_x - contact.cell_x) ** 2 + (unit.cell_y - contact.cell_y) ** 2,
            )[:4]
            if defenders:
                count = len(defenders)
                plural = "s" if count != 1 else ""
                return (
                    f"Move {count} idle defender{plural} toward the visible threat",
                    f"Threat is {threat.level}; I can move {count} idle defender{plural} toward it. Say confirm.",
                    [
                        {
                            "action": "attack_move",
                            "actor_id": unit.actor_id,
                            "target_x": contact.cell_x,
                            "target_y": contact.cell_y,
                        }
                        for unit in defenders
                    ],
                )

        return None

    def propose_routine_action(self) -> CompanionResponse | None:
        """Create one free deterministic proposal for routine economy and base upkeep."""
        if not self.enabled or self.latest_snapshot is None or self.latest_snapshot.done:
            return None
        if self.pending_action() is not None:
            return None
        with self._action_lock:
            snapshot_provider = self._snapshot_provider
        if snapshot_provider is not None:
            try:
                self.update_snapshot(snapshot_provider())
            except RuntimeError:
                pass
        snapshot = self.latest_snapshot
        available_types = {
            item.lower().split(".", 1)[0] for item in snapshot.available_production
        }
        if any(unit.kind.split(".", 1)[0] == "mcv" for unit in snapshot.units) and not snapshot.buildings:
            key = "opening_deploy"
        elif snapshot.power_drained > snapshot.power_provided and {"powr", "apwr"} & available_types:
            key = "low_power"
        elif (
            snapshot.resource_capacity > 0
            and snapshot.ore * 100 > snapshot.resource_capacity * 80
        ):
            key = "storage_pressure"
        elif snapshot.harvester_count == 0 and snapshot.tick > 400 and "harv" in available_types:
            key = "no_harvester"
        elif any(building.hp_percent <= 0.22 for building in snapshot.buildings):
            key = "critical_damage"
        elif any(
            building.kind.lower().split(".", 1)[0] in {"weap", "barr", "tent"}
            and building.rally_x < 0
            and building.rally_y < 0
            and rally_target(snapshot, building) is not None
            for building in snapshot.buildings
        ):
            key = "production_rally"
        elif (
            snapshot.tick <= 5_000
            and snapshot.explored_percent < 55
            and self._opening_scout_action_needed(snapshot)
        ):
            key = "opening_scout"
        else:
            key = "situation_update"
        insight = Insight(key, 80, "Autonomous routine review", "Autonomous routine review.", snapshot.tick)
        response = CompanionResponse(
            insight.fallback_text,
            "auto-routine",
            insight=insight,
            metadata={"auto_act": True, "local": True},
        )
        self._attach_contextual_suggestion(response, snapshot, insight, self.current_threat)
        return response if response.metadata.get("action", {}).get("state") == "pending" else None

    def _opening_scout_action_needed(self, snapshot: GameSnapshot) -> bool:
        quota = opening_scout_count(snapshot)
        riflemen = [unit for unit in snapshot.units if unit.kind.lower().split(".", 1)[0] == "e1"]
        if any(unit.idle and unit.actor_id not in self._opening_scout_ids for unit in riflemen):
            return True
        queued = sum(
            str(item.get("item", "")).lower().split(".", 1)[0] == "e1"
            for item in snapshot.production
        )
        available = {item.lower().split(".", 1)[0] for item in snapshot.available_production}
        return "e1" in available and queued == 0 and max(self._opening_scouts_committed, len(riflemen)) < quota

    def auto_act_once(self, event_context: dict | None = None) -> CompanionResponse | None:
        """Plan through the MCP toolset and execute after explicit AUTO authority."""
        if not self.enabled or not self.auto_act_enabled:
            return None
        if self.latest_snapshot is None or self.latest_snapshot.done:
            return None
        if self.pending_action() is None:
            retry = self.goal_blackboard.next_retry()
            if retry is not None:
                try:
                    commands = self._validate_action_commands(
                        self.latest_snapshot,
                        [command.as_dict() for command in retry.commands],
                    )
                except ValueError as exc:
                    self.goal_blackboard.fail(retry.proposal_id, self.latest_snapshot.tick, str(exc))
                    return None
                proposal = ActionProposal(
                    proposal_id=str(uuid.uuid4()),
                    instruction=retry.instruction,
                    summary=retry.summary,
                    expected_tick=self.latest_snapshot.tick,
                    commands=commands,
                    created_at=time.monotonic(),
                )
                if self.goal_blackboard.bind_retry(retry.goal_id, proposal, self.latest_snapshot) is not None:
                    with self._action_lock:
                        self._pending_action = proposal
                    retried = self.confirm_action()
                    retried.metadata["auto_act"] = True
                    if retried.metadata.get("action", {}).get("state") == "executed":
                        retried.text = f"Auto commander: {retried.text}"
                    return retried
            fast_decision = self.tactical_controller.decide(self.latest_snapshot, self.native_profile)
            if fast_decision is not None and (
                fast_decision.owner == "safety"
                or self.latest_snapshot.mission_mode
                or not self.native_brain_available
            ):
                values = [command.as_dict() for command in fast_decision.commands]
                try:
                    commands = self._validate_action_commands(self.latest_snapshot, values)
                except ValueError:
                    commands = ()
                if commands and not self.goal_blackboard.has_active_commands(commands):
                    proposal = ActionProposal(
                        proposal_id=str(uuid.uuid4()),
                        instruction=f"{fast_decision.owner}:{fast_decision.key}",
                        summary=fast_decision.summary,
                        expected_tick=self.latest_snapshot.tick,
                        commands=commands,
                        created_at=time.monotonic(),
                    )
                    with self._action_lock:
                        if self._pending_action is None:
                            self._pending_action = proposal
            if self.pending_action() is None and self.latest_snapshot.mission_mode:
                # Scripted mission micro is a deterministic, event-driven control
                # loop. Do not wait for (or charge for) a general LLM/MCP planning
                # round between short stealth moves.
                plan = mission_plan(self.latest_snapshot)
                values = plan.get("recommended_commands") or []
                if not values:
                    return None
                try:
                    commands = self._validate_action_commands(self.latest_snapshot, values)
                except ValueError:
                    return None
                if self.goal_blackboard.has_active_commands(commands):
                    return None
                proposal = ActionProposal(
                    proposal_id=str(uuid.uuid4()),
                    instruction="mission:auto-step",
                    summary=str(plan.get("next_step") or "Execute the next scripted mission step"),
                    expected_tick=self.latest_snapshot.tick,
                    commands=commands,
                    created_at=time.monotonic(),
                )
                with self._action_lock:
                    if self._pending_action is None:
                        self._pending_action = proposal
                    else:
                        return None
            elif self.pending_action() is None:
                instruction = AUTO_ACTION_INSTRUCTION
                if event_context:
                    instruction += (
                        "\nA priority game event just interrupted the periodic timer. "
                        "Respond to it now, and re-read the battlefield through MCP before acting.\nEVENT_CONTEXT:\n"
                        + json.dumps(event_context, separators=(",", ":"))
                    )
                planned = self.handle_player_input(instruction)
                if planned.metadata.get("action", {}).get("state") != "pending":
                    # AUTO reevaluates frequently. A stale or temporarily impossible model plan is
                    # not useful player-facing advice and must not pollute the tactical feed.
                    return None
        receipt = self.confirm_action()
        receipt.metadata["auto_act"] = True
        if receipt.metadata.get("action", {}).get("state") == "executed":
            receipt.text = f"Auto commander: {receipt.text}"
        return receipt

    def _attach_contextual_suggestion(
        self,
        response: CompanionResponse,
        snapshot: GameSnapshot,
        insight: Insight,
        threat: ThreatAssessment,
    ) -> None:
        if response.interrupted or not response.text:
            return
        self.pending_action()
        with self._action_lock:
            if self._pending_action is not None:
                return
        suggestion = self._contextual_action(snapshot, insight, threat)
        if suggestion is None:
            return
        summary, message, values = suggestion
        try:
            commands = self._validate_action_commands(snapshot, values)
        except ValueError:
            return
        proposal = ActionProposal(
            proposal_id=str(uuid.uuid4()),
            instruction=f"contextual:{insight.key}",
            summary=summary,
            expected_tick=snapshot.tick,
            commands=commands,
            created_at=time.monotonic(),
        )
        with self._action_lock:
            if self._pending_action is not None:
                return
            self._pending_action = proposal
        response.text = message
        response.source = "contextual-action-suggestion"
        response.metadata["action"] = {"state": "pending", "contextual": True, **proposal.as_dict()}

    @staticmethod
    def _fallback_scout_targets(
        snapshot: GameSnapshot,
        origin: tuple[int, int],
        count: int,
    ) -> list[tuple[int, int]]:
        """Choose bounded cardinal reconnaissance targets when no spatial grid is available."""
        left = snapshot.map_bounds_x
        top = snapshot.map_bounds_y
        width = snapshot.map_bounds_width or snapshot.map_width
        height = snapshot.map_bounds_height or snapshot.map_height
        if width <= 2 or height <= 2:
            return []
        right = left + width - 1
        bottom = top + height - 1
        ox = min(max(origin[0], left + 1), right - 1)
        oy = min(max(origin[1], top + 1), bottom - 1)
        return [
            (left + 1, oy),
            (right - 1, oy),
            (ox, top + 1),
            (ox, bottom - 1),
        ][:max(0, min(4, count))]

    def _scout_request_response(
        self,
        snapshot: GameSnapshot,
        instruction: str,
        generation: int,
    ) -> CompanionResponse:
        """Turn a natural scouting request into the next legal, state-aware step."""
        def base_type(value: object) -> str:
            return str(value).lower().split("@", 1)[0].split(".", 1)[0]

        barracks_types = {"tent", "barr"}
        rifle_types = {"e1", "e2", "cnrifle"}
        excluded_types = {"dog", "spy", "e6", "medi", "mech", "e7"}
        building_types = {base_type(building.kind) for building in snapshot.buildings}
        barracks_ready = bool(building_types & barracks_types)
        queued_barracks = next((
            item for item in snapshot.production
            if base_type(item.get("item", "")) in barracks_types
        ), None)

        candidates = sorted(
            (
                unit for unit in snapshot.units
                if unit.idle
                and unit.can_attack
                and base_type(unit.kind) not in excluded_types
                and (
                    base_type(unit.kind) in rifle_types
                    or (unit.armor_type.lower() in {"", "none"} and 0 < unit.cost <= 400)
                )
            ),
            key=lambda unit: (
                base_type(unit.kind) not in rifle_types,
                unit.cost,
                unit.actor_id,
            ),
        )
        quota = min(4, opening_scout_count(snapshot))
        targets = scout_targets(snapshot, base_center(snapshot), min(quota, len(candidates)))
        if not targets:
            targets = self._fallback_scout_targets(
                snapshot,
                base_center(snapshot),
                min(quota, len(candidates)),
            )
        assignments = list(zip(candidates, targets))
        if assignments:
            commands = self._validate_action_commands(snapshot, [
                {
                    "action": "attack_move",
                    "actor_id": unit.actor_id,
                    "target_x": target[0],
                    "target_y": target[1],
                }
                for unit, target in assignments
            ])
            count = len(commands)
            summary = f"Fan {count} infantry scout{'s' if count != 1 else ''} across unexplored approaches"
            proposal = ActionProposal(
                proposal_id=str(uuid.uuid4()),
                instruction=instruction,
                summary=summary,
                expected_tick=snapshot.tick,
                commands=commands,
                created_at=time.monotonic(),
            )
            with self._action_lock:
                self._pending_action = proposal
            barracks_note = (
                "The Barracks is already ready; " if barracks_ready
                else "You already have scout-capable infantry, so another Barracks is unnecessary; "
            )
            return CompanionResponse(
                f"{barracks_note}I can fan {count} infantry scout{'s' if count != 1 else ''} "
                "toward different unexplored approaches. Say confirm.",
                "action-proposal",
                utterance_id=generation,
                metadata={"deterministic": True, "action": {"state": "pending", **proposal.as_dict()}},
            )

        if queued_barracks is not None:
            progress = max(0, min(100, round(float(queued_barracks.get("progress", 0)) * 100)))
            if progress >= 100:
                commands = self._validate_action_commands(snapshot, [{
                    "action": "place_building",
                    "item_type": str(queued_barracks.get("item", "")),
                }])
                proposal = ActionProposal(
                    proposal_id=str(uuid.uuid4()),
                    instruction=instruction,
                    summary="Place the completed Barracks before training scouts",
                    expected_tick=snapshot.tick,
                    commands=commands,
                    created_at=time.monotonic(),
                )
                with self._action_lock:
                    self._pending_action = proposal
                return CompanionResponse(
                    "The Barracks is complete but not placed; I can place it now, then infantry production can begin. Say confirm.",
                    "action-proposal",
                    utterance_id=generation,
                    metadata={"deterministic": True, "action": {"state": "pending", **proposal.as_dict()}},
                )
            authority = (
                "AUTO is already finishing it and will re-evaluate reconnaissance when infantry deploy."
                if self.auto_act_enabled else
                "Let it finish; then I can train and fan out the scouts."
            )
            return CompanionResponse(
                f"The Barracks is already {progress}% complete, so a duplicate build would be wrong. {authority}",
                "action-progress",
                utterance_id=generation,
                metadata={"deterministic": True, "production": dict(queued_barracks)},
            )

        available = {base_type(item): item for item in snapshot.available_production}
        queued_rifle = next((
            item for item in snapshot.production
            if base_type(item.get("item", "")) in rifle_types
        ), None)
        if barracks_ready and queued_rifle is not None:
            progress = max(0, min(100, round(float(queued_rifle.get("progress", 0)) * 100)))
            return CompanionResponse(
                f"The Barracks is ready and infantry scouts are already {progress}% trained; I can fan them out when they deploy.",
                "action-progress",
                utterance_id=generation,
                metadata={"deterministic": True, "production": dict(queued_rifle)},
            )

        if barracks_ready:
            rifle_item = next((available[kind] for kind in ("e1", "cnrifle", "e2") if kind in available), None)
            if rifle_item:
                commands = self._validate_action_commands(snapshot, [
                    {"action": "train", "item_type": rifle_item}
                    for _ in range(quota)
                ])
                proposal = ActionProposal(
                    proposal_id=str(uuid.uuid4()),
                    instruction=instruction,
                    summary=f"Train {quota} infantry scouts",
                    expected_tick=snapshot.tick,
                    commands=commands,
                    created_at=time.monotonic(),
                )
                with self._action_lock:
                    self._pending_action = proposal
                return CompanionResponse(
                    f"The Barracks is ready; I can train {quota} infantry scouts now, then fan them out as they deploy. Say confirm.",
                    "action-proposal",
                    utterance_id=generation,
                    metadata={"deterministic": True, "action": {"state": "pending", **proposal.as_dict()}},
                )

        barracks_item = next((available[kind] for kind in ("tent", "barr") if kind in available), None)
        if barracks_item:
            commands = self._validate_action_commands(snapshot, [{"action": "build", "item_type": barracks_item}])
            proposal = ActionProposal(
                proposal_id=str(uuid.uuid4()),
                instruction=instruction,
                summary="Build a Barracks as the first step toward infantry scouting",
                expected_tick=snapshot.tick,
                commands=commands,
                created_at=time.monotonic(),
            )
            with self._action_lock:
                self._pending_action = proposal
            return CompanionResponse(
                "I can queue the Barracks now; once it is placed, infantry scouts become the next legal step. Say confirm.",
                "action-proposal",
                utterance_id=generation,
                metadata={"deterministic": True, "action": {"state": "pending", **proposal.as_dict()}},
            )

        return CompanionResponse(
            "Your scouting order is clear, but no scout-capable infantry or Barracks production is currently available.",
            "action-unavailable",
            utterance_id=generation,
            metadata={"deterministic": True, "action": {"state": "unavailable"}},
        )

    def _action_failure_followup_response(
        self,
        snapshot: GameSnapshot,
        generation: int,
    ) -> CompanionResponse:
        """Own a planner failure and explain the live blocker without blaming the player."""
        def base_type(value: object) -> str:
            return str(value).lower().split("@", 1)[0].split(".", 1)[0]

        queued_barracks = next((
            item for item in snapshot.production
            if base_type(item.get("item", "")) in {"tent", "barr"}
        ), None)
        barracks_ready = any(base_type(building.kind) in {"tent", "barr"} for building in snapshot.buildings)
        if queued_barracks is not None:
            progress = max(0, min(100, round(float(queued_barracks.get("progress", 0)) * 100)))
            detail = f"The Barracks was already {progress}% complete; the right response was to say that and continue with scouting afterward."
        elif barracks_ready:
            detail = "The Barracks is ready; I should have proposed available infantry and safe unexplored routes."
        else:
            detail = "I should have named the exact unavailable prerequisite or proposed the first legal step."
        return CompanionResponse(
            f"Your request was clear; that was my planning failure, not missing information. {detail}",
            "planner-correction",
            utterance_id=generation,
            metadata={"deterministic": True, "planner_failure": True},
        )

    def _mission_progress_response(self, snapshot: GameSnapshot, generation: int) -> CompanionResponse:
        plan = mission_plan(snapshot)
        next_step = str(plan.get("next_step") or "Follow the current mission objective.")
        values = plan.get("recommended_commands") or []
        created_proposal: ActionProposal | None = None
        if not self.auto_act_enabled and values and self.pending_action() is None:
            try:
                commands = self._validate_action_commands(snapshot, values)
            except ValueError:
                commands = ()
            if commands:
                created_proposal = ActionProposal(
                    proposal_id=str(uuid.uuid4()),
                    instruction="mission:next-step",
                    summary=next_step,
                    expected_tick=snapshot.tick,
                    commands=commands,
                    created_at=time.monotonic(),
                )
                with self._action_lock:
                    if self._pending_action is None:
                        self._pending_action = created_proposal
                    else:
                        created_proposal = None

        detector_count = len(plan.get("hazards", {}).get("disguise_detectors", []))
        warning = (
            f" {detector_count} visible dog detector{'s' if detector_count != 1 else ''} must be avoided."
            if detector_count else ""
        )
        if self.auto_act_enabled:
            authority = "AUTO is handling this with the mission brain; the skirmish bot is disabled here."
        elif created_proposal is not None:
            authority = "Press ACCEPT to issue this mission step."
        else:
            authority = "I will re-evaluate when the objective or visible patrol state changes."
        metadata = {"mission_plan": plan}
        if created_proposal is not None:
            metadata["action"] = {"state": "pending", "contextual": True, **created_proposal.as_dict()}
        return CompanionResponse(
            f"Mission next: {next_step}{warning} {authority}",
            "mission-next-step",
            utterance_id=generation,
            metadata=metadata,
        )

    def _strategy_progress_response(self, snapshot: GameSnapshot, generation: int) -> CompanionResponse:
        """Explain the live plan and expose one safe confirmation-bound next step."""
        active = strategy_contract(self.native_profile)
        state = strategy_state(snapshot, self.native_strategy, native_active=self.auto_act_enabled)
        threat = self.current_threat
        power_balance = snapshot.power_provided - snapshot.power_drained
        known_structures = len(snapshot.visible_enemy_buildings) + len(snapshot.remembered_enemy_buildings)

        if snapshot.done:
            result = snapshot.result or "complete"
            return CompanionResponse(
                f"The match is {result}; there is no remaining battlefield objective.",
                "strategy-next-step",
                utterance_id=generation,
                metadata={"strategy": {**state, "active_native_profile": self.native_profile}},
            )

        pending = self.pending_action()
        created_proposal: ActionProposal | None = None
        suggestion: tuple[str, str, list[dict]] | None = None
        if not self.auto_act_enabled and pending is None:
            opening_mcv = any(
                unit.kind.split(".", 1)[0] == "mcv" for unit in snapshot.units
            ) and not snapshot.buildings
            briefing_insight = Insight(
                "opening_deploy" if opening_mcv else "situation_update",
                80,
                "Player requested the live strategic plan",
                "Player requested the live strategic plan.",
                snapshot.tick,
            )
            suggestion = self._contextual_action(snapshot, briefing_insight, threat)
            if suggestion is not None:
                summary, _, values = suggestion
                try:
                    commands = self._validate_action_commands(snapshot, values)
                except ValueError:
                    suggestion = None
                else:
                    created_proposal = ActionProposal(
                        proposal_id=str(uuid.uuid4()),
                        instruction="strategy:next-step",
                        summary=summary,
                        expected_tick=snapshot.tick,
                        commands=commands,
                        created_at=time.monotonic(),
                    )
                    with self._action_lock:
                        if self._pending_action is None:
                            self._pending_action = created_proposal
                        else:
                            created_proposal = None
                    pending = created_proposal.as_dict() if created_proposal is not None else self.pending_action()

        if suggestion is not None and created_proposal is not None:
            objective = suggestion[0].rstrip(".")
            if "squad" in objective.lower() and snapshot.visible_enemy_buildings:
                count = len(snapshot.visible_enemy_buildings)
                objective += f" against {count} visible enemy structure{'s' if count != 1 else ''}"
        elif threat.heated and snapshot.visible_enemies:
            objective = f"stabilize the visible attack with our combat force before resuming the wider plan"
        elif snapshot.visible_enemy_buildings:
            count = len(snapshot.visible_enemy_buildings)
            objective = f"regroup and pressure the {count} visible enemy structure{'s' if count != 1 else ''}"
        elif snapshot.remembered_enemy_buildings:
            objective = "reconfirm the last-known enemy base and prepare a concentrated assault"
        elif snapshot.production:
            names = list(dict.fromkeys(
                production_name(str(item.get("item", ""))) for item in snapshot.production[:3]
            ))
            objective = f"finish {', '.join(names)}, then reassess the next attack threshold"
        elif snapshot.explored_percent < 90:
            objective = "scout the remaining fog until enemy production and economy are located"
        else:
            objective = "sweep the remaining map and concentrate on any surviving enemy force"

        if snapshot.visible_enemy_buildings:
            remaining = (
                f"{len(snapshot.visible_enemy_buildings)} enemy structure"
                f"{'s are' if len(snapshot.visible_enemy_buildings) != 1 else ' is'} visible; "
                "destroy them, then locate surviving production and forces"
            )
        elif snapshot.remembered_enemy_buildings:
            remaining = "reveal the last-known structures again, then eliminate surviving production and forces"
        elif known_structures == 0:
            remaining = "locate the enemy base, destroy its production and economy, and eliminate surviving forces"
        else:
            remaining = "eliminate surviving enemy production and forces"

        trade_delta = snapshot.kills_cost - snapshot.deaths_cost
        trade_status = ""
        if snapshot.kills_cost or snapshot.deaths_cost:
            trade_status = f", combat trades {trade_delta:+,}"
        facts = (
            f"{active['name']} is active; threat {threat.level}, power {power_balance:+}, "
            f"{snapshot.harvester_count} harvester{'s' if snapshot.harvester_count != 1 else ''}{trade_status}"
        )

        if self.auto_act_enabled:
            authority = "AUTO is executing this plan now."
        elif created_proposal is not None:
            authority = "AUTO is off; ACCEPT issues this proposed step."
        elif pending is not None:
            authority = "AUTO is off; the existing ACCEPT proposal is still waiting."
        else:
            authority = "AUTO is off; ask me to prepare a specific move when you want one."

        metadata = {
            "strategy": {**state, "active_native_profile": self.native_profile},
            "briefing": {
                "phase": state["phase"],
                "next": objective,
                "remaining": remaining,
                "facts": facts,
                "native_profile": self.native_profile,
                "auto_act": self.auto_act_enabled,
            },
        }
        if pending is not None:
            metadata["action"] = {"state": "pending", "contextual": True, **pending}
        return CompanionResponse(
            f"Next: {objective}. {facts}. Remaining: {remaining}. {authority}",
            "strategy-next-step",
            utterance_id=generation,
            metadata=metadata,
        )

    def handle_player_input(self, text: str) -> CompanionResponse:
        """Answer a question or create a proposal that still requires confirmation."""
        instruction = text.strip()
        if not instruction:
            raise ValueError("question must not be empty")
        if _is_cancel_intent(instruction):
            return self.cancel_action()
        if _is_confirm_intent(instruction):
            return self.confirm_action()

        strategy_intent, requested_strategy = detect_strategy_intent(instruction)
        if strategy_intent == "query":
            generation = self._begin()
            metadata_strategy = strategy_contract(requested_strategy or self.native_strategy)
            if requested_strategy is not None:
                answer = strategy_answer(requested_strategy, include_sequence=True)
            elif any(word in instruction.lower() for word in ("available", "options", "strategies")):
                answer = "Available strategies are Adaptive, Balanced, Rush, Turtle, Naval, and Measured pressure."
            else:
                answer = strategy_answer(self.native_strategy, include_sequence=True)
                answer = f"Current strategy—{answer}"
                if self.native_strategy == "adaptive":
                    active = strategy_contract(self.native_profile)
                    answer += f" Active native profile: {active['name']}."
                    metadata_strategy = {
                        **metadata_strategy,
                        "active_native_profile": self.native_profile,
                        "active_native_strategy": active,
                    }
            return CompanionResponse(
                answer,
                "strategy-assistant",
                utterance_id=generation,
                metadata={"strategy": metadata_strategy},
            )
        if strategy_intent == "set" and requested_strategy is not None:
            generation = self._begin()
            accepted = self.select_strategy(requested_strategy)
            contract = strategy_contract(requested_strategy)
            if not accepted:
                return CompanionResponse(
                    "The native strategy controller is unavailable, so I left the current strategy unchanged.",
                    "strategy-rejected",
                    utterance_id=generation,
                    metadata={"strategy": strategy_contract(self.native_strategy)},
                )
            mission = self.latest_snapshot is not None and self.latest_snapshot.mission_mode
            execution = (
                "The mission brain keeps control; skirmish strategy is suspended"
                if mission else
                "OpenRA's native brain is switching now"
                if self.auto_act_enabled else
                "It will take control when Auto mode is enabled"
            )
            return CompanionResponse(
                f"Strategy set to {contract['name']}. {execution}.",
                "strategy-changed",
                utterance_id=generation,
                metadata={"strategy": contract, "native_active": self.auto_act_enabled},
            )

        # Any new instruction replaces an unconfirmed proposal.
        with self._action_lock:
            self._pending_action = None

        generation = self._begin()
        if not self.enabled:
            return CompanionResponse("", "disabled", utterance_id=generation)
        snapshot = self.latest_snapshot
        if snapshot is None:
            return CompanionResponse(
                "I don't have a live game snapshot yet.",
                "deterministic-fallback",
                utterance_id=generation,
                metadata={"degraded": True},
            )
        progress_request = strategy_intent == "progress"
        failure_followup = _is_action_failure_followup(instruction)
        scout_request = _is_scout_request(instruction)

        started = time.perf_counter()
        with self._action_lock:
            planner = self._action_planner
        planner_metadata: dict = {}
        planner_error = ""
        views: list[dict] = []
        result: RouterResult | None = None
        if planner is not None:
            try:
                planned = planner(instruction)
                values = planned.get("commands", []) if isinstance(planned, dict) else []
                if values:
                    decoded_plan = {
                        "mode": "action",
                        "message": humanize_text(str(planned.get("message") or "")),
                        "summary": humanize_text(str(planned.get("summary") or planned.get("message") or "Proposed action")),
                        "commands": values,
                    }
                else:
                    decoded_plan = {
                        "mode": "answer",
                        "answer": humanize_text(str(planned.get("message") or "I need a more specific objective.")),
                    }
                planner_metadata = dict(planned.get("mcp", {}))
                result = RouterResult(
                    json.dumps(decoded_plan, separators=(",", ":")),
                    int(planned.get("latency_ms", round((time.perf_counter() - started) * 1000))),
                    str(planned.get("model", "mcp-agent")),
                )
            except Exception as exc:  # Fall back to the direct action interpreter.
                planner_error = f"{type(exc).__name__}: {str(exc)[:240]}"

        if result is None:
            if failure_followup:
                return self._action_failure_followup_response(snapshot, generation)
            if scout_request:
                return self._scout_request_response(snapshot, instruction, generation)
            if progress_request:
                if snapshot.mission_mode:
                    return self._mission_progress_response(snapshot, generation)
                return self._strategy_progress_response(snapshot, generation)
            try:
                images, views = self._vision_inputs(snapshot)
                if images:
                    result = self.router.vision_many(
                        ACTION_PROMPT + "\n" + FULL_VISION_PROMPT + "\nCONTEXT:\n" +
                        json.dumps({
                            "player_input": instruction,
                            "snapshot": snapshot.action_context(),
                            "vision_views": views,
                        }, separators=(",", ":")),
                        images,
                    )
                else:
                    result = self.router.chat([
                        {"role": "system", "content": ACTION_PROMPT},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"player_input": instruction, "snapshot": snapshot.action_context()},
                                separators=(",", ":"),
                            ),
                        },
                    ])
            except RouterError as exc:
                reason = planner_error or str(exc)
                return CompanionResponse(
                    "The AI router is unavailable; no action was created.",
                    "deterministic-fallback",
                    utterance_id=generation,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    metadata={"degraded": True, "reason": reason, "action": {"state": "not_created"}},
                )

        decoded = self._json_object(result.text)
        if decoded is None:
            # Preserve compatibility with providers that ignore structured instructions.
            return self.ask(instruction)

        created_proposal: ActionProposal | None = None
        result_metadata = {"model": result.model}
        if planner_metadata:
            result_metadata["mcp"] = planner_metadata
        elif planner_error:
            result_metadata["mcp"] = {"connected": False, "fallback": True, "reason": planner_error}
        if views:
            result_metadata["vision"] = {
                "used": result.vision_used,
                "views": views,
                "fallback": None if result.vision_used else "structured-context",
            }
        if str(decoded.get("mode", "")).lower() != "action":
            answer = humanize_text(str(decoded.get("answer", "")).strip())
            if _is_unhelpful_player_answer(answer) or (progress_request and answer.endswith("?")):
                if failure_followup:
                    return self._action_failure_followup_response(snapshot, generation)
                if scout_request:
                    return self._scout_request_response(snapshot, instruction, generation)
                if progress_request:
                    if snapshot.mission_mode:
                        return self._mission_progress_response(snapshot, generation)
                    return self._strategy_progress_response(snapshot, generation)
            if not answer:
                answer = "Please make the requested units, task, and destination more specific."
            response = CompanionResponse(
                answer,
                "ai-layer",
                utterance_id=generation,
                latency_ms=result.latency_ms,
                metadata=result_metadata,
            )
        else:
            try:
                commands = self._validate_action_commands(snapshot, decoded.get("commands"))
                summary = humanize_text(str(decoded.get("summary", "")).strip().rstrip("."))
                if not summary or len(summary) > 180:
                    raise ValueError("the proposal summary is missing or too long")
                proposal = ActionProposal(
                    proposal_id=str(uuid.uuid4()),
                    instruction=instruction,
                    summary=summary,
                    expected_tick=snapshot.tick,
                    commands=commands,
                    created_at=time.monotonic(),
                )
                with self._action_lock:
                    self._pending_action = proposal
                created_proposal = proposal
                message = humanize_text(str(decoded.get("message", "")).strip().rstrip("."))
                lead = f"{message}. " if message else ""
                order_count = len(commands)
                order_label = "order" if order_count == 1 else "orders"
                response = CompanionResponse(
                    f"{lead}I prepared {order_count} validated {order_label}. Say confirm to execute, or cancel.",
                    "action-proposal",
                    utterance_id=generation,
                    latency_ms=result.latency_ms,
                    metadata={**result_metadata, "action": {"state": "pending", **proposal.as_dict()}},
                )
            except ValueError as exc:
                if scout_request:
                    return self._scout_request_response(snapshot, instruction, generation)
                response = CompanionResponse(
                    "The proposed order failed live safety validation, so nothing was sent. Ask me to retry or choose another move.",
                    "action-rejected",
                    utterance_id=generation,
                    latency_ms=result.latency_ms,
                    metadata={**result_metadata, "action": {"state": "rejected", "reason": str(exc)}},
                )

        if self._interrupted(generation):
            if created_proposal is not None:
                with self._action_lock:
                    if self._pending_action == created_proposal:
                        self._pending_action = None
            response.text = ""
            response.interrupted = True
        return response

    def confirm_action(self, proposal_id: str = "") -> CompanionResponse:
        generation = self._begin()
        if not self.enabled:
            return CompanionResponse(
                "The companion is disabled; no orders were sent.",
                "disabled",
                utterance_id=generation,
                metadata={"action": {"state": "disabled"}},
            )
        with self._action_lock:
            proposal = self._pending_action
            executor = self._action_executor
            if proposal is not None and proposal_id and proposal.proposal_id != proposal_id:
                proposal = None

        if proposal is None:
            return CompanionResponse(
                "There is no matching action waiting for confirmation.",
                "action-confirmation",
                utterance_id=generation,
                metadata={"action": {"state": "missing"}},
            )

        with self._action_lock:
            snapshot_provider = self._snapshot_provider
        if snapshot_provider is not None:
            try:
                self.update_snapshot(snapshot_provider())
            except RuntimeError:
                pass
        snapshot = self.latest_snapshot
        if time.monotonic() - proposal.created_at > ACTION_EXPIRY_SECONDS:
            with self._action_lock:
                if self._pending_action == proposal:
                    self._pending_action = None
            return CompanionResponse(
                "That proposal expired after five minutes. Please ask again.",
                "action-confirmation",
                utterance_id=generation,
                metadata={"action": {"state": "expired", **proposal.as_dict()}},
            )

        if snapshot is None:
            return CompanionResponse(
                "I cannot confirm that order until the live battlefield reconnects. Nothing was sent.",
                "action-confirmation",
                utterance_id=generation,
                metadata={"action": {"state": "unavailable", **proposal.as_dict()}},
            )

        try:
            commands = self._validate_action_commands(snapshot, [command.as_dict() for command in proposal.commands])
        except ValueError as exc:
            with self._action_lock:
                if self._pending_action == proposal:
                    self._pending_action = None
            return CompanionResponse(
                "That order is no longer valid on the current battlefield. Nothing was sent.",
                "action-rejected",
                utterance_id=generation,
                metadata={"action": {"state": "rejected", "reason": str(exc), **proposal.as_dict()}},
            )

        if executor is None:
            return CompanionResponse(
                "The action bridge is unavailable; nothing was sent.",
                "action-rejected",
                utterance_id=generation,
                metadata={"action": {"state": "unavailable", **proposal.as_dict()}},
            )

        owner = self.brain_arbiter.owner_for(
            proposal.instruction,
            snapshot,
            auto_act=self.auto_act_enabled,
            native_brain_available=self.native_brain_available,
            commands=commands,
        )
        automatic = self.auto_act_enabled and owner != BrainOwner.USER
        goal = self.goal_blackboard.register(
            proposal,
            snapshot,
            owner,
            automatic=automatic,
        )
        if not self.brain_arbiter.claim(
            goal.scope,
            owner,
            snapshot.tick,
            ttl_ticks=self.goal_blackboard.verify_timeout_ticks * self.goal_blackboard.max_attempts,
            reason=proposal.summary,
        ):
            self.goal_blackboard.fail(proposal.proposal_id, snapshot.tick, "a higher-priority brain owns this control scope")
            with self._action_lock:
                if self._pending_action == proposal:
                    self._pending_action = None
            return CompanionResponse(
                "A higher-priority command currently owns those units; nothing was sent.",
                "action-rejected",
                utterance_id=generation,
                metadata={"action": {"state": "rejected", "reason": "brain ownership conflict", **proposal.as_dict()}},
            )

        # Clear before the call: the proposal id remains the idempotency key if the response is lost.
        with self._action_lock:
            if self._pending_action == proposal:
                self._pending_action = None
        self.goal_blackboard.mark_dispatched(proposal.proposal_id, snapshot.tick)
        try:
            receipt = executor(proposal.proposal_id, snapshot.tick, commands)
        except RuntimeError as exc:
            self.goal_blackboard.fail(proposal.proposal_id, snapshot.tick, str(exc))
            return CompanionResponse(
                (
                    "The engine action bridge was unavailable; AUTO will retry this verified goal."
                    if automatic else "The engine action bridge was unavailable; nothing was sent."
                ),
                "action-rejected",
                utterance_id=generation,
                metadata={"action": {"state": "failed", "reason": str(exc), **proposal.as_dict()}},
            )

        self.goal_blackboard.apply_receipt(receipt)
        state = "executed" if receipt.accepted else "rejected"
        if receipt.accepted and "Rifle Infantry scout" in proposal.summary:
            trained = [
                command for command in commands
                if command.action == "train" and command.item_type.split(".", 1)[0] == "e1"
            ]
            self._opening_scouts_committed += len(trained)
            for command in commands:
                if command.action == "attack_move":
                    self._opening_scout_ids.add(command.actor_id)
                    self._opening_scout_targets.add((command.target_x, command.target_y))
        text = (
            f"Confirmed: {proposal.summary}. {receipt.detail}"
            if receipt.accepted
            else f"The engine rejected that action. {receipt.detail}"
        )
        return CompanionResponse(
            text,
            "action-receipt",
            utterance_id=generation,
            metadata={"action": {"state": state, **proposal.as_dict(), "receipt": receipt.as_dict()}},
        )

    def cancel_action(self, proposal_id: str = "") -> CompanionResponse:
        generation = self._begin()
        with self._action_lock:
            proposal = self._pending_action
            if proposal is not None and proposal_id and proposal.proposal_id != proposal_id:
                proposal = None
            if proposal is not None:
                self._pending_action = None
        if proposal is not None:
            self.goal_blackboard.cancel(
                proposal.proposal_id,
                self.latest_snapshot.tick if self.latest_snapshot is not None else 0,
            )
        if proposal is None:
            text = "There is no matching action waiting to be cancelled."
            state = "missing"
        else:
            text = "Cancelled. No orders were sent."
            state = "cancelled"
        return CompanionResponse(
            text,
            "action-confirmation",
            utterance_id=generation,
            metadata={"action": {"state": state}},
        )

    def draft_mission(self, context: dict) -> CompanionResponse:
        generation = self._begin()
        started = time.perf_counter()
        try:
            result = self.router.chat([
                {"role": "system", "content": MISSION_DESIGN_PROMPT},
                {"role": "user", "content": json.dumps(context, separators=(",", ":"))},
            ])
            response = CompanionResponse(
                result.text,
                "ai-layer",
                utterance_id=generation,
                latency_ms=result.latency_ms,
                metadata={"model": result.model},
            )
        except RouterError as exc:
            location = str(context.get("location") or "the selected region")
            archetype = str(context.get("archetype") or "balanced skirmish").lower()
            fallback = f"Secure {location} in a {archetype}; capture the center while a disrupted supply route forces both armies onto exposed flanks."
            response = CompanionResponse(
                fallback,
                "deterministic-fallback",
                utterance_id=generation,
                latency_ms=round((time.perf_counter() - started) * 1000),
                metadata={"degraded": True, "reason": str(exc)},
            )
        if self._interrupted(generation):
            response.text = ""
            response.interrupted = True
        return response

    def analyze_terrain(self, context: dict, image: bytes) -> dict:
        prompt = TERRAIN_ANALYSIS_PROMPT + "\n\nCONTEXT:\n" + json.dumps(context, separators=(",", ":"))
        result = self.router.vision(prompt, image)
        text = result.text.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            analysis = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RouterError("AI router returned invalid terrain analysis JSON") from exc
        if not isinstance(analysis, dict):
            raise RouterError("AI router returned a non-object terrain analysis")
        analysis["vision_used"] = True
        analysis["model"] = result.model
        analysis["latency_ms"] = result.latency_ms
        return analysis

    def transcribe(self, audio: bytes, filename: str = "question.wav") -> CompanionResponse:
        if not audio:
            raise ValueError("audio must not be empty")
        generation = self._begin()
        if not self.enabled:
            return CompanionResponse("", "disabled", utterance_id=generation)
        result = self.router.transcribe(audio, filename)
        response = CompanionResponse(
            result.text,
            "ai-layer",
            utterance_id=generation,
            latency_ms=result.latency_ms,
            metadata={"model": result.model, "language": self.router.settings.transcribe_language},
        )
        if self._interrupted(generation):
            response.text = ""
            response.interrupted = True
        return response

    def speech(self, text: str) -> tuple[bytes, dict]:
        text = text.strip()
        if not text:
            raise ValueError("text must not be empty")
        generation = self._begin()
        if not self.enabled or self.muted:
            return b"", {"interrupted": False, "disabled": True, "utterance_id": generation}
        audio, latency_ms, content_type = self.router.speech(text)
        interrupted = self._interrupted(generation)
        return (b"" if interrupted else audio), {
            "interrupted": interrupted,
            "utterance_id": generation,
            "latency_ms": latency_ms,
            "content_type": content_type,
        }

    def status(self) -> dict:
        return {
            "service": "companion",
            "version": "0.1.0",
            "enabled": self.enabled,
            "muted": self.muted,
            "auto_act_enabled": self.auto_act_enabled,
            "strategy": (
                {
                    **strategy_state(self.latest_snapshot, self.native_strategy, native_active=self.auto_act_enabled),
                    "active_native_profile": self.native_profile,
                }
                if self.latest_snapshot is not None
                else {**strategy_contract(self.native_strategy), "active_native_profile": self.native_profile}
            ),
            "has_snapshot": self.latest_snapshot is not None,
            "pending_action": self.pending_action(),
            "threat": self.threat_status(),
            "vision": {
                "live_frame_provider": self._frame_provider is not None,
                "tactical_overview": bool(self.latest_snapshot and self.latest_snapshot.spatial_map),
                "last_frame_error": self._last_vision_error,
            },
            "router": self.router.health(),
            "usage": self.router.usage_summary(),
        }
