from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path


_ESSENTIAL_NAMES = {
    "e1": "Rifle Infantry",
    "e2": "Grenadier",
    "e3": "Rocket Soldier",
    "e4": "Flame Infantry",
    "e6": "Engineer",
    "mcv": "Mobile Construction Vehicle",
    "harv": "Ore Truck",
    "fact": "Construction Yard",
    "powr": "Power Plant",
    "apwr": "Advanced Power Plant",
    "proc": "Ore Refinery",
    "tent": "Allied Barracks",
    "barr": "Soviet Barracks",
    "weap": "War Factory",
    "1tnk": "Light Tank",
    "2tnk": "Medium Tank",
    "3tnk": "Heavy Tank",
    "4tnk": "Mammoth Tank",
}


def _engine_roots() -> tuple[Path, ...]:
    configured = os.environ.get("OPENRA_AI_ENGINE_DIR", "").strip()
    roots = []
    if configured:
        roots.append(Path(configured))
    roots.append(Path(__file__).resolve().parents[4] / "engine" / "openra")
    return tuple(dict.fromkeys(root.resolve() for root in roots))


@lru_cache(maxsize=1)
def actor_names() -> dict[str, str]:
    """Load OpenRA's own English actor names, with a portable fallback."""
    names = dict(_ESSENTIAL_NAMES)
    for root in _engine_roots():
        rules = root / "mods" / "ra" / "fluent" / "rules.ftl"
        if not rules.is_file():
            continue
        actor_id = ""
        for raw_line in rules.read_text(encoding="utf-8").splitlines():
            actor_match = re.fullmatch(r"actor-([a-z0-9_.@-]+)\s*=\s*", raw_line.strip())
            if actor_match:
                actor_id = actor_match.group(1).lower()
                continue
            if actor_id:
                name_match = re.fullmatch(r"\.name\s*=\s*(.+)", raw_line.strip())
                if name_match:
                    names[actor_id] = name_match.group(1).strip()
                    actor_id = ""
                    continue
                if raw_line and not raw_line[0].isspace():
                    actor_id = ""
        break
    return names


def _normalized(value: str) -> str:
    return value.strip().lower().split("@", 1)[0].split(".", 1)[0]


def display_name(value: str, fallback: str = "Game object") -> str:
    internal_id = _normalized(value)
    if not internal_id or internal_id == "unknown":
        return fallback
    name = actor_names().get(internal_id)
    if name:
        return name
    words = re.sub(r"[_-]+", " ", internal_id).strip()
    if words != internal_id and any(character.isalpha() for character in words):
        return words.title()
    return fallback


def unit_name(value: str) -> str:
    return display_name(value, "Unit")


def building_name(value: str) -> str:
    return display_name(value, "Building")


def production_name(value: str) -> str:
    return display_name(value, "Production item")


def humanize_text(text: str) -> str:
    """Replace any leaked actor type IDs in player-facing model text."""
    result = text
    for internal_id, name in sorted(actor_names().items(), key=lambda item: len(item[0]), reverse=True):
        result = re.sub(
            rf"(?<![A-Za-z0-9]){re.escape(internal_id)}(?![A-Za-z0-9])",
            name,
            result,
            flags=re.IGNORECASE,
        )
    return result
