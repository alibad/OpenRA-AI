"""Fast answers to "what should I build first?" and "what should I do next?".

These questions used to go through the interactive MCP planner, which reads
the battlefield with tools and takes several model calls (9-24 s on the local
2B model).  The next step is almost always decidable from the game state: place
a finished building, fix power, follow the opening build order, add harvesters,
build an army, scout, then attack.  :func:`next_step` decides it without any
model call and returns one short spoken sentence plus the commands for a card.
Open questions that are not a plain "what next?" get a single model call with
the compact state summary from :func:`state_summary` instead (see core.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import GameSnapshot, ThreatAssessment
from .strategy import desired_harvester_count
from .techtree import TechTree, _article, base_type

# "What should I build first?", "what now?", "any advice?" -- a plain request for the next step.
NEXT_STEP_PATTERN = re.compile(
    r"\b(what should (?:i|we) (?:do|build|make|train|get|queue|focus on|work on)"
    r"|what (?:do|can) (?:i|we) (?:do|build)|what(?: is| s)? next|what now|next (?:move|step|priority)"
    r"|(?:any|some|give me) (?:advice|suggestions?|ideas|tips?)|what (?:\w+ )?(?:do|would) you (?:suggest|recommend)"
    r"|(?:what|which) (?:\w+ )?(?:should|shall) (?:i|we) (?:build|train|make|get|do)"
    r"|what would you (?:do|build)|suggest (?:something|a move|what)|recommend (?:something|a move)|help me"
    r"|where (?:do|should) (?:i|we) start|how (?:do|should) (?:i|we) start)\b"
)
BUILD_FOCUS = re.compile(r"\b(build|make|construct|queue|first)\b")

# Opening order by role: power, then the economy, then the two production buildings.
OPENING = ("power", "refinery", "barracks", "factory")
CLASSIC_ROLES = {
    "powr": "power", "apwr": "power", "gapowr": "power", "napowr": "power",
    "proc": "refinery", "garefn": "refinery", "narefn": "refinery",
    "tent": "barracks", "barr": "barracks", "gapile": "barracks", "nahand": "barracks",
    "weap": "factory", "gaweap": "factory", "naweap": "factory",
    "dome": "radar", "naradr": "radar",
}
NAME_ROLES = (
    ("power", ("power plant", "reactor", "power station")),
    ("refinery", ("refinery",)),
    ("barracks", ("barracks",)),
    ("factory", ("war factory", "vehicle factory")),
    ("radar", ("radar",)),
)


@dataclass
class Advice:
    text: str
    summary: str = ""
    commands: list[dict] = field(default_factory=list)
    key: str = ""


def is_next_step_question(text: str) -> bool:
    return bool(NEXT_STEP_PATTERN.search(" ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())))


class Advisor:
    def __init__(self, snapshot: GameSnapshot, threat: ThreatAssessment | None = None) -> None:
        self.snapshot = snapshot
        self.threat = threat or ThreatAssessment()
        self.tree = TechTree(snapshot)
        self.available = [item.lower() for item in snapshot.available_production]

    # -- naming and roles --------------------------------------------------------------
    def name(self, item: str) -> str:
        return self.tree.name(item) if self.tree.factions else self.snapshot.actor_name(item)

    def plural(self, item: str) -> str:
        name = self.name(item)
        if name.lower().endswith(("infantry", "team", "section")) or name.endswith("s"):
            return name
        if name.endswith("man"):
            return name[:-3] + "men"
        return name + "s"

    def roles(self, kind: str) -> set[str]:
        kind = base_type(kind)
        roles: set[str] = set()
        entry = self.tree.items.get(kind)
        if entry is not None:
            provides, produces = set(entry.get("provides", ())), set(entry.get("produces", ()))
            if "power" in provides:
                roles.add("power")
            if "refinery" in provides:
                roles.add("refinery")
            if "infantry" in produces:
                roles.add("barracks")
            if "vehicle" in produces:
                roles.add("factory")
            if "radar" in provides:
                roles.add("radar")
            return roles
        if kind in CLASSIC_ROLES:
            return {CLASSIC_ROLES[kind]}
        name = self.snapshot.actor_name(kind).lower()
        return {role for role, words in NAME_ROLES if any(word in name for word in words)}

    def owned_roles(self) -> set[str]:
        return {role for building in self.snapshot.buildings for role in self.roles(building.kind)}

    def queued(self) -> list[dict]:
        return list(self.snapshot.production)

    @staticmethod
    def finished(entry: dict) -> bool:
        return float(entry.get("progress", 0)) >= 0.999 or int(entry.get("remaining_ticks", 1)) <= 0

    def _is_structure(self, entry: dict) -> bool:
        queue = str(entry.get("queue_type", "")).lower()
        if queue in {"building", "defense", "support"}:
            return True
        item = base_type(str(entry.get("item", "")))
        return not queue and (self.tree.items.get(item, {}).get("kind") == "building" or bool(self.roles(item)))

    def queued_roles(self) -> set[str]:
        return {role for entry in self.queued() for role in self.roles(str(entry.get("item", "")))}

    def available_for(self, role: str) -> str | None:
        candidates = [item for item in self.available if role in self.roles(item) and not item.endswith("f")]
        if not candidates:
            return None
        order = {item: index for index, item in enumerate(self.available)}
        return min(candidates, key=lambda item: (self.tree.items.get(base_type(item), {}).get("order", 0), order[item]))

    def basic_unit(self, queue: str, word: str) -> str | None:
        """The faction's standard rifleman ("Infantry") or battle tank ("Vehicle") when buildable now."""
        for item in self.available:
            entry = self.tree.items.get(base_type(item), {})
            name = self.name(item).lower()
            if self.tree.known and entry.get("queue") != queue:
                continue
            if word == "tank" and "tank" in name:
                return item
            if word == "infantry" and not any(skip in name for skip in ("engineer", "dog", "spy", "medic", "technician")) and (
                entry.get("cost", 0) <= 400 or base_type(item) in {"e1", "e2"}
            ):
                return item
        return None

    # -- the decision -------------------------------------------------------------------
    def next_step(self, *, build_focus: bool = False) -> Advice | None:
        snapshot = self.snapshot
        if snapshot.done:
            return Advice(f"The match is over ({snapshot.result or 'finished'}); there is nothing left to do.", key="done")
        units = [unit for unit in snapshot.units if "husk" not in unit.kind.lower()]
        mcv = next((unit for unit in units if base_type(unit.kind) in {"mcv", "amcv", "smcv"}
                    or "construction vehicle" in snapshot.actor_name(unit.kind).lower()), None)
        if mcv is not None and not snapshot.buildings:
            return Advice(
                f"Deploy your {self.name(mcv.kind)} first; nothing can be built until the Construction Yard is up.",
                f"Deploy the {self.name(mcv.kind)}",
                [{"action": "deploy", "actor_id": mcv.actor_id}],
                "deploy",
            )
        ready = next((entry for entry in self.queued() if self.finished(entry) and self._is_structure(entry)), None)
        if ready is not None:
            item = str(ready.get("item", "")).lower()
            return Advice(
                f"Place the finished {self.name(item)} first; the build queue waits until it's down.",
                f"Place the {self.name(item)}",
                [{"action": "place_building", "item_type": item}],
                "place",
            )
        if not build_focus:
            defend = self._defend()
            if defend is not None:
                return defend
        power = self._power()
        if power is not None:
            return power
        opening = self._opening()
        if opening is not None:
            return opening
        economy = self._harvester()
        if economy is not None:
            return economy
        owned = self.owned_roles()
        if "radar" not in owned and "radar" not in self.queued_roles():
            radar = self.available_for("radar")
            if radar:
                return Advice(
                    f"Build {_article(self.name(radar))} next: it lights up the minimap and unlocks advanced units.",
                    f"Build {_article(self.name(radar))}",
                    [{"action": "build", "item_type": radar}],
                    "build:radar",
                )
        return self._army(build_focus=build_focus)

    def _defend(self) -> Advice | None:
        snapshot = self.snapshot
        if not (self.threat.heated and snapshot.visible_enemies):
            return None
        assets = (*snapshot.buildings, *snapshot.units)
        contact = min(snapshot.visible_enemies, key=lambda enemy: min(
            ((enemy.cell_x - asset.cell_x) ** 2 + (enemy.cell_y - asset.cell_y) ** 2 for asset in assets), default=0))
        defenders = sorted((unit for unit in snapshot.units if unit.idle and unit.can_attack),
                           key=lambda unit: (unit.cell_x - contact.cell_x) ** 2 + (unit.cell_y - contact.cell_y) ** 2)[:6]
        if not defenders:
            return None
        count = len(defenders)
        return Advice(
            f"Enemies are at your base; send your {count} idle fighter{'s' if count != 1 else ''} at them now.",
            f"Attack-move {count} idle unit{'s' if count != 1 else ''} to the attackers",
            [{"action": "attack_move", "actor_id": unit.actor_id, "target_x": contact.cell_x, "target_y": contact.cell_y}
             for unit in defenders],
            "defend",
        )

    def _power(self) -> Advice | None:
        snapshot = self.snapshot
        if not snapshot.buildings or snapshot.power_drained <= snapshot.power_provided:
            return None
        if "power" in self.queued_roles():
            return None
        item = self.available_for("power")
        if item is None:
            return None
        short = snapshot.power_drained - snapshot.power_provided
        return Advice(
            f"Power is short by {short}; build another {self.name(item)} so production runs at full speed.",
            f"Build {_article(self.name(item))}",
            [{"action": "build", "item_type": item}],
            "build:power",
        )

    def _opening(self) -> Advice | None:
        owned, queued = self.owned_roles(), self.queued_roles()
        for role in OPENING:
            if role in owned or role in queued:
                continue
            item = self.available_for(role)
            if item is None:
                continue
            name = self.name(item)
            reason = {
                "power": self._power_reason(),
                "refinery": "it comes with a harvester and pays for everything else",
                "barracks": self._barracks_reason(),
                "factory": self._factory_reason(),
            }[role]
            first = role == "power" and not owned and not self.snapshot.production
            text = f"{'Start with' if first else 'Build'} {_article(name)}{'' if first else ' next'}: {reason}."
            return Advice(text, f"Build {_article(name)}", [{"action": "build", "item_type": item}], f"build:{role}")
        return None

    def _power_reason(self) -> str:
        dependants = [self.name(item) for item in self._role_items("barracks")[:1] + self._role_items("refinery")[:1]]
        if len(dependants) == 2:
            return f"the {dependants[0]} and the {dependants[1]} both need it"
        return "everything else needs power"

    def _barracks_reason(self) -> str:
        infantry = self._roster_basic("Infantry", "infantry")
        return f"you can train {self.plural(infantry)}" if infantry else "it trains your infantry"

    def _factory_reason(self) -> str:
        tank = self._roster_basic("Vehicle", "tank")
        return f"it builds {self.plural(tank)}" if tank else "it builds your vehicles"

    def _role_items(self, role: str) -> list[str]:
        if self.tree.known:
            return [item for item in sorted(self.tree.items, key=lambda item: self.tree.items[item].get("order", 0))
                    if role in self.roles(item)]
        return [item for item in self.available if role in self.roles(item)]

    def _roster_basic(self, queue: str, word: str) -> str | None:
        if not self.tree.known:
            return None
        for item, entry in sorted(self.tree.items.items(), key=lambda pair: pair[1].get("order", 0)):
            name = entry["name"].lower()
            if entry.get("queue") != queue:
                continue
            if word == "tank" and "tank" in name:
                return item
            if word == "infantry" and entry.get("cost", 0) <= 400 and not any(
                    skip in name for skip in ("engineer", "dog", "spy", "medic", "technician")):
                return item
        return None

    def _harvester(self) -> Advice | None:
        snapshot = self.snapshot
        if "refinery" not in self.owned_roles():
            return None
        target = desired_harvester_count(snapshot)
        if snapshot.harvester_count >= target:
            return None
        harvesters = [item for item in self.available if base_type(item) in {"harv", "cmin"}
                      or any(word in self.name(item).lower() for word in ("harvester", "miner", "ore truck"))]
        if not harvesters or any(base_type(str(entry.get("item", ""))) == base_type(harvesters[0]) for entry in self.queued()):
            return None
        item = harvesters[0]
        return Advice(
            f"Train another {self.name(item)}: you have {snapshot.harvester_count} and this map supports {target}.",
            f"Train 1 {self.name(item)}",
            [{"action": "train", "item_type": item}],
            "train:harvester",
        )

    def _army(self, *, build_focus: bool) -> Advice | None:
        snapshot = self.snapshot
        fighters = [unit for unit in snapshot.units if unit.can_attack and "husk" not in unit.kind.lower()
                    and base_type(unit.kind) not in {"harv", "cmin", "mcv", "amcv", "smcv"}]
        busy = {str(entry.get("queue_type", "")).lower() for entry in self.queued()}
        tank = self.basic_unit("Vehicle", "tank")
        infantry = self.basic_unit("Infantry", "infantry")
        if tank and "vehicle" not in busy:
            return Advice(
                f"Build up the army: train {self.plural(tank)}; you have {len(fighters)} combat unit{'s' if len(fighters) != 1 else ''}.",
                f"Train 3 {self.plural(tank)}",
                [{"action": "train", "item_type": tank} for _ in range(3)],
                "train:tank",
            )
        if infantry and "infantry" not in busy and len(fighters) < 8:
            return Advice(
                f"Train more {self.plural(infantry)} to protect the base while it grows.",
                f"Train 3 {self.plural(infantry)}",
                [{"action": "train", "item_type": infantry} for _ in range(3)],
                "train:infantry",
            )
        if build_focus:
            return None
        if fighters and not snapshot.visible_enemy_buildings and not snapshot.remembered_enemy_buildings:
            return Advice(
                f"We haven't found the enemy base yet; send a scout to explore the {100 - round(snapshot.explored_percent)}% of the map still in fog.",
                key="scout",
            )
        if len(fighters) >= 8 and (snapshot.visible_enemy_buildings or snapshot.remembered_enemy_buildings):
            target = (snapshot.visible_enemy_buildings or snapshot.remembered_enemy_buildings)[0]
            attackers = sorted(fighters, key=lambda unit: (not unit.idle, unit.actor_id))[:12]
            return Advice(
                f"Your {len(fighters)} combat units can push now; attack-move them to the enemy base.",
                f"Attack-move {len(attackers)} units to the enemy base",
                [{"action": "attack_move", "actor_id": unit.actor_id, "target_x": target.cell_x, "target_y": target.cell_y}
                 for unit in attackers],
                "attack",
            )
        return None


def state_summary(snapshot: GameSnapshot, threat: ThreatAssessment | None = None) -> str:
    """A compact, fog-respecting summary for one short model call (no ids, no images)."""
    from .nl_orders import vocabulary_context  # local import: nl_orders imports this package's tree

    threat = threat or ThreatAssessment()
    power = snapshot.power_provided - snapshot.power_drained
    lines = [
        vocabulary_context(snapshot),
        f"Cash: ${snapshot.cash:,}; power {power:+}; harvesters {snapshot.harvester_count}; "
        f"threat {threat.level}; explored {round(snapshot.explored_percent)}%",
    ]
    if snapshot.kills_cost or snapshot.deaths_cost:
        lines.append(f"Trades: destroyed ${snapshot.kills_cost:,}, lost ${snapshot.deaths_cost:,}")
    return "\n".join(lines)
