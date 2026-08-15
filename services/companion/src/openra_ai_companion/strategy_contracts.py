from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from typing import Any

from .models import GameSnapshot


@dataclass(frozen=True)
class StrategyProgram:
    """Bounded strategic knobs consumed by deterministic planners.

    The LLM may select a doctrine, but never emits free-form real-time policy.
    Every selection is compiled into this stable, inspectable contract.
    """

    profile: str = "normal"
    target_harvesters: int = 3
    attack_squad_size: int = 8
    defense_reserve: int = 3
    retreat_hp: float = 0.35
    siege_standoff_cells: int = 5
    scout_count: int = 3
    aggression: float = 0.55
    expansion_bias: float = 0.5
    defense_bias: float = 0.5
    support_power_risk: float = 0.0
    force_weights: tuple[tuple[str, int], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["force_weights"] = dict(self.force_weights)
        return value


PROFILE_PROGRAMS: dict[str, StrategyProgram] = {
    "normal": StrategyProgram(
        profile="normal", aggression=0.55, expansion_bias=0.6, defense_bias=0.5,
        force_weights=(("infantry", 30), ("armor", 45), ("siege", 15), ("air", 10)),
    ),
    "medium": StrategyProgram(
        profile="medium", attack_squad_size=7, aggression=0.65, expansion_bias=0.5,
        force_weights=(("infantry", 30), ("armor", 50), ("siege", 15), ("air", 5)),
    ),
    "rush": StrategyProgram(
        profile="rush", target_harvesters=2, attack_squad_size=5, defense_reserve=2,
        aggression=0.9, expansion_bias=0.2, defense_bias=0.2,
        force_weights=(("infantry", 35), ("armor", 50), ("siege", 10), ("air", 5)),
    ),
    "turtle": StrategyProgram(
        profile="turtle", target_harvesters=4, attack_squad_size=11, defense_reserve=5,
        retreat_hp=0.45, aggression=0.25, expansion_bias=0.45, defense_bias=0.95,
        force_weights=(("infantry", 30), ("armor", 40), ("siege", 20), ("air", 10)),
    ),
    "naval": StrategyProgram(
        profile="naval", attack_squad_size=8, defense_reserve=3, aggression=0.6,
        expansion_bias=0.55, defense_bias=0.4,
        force_weights=(("infantry", 15), ("armor", 20), ("siege", 5), ("air", 20), ("naval", 40)),
    ),
}


def compile_strategy_program(profile: str, snapshot: GameSnapshot) -> StrategyProgram:
    """Compile a named doctrine into map-scaled, bounded execution parameters."""
    normalized = strategy_contract(profile)["native_profile"]
    base = PROFILE_PROGRAMS.get(normalized, PROFILE_PROGRAMS["normal"])
    area = max(1, snapshot.map_width * snapshot.map_height)
    scale_bonus = 0 if area <= 4_096 else 1 if area <= 9_216 else 2 if area <= 16_384 else 3
    return replace(
        base,
        target_harvesters=max(2, min(6, base.target_harvesters + scale_bonus)),
        attack_squad_size=max(4, min(16, base.attack_squad_size + scale_bonus * 2)),
        defense_reserve=max(2, min(7, base.defense_reserve + scale_bonus)),
        scout_count=max(2, min(4, 2 + scale_bonus)),
        retreat_hp=max(0.2, min(0.6, base.retreat_hp)),
        siege_standoff_cells=max(4, min(8, base.siege_standoff_cells)),
        aggression=max(0.0, min(1.0, base.aggression)),
        expansion_bias=max(0.0, min(1.0, base.expansion_bias)),
        defense_bias=max(0.0, min(1.0, base.defense_bias)),
        support_power_risk=0.0,
    )


STRATEGY_CONTRACTS: dict[str, dict[str, Any]] = {
    "adaptive": {
        "name": "Adaptive command",
        "native_profile": "normal",
        "intent": "Start from OpenRA's complete general-purpose brain and switch doctrine only when battlefield evidence invalidates it.",
        "sequence": [
            "stabilize power and income",
            "scout reachable approaches",
            "build a balanced production base",
            "counter confirmed enemy composition",
            "concentrate a mixed attack group",
            "switch to rush, turtle, or naval doctrine when the map and contact justify it",
        ],
        "switch_triggers": ["major enemy discovery", "sustained base pressure", "water-dominated access", "failed assault", "decisive economic lead"],
    },
    "normal": {
        "name": "Balanced combined arms",
        "native_profile": "normal",
        "intent": "Use OpenRA's richest general-purpose economy, expansion, air, naval, support-power, and combined-arms configuration.",
        "sequence": [
            "establish four-harvester income over time",
            "expand production and technology",
            "maintain a weighted mixed force",
            "protect critical economy and production",
            "assemble large attack squads and pressure enemy production",
        ],
        "switch_triggers": ["urgent early opening", "prolonged defensive emergency", "naval map dominance"],
    },
    "rush": {
        "name": "Aggressive pressure",
        "native_profile": "rush",
        "intent": "Trade slower infrastructure for faster production, frequent attacks, forward expansion, and pressure on enemy economy.",
        "sequence": [
            "secure minimum viable income",
            "accelerate barracks and vehicle production",
            "assemble the first attack threshold quickly",
            "rush enemy production and harvesters",
            "replace losses and keep reinforcement pressure continuous",
        ],
        "switch_triggers": ["rush is repelled with poor trades", "economy collapses", "enemy static defense becomes dominant"],
    },
    "turtle": {
        "name": "Fortified defense",
        "native_profile": "turtle",
        "intent": "Prioritize power headroom, defensive coverage, protected economy, deliberate expansion, and counterattacks from strength.",
        "sequence": [
            "secure the refinery and production core",
            "layer powered defenses across approaches",
            "repair and power-manage critical structures",
            "build a protected mixed reserve",
            "counterattack after the enemy commits into defensive range",
        ],
        "switch_triggers": ["defensive line is secure", "enemy economy is exposed", "map requires naval access"],
    },
    "naval": {
        "name": "Naval control",
        "native_profile": "naval",
        "intent": "Prioritize water production, aircraft support, coastal pressure, and only enough ground infrastructure to preserve the economy.",
        "sequence": [
            "stabilize land income",
            "establish naval production on reachable water",
            "produce a weighted fleet and air support",
            "locate enemy docks and coastal economy",
            "control water lanes and project force onto land targets",
        ],
        "switch_triggers": ["water is inaccessible", "enemy wins the ground base race", "naval targets are exhausted"],
    },
    "medium": {
        "name": "Measured pressure",
        "native_profile": "medium",
        "intent": "Use the complete traditional module stack with moderate squad sizes, expansion, technology, and faster attacks than Normal.",
        "sequence": [
            "reach a three-harvester economy",
            "add core technology and production",
            "produce a weighted mixed force",
            "protect important structures",
            "attack with medium-sized squads and reinforce deliberately",
        ],
        "switch_triggers": ["decisive advantage", "sustained defensive emergency", "water-dominated map"],
    },
}


STRATEGY_ALIASES = {
    "adaptive": "adaptive",
    "adapt": "adaptive",
    "choose": "adaptive",
    "balanced": "normal",
    "normal": "normal",
    "standard": "normal",
    "rush": "rush",
    "aggressive": "rush",
    "offensive": "rush",
    "pressure": "rush",
    "turtle": "turtle",
    "defensive": "turtle",
    "defense": "turtle",
    "fortify": "turtle",
    "fortified": "turtle",
    "naval": "naval",
    "navy": "naval",
    "sea": "naval",
    "medium": "medium",
    "measured": "medium",
}


def strategy_contract(profile: str) -> dict[str, Any]:
    normalized = profile.strip().lower()
    return {"id": normalized, **STRATEGY_CONTRACTS.get(normalized, STRATEGY_CONTRACTS["adaptive"])}


def strategy_phase(snapshot: GameSnapshot) -> str:
    if snapshot.tick < 3_000:
        return "opening"
    if snapshot.visible_enemies:
        return "contact"
    if snapshot.visible_enemy_buildings or snapshot.remembered_enemy_buildings:
        return "assault preparation"
    if snapshot.explored_percent < 70:
        return "reconnaissance and buildup"
    return "map control"


def strategy_state(snapshot: GameSnapshot, profile: str, *, native_active: bool) -> dict[str, Any]:
    contract = strategy_contract(profile)
    program = compile_strategy_program(profile, snapshot)
    return {
        **contract,
        "program": program.as_dict(),
        "phase": strategy_phase(snapshot),
        "native_brain_active": native_active,
        "execution": (
            "OpenRA ModularBot owns real-time economy, construction, production, squads, repairs, power, expansion, and support powers"
            if native_active
            else "advice and confirmed actions only; the native brain is standing by"
        ),
        "llm_role": "choose or revise this persistent strategy at major events; do not micromanage real-time unit behavior",
    }


def detect_strategy_intent(text: str) -> tuple[str, str | None]:
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())
    if not normalized:
        return "", None

    progress_patterns = (
        r"\bwhat(?: is| s)? next\b",
        r"\bwhat(?: is| s)? (?:the )?situation\b",
        r"\bwhat(?: is| s)? happening(?: right now)?\b",
        r"\bwhat(?: the hell )?is going on\b",
        r"\bnext (?:move|step|objective|priority)\b",
        r"\bwhat (?:are we|re we) (?:going to|gonna) do\b",
        r"\bwhat should (?:we|i) do(?: next)?\b",
        r"\bwhat (?:is|s) (?:left|remaining)\b",
        r"\bwhat remains\b",
        r"\bremaining in (?:this|the) (?:game|match)\b",
        r"\bcurrent objective\b",
        r"\bplan from here\b",
        r"\bwhat now\b",
        r"\bhow are we doing\b",
        r"\bare we winning\b",
        r"\bwhere are we at\b",
        r"\bgame status\b",
        r"\bstatus report\b",
        r"\btell me something useful\b",
        r"\bis that all you have\b",
    )
    if any(re.search(pattern, normalized) for pattern in progress_patterns):
        return "progress", None

    strategy_words = {word for word in STRATEGY_ALIASES if re.search(rf"\b{re.escape(word)}\b", normalized)}
    is_question = normalized.startswith(("what", "which", "why", "how", "tell", "explain", "describe")) or "?" in text
    if is_question and any(term in normalized for term in ("strategy", "plan", "doctrine", "playing")):
        profile = STRATEGY_ALIASES[next(iter(sorted(strategy_words)))] if strategy_words else None
        return "query", profile

    imperative = any(re.search(rf"\b{verb}\b", normalized) for verb in (
        "switch", "change", "use", "adopt", "set", "play", "go", "be", "enable",
    ))
    if imperative and strategy_words:
        # Prefer exact doctrine names over descriptive aliases when several occur.
        for word in ("adaptive", "normal", "rush", "turtle", "naval", "medium"):
            if word in strategy_words:
                return "set", STRATEGY_ALIASES[word]
        return "set", STRATEGY_ALIASES[next(iter(sorted(strategy_words)))]

    if any(term in normalized for term in ("current strategy", "our strategy", "current plan", "what are we doing")):
        return "query", None
    return "", None


def strategy_answer(profile: str, *, include_sequence: bool = False) -> str:
    contract = strategy_contract(profile)
    answer = f"{contract['name']}: {contract['intent']}"
    if include_sequence:
        answer += " Sequence: " + "; then ".join(contract["sequence"]) + "."
    return answer
