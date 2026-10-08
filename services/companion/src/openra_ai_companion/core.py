from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from collections.abc import Callable

from .brain import BrainArbiter, BrainOwner, GoalBlackboard, default_blackboard_path
from .controller import TacticalController, controller_state
from .faction_catalog import FactionKnowledge
from .feedback import FeedbackStore
from .insights import InsightEngine
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
from . import nl_orders
from .advisor import BUILD_FOCUS, Advice, Advisor, is_next_step_question, state_summary
from .contextual_strategy import ContextualStrategy
from .tactical_vision import tactical_overview_png
from .vision_budget import fit_images
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
- {"action":"repair"|"set_primary","actor_id":owned_building_id}
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
- {"action":"use_support_power","item_type":"exact ready support_powers key","target_x":int,"target_y":int}

Use only actor ids and facts supplied in the snapshot. Coordinates must be inside the map. Never target remembered or hidden enemies.
The mod_id identifies the game. Use its supplied actor_names and available_production; never substitute Red Alert 1 rules or country bonuses into Red Alert 2.
Create one command per actor or production item, with at most 12 commands. Never sell, surrender, cancel production, power down,
attack a specific actor, spend resources speculatively, or invent an actor or item id. Use support powers only when explicitly requested by the player.
An action is only a proposal; never say it already happened. Never expose internal type IDs in the answer or summary.
Use player-facing `display_name` values. If the requested target or units are unclear, ask one concise question.
Build and train commands contain only action and item_type; do not add coordinates.
Requests to sell, cancel production, power down, or attack hidden enemies MUST use mode answer, with no commands.
Explain that the requested action cannot be proposed; do not repeat it as advice."""

# Progress questions about the state of play rather than the next step.
STATUS_WORDS = re.compile(
    r"\b(remaining|left|remains|situation|happening|going on|winning|doing|status|report|useful|all you have|where are we)\b"
)

ADVICE_PROMPT = """You are the player's co-commander in a real-time strategy game.
Answer the player's question in one or two short sentences, under 35 words in total, using only the supplied state.
If a suggested next step is supplied and it fits the question, recommend it in your own words.
Never invent units, buildings, places or numbers. No internal ids, markdown, greetings or filler such as "I am assessing"."""

CONFIRM_WORDS = frozenset({"confirm", "confirmed", "yes", "do it", "execute", "go ahead", "proceed"})
CANCEL_WORDS = frozenset({"cancel", "never mind", "nevermind", "stop", "discard"})
ACTION_EXPIRY_SECONDS = 300.0
# Offers the player can have open at once (cards in the panel); the oldest drops out first.
MAX_PENDING_ACTIONS = 3
# After a placement order, how long a structure may still show as "finished" before the
# engine's next observation; within it the structure is not offered for placement again.
PLACEMENT_SETTLE_SECONDS = 8.0


def proposal_subjects(proposal: ActionProposal) -> frozenset[str]:
    """What an offer is about: the production items and the units it would order.

    A newer offer replaces an older one only when they share a subject, so a
    question, or an order for different units, leaves the older offer standing.
    """
    subjects: set[str] = set()
    for command in proposal.commands:
        if command.action in ITEM_ACTIONS and command.item_type:
            subjects.add("item:" + command.item_type.lower().split("@", 1)[0].split(".", 1)[0])
        if command.action in ACTOR_ACTIONS and command.actor_id:
            subjects.add(f"actor:{command.actor_id}")
    return frozenset(subjects)
AUTO_ACTION_INSTRUCTION = """Autonomous commander mode is enabled. Inspect the battlefield with MCP tools and issue one immediately useful batch of legal orders toward winning. In scripted missions, follow mission_plan and the live objectives before skirmish economy logic; preserve required heroes, avoid dog detectors, and restrict disguise, infiltration, capture, and C4 to listed valid targets. Otherwise prioritize completed building placement, economy, production, scouting, defense, then concentrated attacks. Act instead of merely advising; return no commands only when no useful legal order exists."""


def _normalized_action_intent(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


_PROPOSAL_OBJECTS = frozenset({
    "", "that", "it", "this", "order", "orders", "proposal", "proposals", "command", "commands", "everything", "all",
    "please", "now", "thanks", "thank", "plan", "action", "actions", "request", "last", "those", "them", "the",
})


def _is_cancel_intent(text: str) -> bool:
    normalized = _normalized_action_intent(text)
    if normalized in CANCEL_WORDS or normalized in {"no", "nope", "don t", "do not"}:
        return True
    cancelled = re.search(r"\b(?:cancel|abort)\s+(?:the\s+|my\s+|our\s+|that\s+)?(\w*)", normalized)
    if cancelled and cancelled.group(1) not in _PROPOSAL_OBJECTS:
        # "cancel the radar dome" cancels production, not the pending proposal.
        return False
    return any(phrase in f" {normalized} " for phrase in (
        " cancel ",
        " never mind ",
        " do not confirm ",
        " don t confirm ",
        " do not execute ",
        " don t execute ",
    ))


def _cancels_everything(text: str) -> bool:
    words = set(_normalized_action_intent(text).split())
    return bool(words & {"all", "everything", "every", "them", "those", "proposals", "offers", "orders"})


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


# HUD wording for the hosted brain's degraded states (see hosted_gateway.py).
HOSTED_REASONS = {
    "allowance": "DAILY HOSTED ALLOWANCE USED, RESETS 00:00 UTC",
    "offline": "HOSTED AI UNREACHABLE",
    "gateway_unreachable": "AI GATEWAY NOT RUNNING",
    "paused": "HOSTED AI PAUSED",
    "budget": "HOSTED AI AT CAPACITY TODAY",
    "rate_limited": "HOSTED AI BUSY, RETRYING SHORTLY",
    "unauthorized": "RECONNECTING TO RTS AI",
    "unavailable": "HOSTED AI UNAVAILABLE",
    "upstream": "HOSTED AI UNAVAILABLE",
}
HOSTED_SPOKEN = {
    "allowance": "Today's free hosted AI allowance is used up; it resets at midnight UTC. Critical alerts continue.",
    "offline": "I can't reach the RTS AI service right now. Critical alerts continue.",
    "gateway_unreachable": "The local AI gateway isn't running. Critical alerts continue.",
    "paused": "Hosted AI is paused right now. Critical alerts continue.",
    "budget": "Hosted AI is at capacity for today. Critical alerts continue.",
    "rate_limited": "That's a lot of questions in one minute. Give me a moment and ask again.",
    "unauthorized": "I'm reconnecting to RTS AI. Critical alerts continue.",
    "unavailable": "Hosted AI is briefly unavailable. Critical alerts continue.",
    "upstream": "Hosted AI is briefly unavailable. Critical alerts continue.",
}


def _unavailable_text(exc: RouterError, default: str) -> str:
    return HOSTED_SPOKEN.get(getattr(exc, "state", ""), default)


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
        self.faction_knowledge = FactionKnowledge.load()
        self.enabled = self.router.settings.companion_enabled
        self.muted = not self.router.settings.voice_enabled
        self.auto_act_enabled = self.router.settings.auto_act_enabled
        self.native_strategy = self.router.settings.native_strategy
        self.native_profile = strategy_contract(self.native_strategy)["native_profile"]
        self.contextual_strategy = ContextualStrategy()
        self._contextual_strategy_lock = threading.RLock()
        self._strategy_offer_signature = ""
        self._generation = 0
        self._lock = threading.Lock()
        self._action_lock = threading.Lock()
        # Offers waiting for the player, oldest first. An offer survives unrelated questions and
        # orders; only a newer offer for the same thing (item or units) replaces it.
        self._pending_actions: list[ActionProposal] = []
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
        # Structures just ordered placed: the observation can still list them as finished for a
        # moment, so they are not offered again until the engine has had time to place them.
        self._placement_sent: dict[str, float] = {}

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
                    self._pending_actions = []
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
        service = self.ai_service_status()
        if service["degraded"]:
            # The state code stays ready:<profile> so OpenRA keeps AUTO semantics; only the line changes.
            return f"ready:{self.native_profile}", service["hud"]
        return f"ready:{self.native_profile}", "AI READY  •  HOLD ASK KEY TO SPEAK OR SET STRATEGY"

    def ai_service_status(self) -> dict:
        """Where the co-commander's thinking currently runs, for the HUD and /v1/state."""
        reader = getattr(self.router, "service_state", None)
        service = reader() if callable(reader) else {}
        route = str(service.get("route") or "")
        state = str(service.get("state") or "")
        provider = str(getattr(getattr(self.router, "settings", None), "model_provider", ""))
        hosted = provider == "hosted"
        degraded = hosted and (route in {"local-fallback", "none"} or state == "gateway_unreachable")
        reason = HOSTED_REASONS.get(state, "HOSTED AI UNAVAILABLE")
        if not degraded:
            hud = ""
        elif route == "local-fallback":
            hud = f"AI READY  •  LOCAL MODEL STANDING IN: {reason}"
        else:
            hud = f"AI ALERTS ONLY  •  {reason}"
        return {
            "provider": provider,
            "route": route or ("hosted" if hosted else "direct"),
            "state": state or "unknown",
            "degraded": degraded,
            "hud": hud,
            "detail": service.get("detail", ""),
            "remaining_usd": service.get("remaining_usd"),
            "llm_auto_planner": self.llm_auto_planner_allowed,
        }

    @property
    def llm_auto_planner_allowed(self) -> bool:
        """AUTO's periodic MCP planning loop is too costly for the shared hosted allowance."""
        return getattr(getattr(self.router, "settings", None), "model_provider", "") != "hosted"

    def update_snapshot(self, snapshot: GameSnapshot) -> ThreatAssessment:
        previous = self.latest_snapshot
        match_changed = previous is not None and (
            snapshot.tick < previous.tick
            or snapshot.mod_id != previous.mod_id
            or snapshot.map_name != previous.map_name
            or snapshot.map_width != previous.map_width
            or snapshot.map_height != previous.map_height
        )
        if match_changed:
            self._opening_scout_ids.clear()
            with self._contextual_strategy_lock:
                self.contextual_strategy = ContextualStrategy()
                self._strategy_offer_signature = ""
            self._opening_scout_targets.clear()
            self._opening_scouts_committed = 0
            self.brain_arbiter = BrainArbiter()
        self.latest_snapshot = snapshot
        if match_changed:
            with self._action_lock:
                self._pending_actions = []
        else:
            self._prune_pending(snapshot)
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

    def capture_feedback(self) -> dict:
        """Capture a player-controlled local evidence bundle from the live match."""
        snapshot = self.latest_snapshot
        if snapshot is None:
            raise RuntimeError("No live match snapshot is available yet.")

        with self._vision_lock:
            provider = self._frame_provider
            if provider is None:
                raise RuntimeError("The live OpenRA viewport is not available yet.")
            frame = provider()

        record = FeedbackStore().capture(
            frame=frame.metadata(),
            frame_png=frame.png,
            snapshot=snapshot.compact(),
            companion=self.status(),
        )
        record["feedback_url"] = f"/feedback/{record['feedback_id']}"
        record["screenshot_url"] = f"/v1/feedback/{record['feedback_id']}/screenshot"
        return record

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
        # Two images, about 300 KB in total: bounded cost and latency on every route.
        return fit_images(images, views)

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
            response = CompanionResponse(snapshot.humanize_text(result.text), "ai-layer", utterance_id=generation, insight=insight, latency_ms=result.latency_ms, metadata=metadata)
        except RouterError as exc:
            response = CompanionResponse(insight.fallback_text, "deterministic-fallback", utterance_id=generation, insight=insight, latency_ms=round((time.perf_counter() - started) * 1000), metadata={"degraded": True, "reason": str(exc)})
        if self._interrupted(generation):
            response.text = ""
            response.interrupted = True
        return response

    def observe(self, snapshot: GameSnapshot) -> CompanionResponse | None:
        threat = self.update_snapshot(snapshot)
        self._ensure_placement_offers(snapshot)
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

    def catalog_mode(self) -> str:
        """Game mode for catalog answers: the live match, else the mode the game last described."""
        if self.latest_snapshot is not None:
            return self.latest_snapshot.mod_id
        return self.faction_knowledge.last_mode or "ra"

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
        payload: dict = {"player_question": question, "snapshot": snapshot.compact()}
        # Named factions/units get mode-filtered catalog and rules facts so the model cannot borrow another mode's roster.
        catalog = self.faction_knowledge.context(question, snapshot.mod_id)
        if catalog is not None:
            payload["faction_catalog"] = catalog
        try:
            images, views = ([], []) if self.router.settings.vision_model == "local-no-vision" else self._vision_inputs(snapshot)
            context = dict(payload)
            if self.contextual_strategy.active:
                context["player_selected_strategy"] = self.contextual_strategy_state()
            if images:
                result = self.router.vision_many(
                    SYSTEM_PROMPT + "\n" + FULL_VISION_PROMPT + "\nCONTEXT:\n" +
