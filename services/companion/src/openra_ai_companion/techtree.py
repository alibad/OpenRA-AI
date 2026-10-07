"""What the player's faction can build, and what each item still needs.

The live observation names only the actors on the field and the items that are
buildable right now, so "Build a Barracks" before the Power Plant is placed
used to be an unknown word.  ``data/tech_tree.json`` (generated from the RTS AI
mod rules by ``scripts/build-companion-tech-tree.py``) lists, per faction,
every unit and building with its display name and the buildings that unlock
it.  This module picks the matching profile and faction for a snapshot and
answers two questions without any model call: *what is this name?* and *what
is missing before it can be built?*
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .models import GameSnapshot

DATA = Path(__file__).with_name("data") / "tech_tree.json"

# Role tokens and producer queues -> spoken names players use for them.
ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "power": ("power plant", "power station", "power"),
    "barracks": ("barracks", "rax", "infantry building"),
    "refinery": ("refinery", "ore refinery", "ref"),
    "radar": ("radar", "radar tower", "radar dome"),
    "repairpad": ("service depot", "repair depot", "repair pad", "depot"),
    "vehicle": ("war factory", "vehicle factory", "factory", "tank factory"),
    "ship": ("naval yard", "shipyard", "navy yard", "dock"),
    "aircraft": ("airfield", "air field", "airport", "helipad"),
}
TECH_WORDS = ("tech center", "battle lab", "tech centre", "laboratory")


def base_type(value: str) -> str:
    return str(value).lower().split("@", 1)[0].split(".", 1)[0]


@functools.lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"profiles": {}, "catalog": {}}


@dataclass(frozen=True)
class Requirement:
    """The first thing to do for an item that is not buildable yet."""

    item: str               # what the player asked for
    blocker: str            # the building that is missing (deepest buildable step)
    chain: tuple[str, ...]  # item -> ... -> blocker, for the explanation
    state: str              # build | place | wait | unavailable | met
    progress: int = 0       # percent, for "wait"


class TechTree:
    """The faction roster that best matches one snapshot."""

    def __init__(self, snapshot: GameSnapshot) -> None:
        self.snapshot = snapshot
        data = load()
        self.catalog: dict[str, dict] = data.get("catalog", {})
        self.profile = ""
        self.faction = ""
        self.confident = False
        self.items: dict[str, dict] = {}
        self.factions: dict[str, dict] = {}
        if snapshot.mod_id == "ra":
            return  # The Classic game keeps its own catalogue (labels.py).
        profiles: dict[str, dict] = data.get("profiles", {})
        if not profiles:
            return
        self.profile = self._pick_profile(profiles)
        self.factions = profiles[self.profile]["factions"]
        self.faction, self.confident = self._pick_faction(self.factions)
        if self.faction:
            self.items = self.factions[self.faction]["items"]

    # -- profile and faction ----------------------------------------------------
    def _own_kinds(self) -> list[str]:
        snapshot = self.snapshot
        kinds = [base_type(actor.kind) for actor in (*snapshot.units, *snapshot.buildings) if "husk" not in actor.kind.lower()]
        kinds += [base_type(item) for item in snapshot.available_production]
        kinds += [base_type(str(entry.get("item", ""))) for entry in snapshot.production]
        return [kind for kind in kinds if kind]

    def _pick_profile(self, profiles: dict[str, dict]) -> str:
        names = {base_type(key): value for key, value in self.snapshot.actor_names.items()}
        best, best_score = next(iter(profiles)), None
        # On a tie (only shared names seen so far) the standalone names win: the public game
        # must not show the original game's coined names.
        for name, profile in sorted(profiles.items(), key=lambda pair: pair[0] != "standalone"):
            score = 0
            for kind, display in names.items():
                known = {faction["items"][kind]["name"] for faction in profile["factions"].values() if kind in faction["items"]}
                if known:
                    # One vote per actor type: a name this profile uses, or one it does not.
                    score += 1 if display in known else -1
            if best_score is None or score > best_score:
                best, best_score = name, score
        return best

    def _pick_faction(self, factions: dict[str, dict]) -> tuple[str, bool]:
        kinds = self._own_kinds()
        if not kinds:
            return "", False
        holders: dict[str, int] = {}
        for faction in factions.values():
            for kind in {*faction["items"], *faction["start"]}:
                holders[kind] = holders.get(kind, 0) + 1
        scores: dict[str, float] = {}
        unique: dict[str, int] = {}
        for name, faction in factions.items():
            known = {*faction["items"], *faction["start"]}
            scores[name] = sum(1.0 / holders[kind] for kind in kinds if kind in known)
            unique[name] = sum(1 for kind in set(kinds) if kind in known and holders.get(kind) == 1)
        ranked = sorted(scores, key=lambda name: (-scores[name], -unique[name], name))
        best = ranked[0]
        if scores[best] <= 0:
            return "", False
        confident = unique[best] > 0 and (len(ranked) == 1 or scores[best] > scores[ranked[1]])
        return best, confident

    @property
    def known(self) -> bool:
        return bool(self.items)

    @property
    def faction_name(self) -> str:
        return str(self.factions.get(self.faction, {}).get("name") or self.faction.title())

    # -- names ------------------------------------------------------------------
    def name(self, item: str) -> str:
        item = item.lower()
        shown = self.snapshot.actor_names.get(item)
        if shown:
            return shown
        entry = self.items.get(base_type(item))
        if entry:
            return entry["name"]
        for faction in self.factions.values():
            if base_type(item) in faction["items"]:
                return faction["items"][base_type(item)]["name"]
        return self.snapshot.actor_name(item)

    def aliases(self, item: str, faction: str | None = None) -> set[str]:
        """Every name this item answers to: profile names, catalog names and role words."""
        item = base_type(item)
        names: set[str] = set()
        roster = self.factions.get(faction or self.faction, {}).get("items", {})
        entry = roster.get(item) or self.items.get(item)
        if entry:
            names.add(entry["name"])
        for profile in load().get("profiles", {}).values():
            for tree in profile["factions"].values():
                if item in tree["items"]:
                    names.add(tree["items"][item]["name"])
        catalog = self.catalog.get(item)
        if catalog:
            names.update(catalog.get("names", []))
        if entry:
            for token in (*entry.get("provides", ()), *entry.get("produces", ())):
                if token in ROLE_ALIASES and entry.get("kind") == "building":
                    names.update(ROLE_ALIASES[token])
            lowered = entry["name"].lower()
            if any(word in lowered for word in TECH_WORDS):
                names.update(TECH_WORDS)
        return {name for name in names if name}

    def roster(self) -> dict[str, dict]:
        return self.items

    def foreign_items(self) -> Iterable[tuple[str, str]]:
        """(item, faction) for items other factions build and this one cannot."""
        for name, faction in self.factions.items():
            if name == self.faction:
                continue
            for item in faction["items"]:
                if item not in self.items:
                    yield item, name

    def owners(self, item: str) -> list[str]:
        """Display names of the factions that can build an item."""
        item = base_type(item)
        return [str(tree.get("name") or name.title()) for name, tree in sorted(self.factions.items()) if item in tree["items"]]

    def foreign_text(self, item: str) -> str:
        owners = self.owners(item)
        name = self.name(item)
        if len(owners) == 1:
            text = f"The {name} belongs to {owners[0]}; {self.faction_name} can't build it."
        else:
            text = f"{self.faction_name} can't build the {name}; other factions field it."
        kind = next((tree["items"][base_type(item)] for tree in self.factions.values() if base_type(item) in tree["items"]), {})
        if kind.get("kind") == "unit" and "tank" in name.lower():
            own = next((self.name(candidate) for candidate, entry in sorted(self.items.items(), key=lambda pair: pair[1].get("order", 0))
                        if entry["kind"] == "unit" and "tank" in entry["name"].lower()), "")
            if own:
                text += f" Your battle tank is the {own}."
        return text

    # -- roles -------------------------------------------------------------------
    def has_role(self, item: str, role: str) -> bool:
        entry = self.items.get(base_type(item))
        if entry is None:
            return False
        return role in entry.get("provides", ()) or role in entry.get("produces", ())

    def role_items(self, role: str) -> list[str]:
        return sorted(
            (item for item, entry in self.items.items() if role in entry.get("provides", ()) or role in entry.get("produces", ())),
            key=lambda item: (self.items[item].get("order", 0), self.items[item].get("cost", 0), item),
        )

    # -- requirements -------------------------------------------------------------
    def _owned(self) -> set[str]:
        return {base_type(building.kind) for building in self.snapshot.buildings}

    def _queued(self, item: str) -> dict | None:
        return next((entry for entry in self.snapshot.production if base_type(str(entry.get("item", ""))) == item), None)

    @staticmethod
    def _finished(entry: dict) -> bool:
        return float(entry.get("progress", 0)) >= 0.999 or int(entry.get("remaining_ticks", 1)) <= 0

    def missing(self, item: str) -> list[list[str]]:
        entry = self.items.get(base_type(item))
        if entry is None:
            return []
        owned = self._owned()
        return [group for group in entry.get("needs", []) if not owned.intersection(group)]

    def requirement(self, item: str, _trail: tuple[str, ...] = ()) -> Requirement:
        """Walk down the missing prerequisites to the first thing the player can do."""
        item = base_type(item)
        trail = (*_trail, item)
        available = {base_type(entry) for entry in self.snapshot.available_production}
        groups = self.missing(item)
        if not groups:
            return Requirement(trail[0], item, trail, "met")
        candidates: list[Requirement] = []
        for group in groups:
            for provider in group:
                queued = self._queued(provider)
                if queued is not None:
                    if self._finished(queued):
                        candidates.append(Requirement(trail[0], provider, (*trail, provider), "place"))
                    else:
                        percent = max(0, min(99, round(float(queued.get("progress", 0)) * 100)))
                        candidates.append(Requirement(trail[0], provider, (*trail, provider), "wait", percent))
                    break
            else:
                buildable = [provider for provider in group if provider in available]
                if buildable:
                    candidates.append(Requirement(trail[0], buildable[0], (*trail, buildable[0]), "build"))
                    continue
                deeper = [provider for provider in group if provider in self.items and provider not in trail]
                if deeper and len(trail) < 6:
                    candidates.append(self.requirement(deeper[0], trail))
                else:
                    candidates.append(Requirement(trail[0], group[0], (*trail, group[0]), "unavailable"))
        # Placing a finished building beats queuing a new one, which beats waiting.
        rank = {"place": 0, "build": 1, "wait": 2, "unavailable": 3, "met": 4}
        return min(candidates, key=lambda requirement: (rank[requirement.state], len(requirement.chain)))

    def missing_names(self, item: str) -> list[str]:
        names = []
        for group in self.missing(item):
            names.append(self.name(group[0]))
        return names

    def explain(self, requirement: Requirement) -> str:
        """'The Barracks needs a Power Plant first.' / '... needs a Radar Tower, which needs an Ore Refinery.'"""
        names = [self.name(item) for item in requirement.chain]
        if len(names) < 2:
            return f"The {names[0]} isn't available yet."
        missing = self.missing_names(requirement.item)
        if len(missing) > 1:
            listed = ", ".join(_article(name) for name in missing[:-1]) + f" and {_article(missing[-1])}"
            text = f"The {names[0]} needs {listed} first."
            if len(names) > 2:
                text += f" The {names[1]} needs " + ", which needs ".join(_article(name) for name in names[2:]) + "."
            return text
        if len(names) > 2:
            return f"The {names[0]} needs {_article(names[1])}, which needs " + ", which needs ".join(
                _article(name) for name in names[2:]
            ) + " first."
        return f"The {names[0]} needs {_article(names[1])} first."


def _article(name: str) -> str:
    return f"{'an' if name[:1].lower() in 'aeiou' else 'a'} {name}"
