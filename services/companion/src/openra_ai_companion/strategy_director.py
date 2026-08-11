from __future__ import annotations

import json
from typing import Any

from .models import GameSnapshot, ThreatAssessment
from .router import AIRouter, RouterError
from .strategy_contracts import STRATEGY_CONTRACTS, strategy_phase


DIRECTOR_PROMPT = """You are the slow strategic director above OpenRA's native real-time ModularBot.
Choose exactly one native profile: normal, rush, turtle, naval, or medium.
The native bot handles every tactical order, economy tick, build decision, squad, retreat, repair, and support power.
Change profile only when the supplied fog-respecting evidence creates a meaningful strategic advantage; otherwise keep the current profile.
Never infer hidden enemies. Return only compact JSON: {"profile":"...","reason":"under 18 words"}."""


class StrategyDirector:
    """Low-cadence LLM doctrine selection; never emits unit-level commands."""

    def __init__(self, router: AIRouter):
        self.router = router

    @staticmethod
    def _fallback(snapshot: GameSnapshot, threat: ThreatAssessment, current_profile: str) -> dict[str, str]:
        combat_units = sum(unit.can_attack for unit in snapshot.units)
        visible_force = len(snapshot.visible_enemies)
        if threat.level == "critical" or (visible_force >= max(4, combat_units // 2) and snapshot.buildings):
            return {"profile": "turtle", "reason": "Critical local pressure favors the fortified defense module."}
        if snapshot.visible_enemy_buildings and combat_units >= 12 and snapshot.kills_cost >= snapshot.deaths_cost:
            return {"profile": "rush", "reason": "Known enemy infrastructure and favorable strength support sustained pressure."}
        if snapshot.explored_percent < 55 and current_profile in {"rush", "turtle"}:
            return {"profile": "normal", "reason": "Map knowledge is insufficient for a specialist commitment."}
        return {"profile": current_profile or "normal", "reason": "No major event justifies changing the native doctrine."}

    def choose(
        self,
        snapshot: GameSnapshot,
        threat: ThreatAssessment,
        current_profile: str,
        event_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        profiles = {
            key: {
                "intent": value["intent"],
                "sequence": value["sequence"],
                "switch_triggers": value["switch_triggers"],
            }
            for key, value in STRATEGY_CONTRACTS.items()
            if key != "adaptive"
        }
        context = {
            "current_profile": current_profile,
            "phase": strategy_phase(snapshot),
            "event": {
                "type": str((event_context or {}).get("type", "periodic strategic review")),
                "fact": str((event_context or {}).get("fact", "")),
            },
            "threat": threat.as_dict(),
            "battlefield": snapshot.compact(),
            "profiles": profiles,
        }
        try:
            result = self.router.chat([
                {"role": "system", "content": DIRECTOR_PROMPT},
                {"role": "user", "content": json.dumps(context, separators=(",", ":"))},
            ], temperature=0.1)
            value = result.text.strip()
            if value.startswith("```"):
                value = value.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            decoded = json.loads(value)
            profile = str(decoded.get("profile", "")).strip().lower()
            reason = str(decoded.get("reason", "")).strip()
            if profile not in {"normal", "rush", "turtle", "naval", "medium"} or not reason:
                raise ValueError("invalid strategy response")
            return {
                "profile": profile,
                "reason": reason[:180],
                "model": result.model,
                "latency_ms": result.latency_ms,
                "fallback": False,
            }
        except (RouterError, ValueError, TypeError, json.JSONDecodeError) as exc:
            fallback = self._fallback(snapshot, threat, current_profile)
            return {
                **fallback,
                "model": "deterministic-fallback",
                "latency_ms": 0,
                "fallback": True,
                "error": f"{type(exc).__name__}: {str(exc)[:160]}",
            }
