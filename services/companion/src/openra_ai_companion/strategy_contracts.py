from __future__ import annotations

import re
from typing import Any

from .models import GameSnapshot


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
    return {
        **contract,
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
        r"\bnext (?:move|step|objective|priority)\b",
        r"\bwhat (?:are we|re we) (?:going to|gonna) do\b",
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
