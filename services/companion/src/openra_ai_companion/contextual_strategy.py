"""Player-selected, match-local goals. Reads only the companion's fog-respecting snapshot.

This layer changes confirmed-action advice, never enables AUTO or issues orders itself.
"""
from __future__ import annotations

from .advisor import Advice, Advisor
from .models import GameSnapshot, ThreatAssessment
from .strategy import base_center, desired_harvester_count, scout_targets, rally_target
from .techtree import base_type, load


STRATEGIES = {
    "economy": ("Expand economy", "Build protected income before committing to a larger army.", "Delays offensive production."),
    "scout": ("Scout first", "Reveal reachable approaches with a cheap scout before committing the army.", "Keeps the main force back while gathering information."),
    "pressure": ("Press the attack", "Assemble a force and pressure the enemy positions we have discovered.", "Commits idle fighters and leaves fewer units at home."),
    "defend": ("Protect the economy", "Keep a reserve near income and production; respond to visible attackers.", "Trades attack tempo for a stronger home reserve."),
    "regroup": ("Regroup and rebuild", "Bring idle fighters home and replace losses before another push.", "Gives the enemy time to recover too."),
    "anti_air": ("Add air defense", "Produce faction-appropriate anti-air against observed aircraft.", "Diverts production from ground pressure."),
    "anti_armor": ("Counter enemy armor", "Produce anti-armor against observed armored units.", "Diverts production from other roles."),
    "balanced": ("Build combined arms", "Maintain income and production, then gather a mixed attack force.", "A slower commitment than an all-in attack."),
}


def situation(snapshot: GameSnapshot, threat: ThreatAssessment) -> tuple[str, list[str], str]:
    if snapshot.done:
        return "finished", [], "The match is over."
    if snapshot.mission_mode:
        return "mission", [], "Mission objectives take priority over skirmish strategies."
    if threat.heated and snapshot.visible_enemies:
        return "under_pressure", ["defend", "regroup", "balanced"], "Visible attackers are putting your assets under pressure."
    if any(enemy.can_attack and "air" in " ".join(enemy.target_types).lower() for enemy in snapshot.visible_enemies):
        return "air_contact", ["anti_air", "defend", "pressure"], "Enemy aircraft are visible."
    if any(enemy.armor_type.lower() in {"heavy", "light", "medium"} and "air" not in " ".join(enemy.target_types).lower()
           for enemy in snapshot.visible_enemies):
        return "armor_contact", ["anti_armor", "defend", "pressure"], "Enemy armor is visible."
    if snapshot.deaths_cost > max(1000, snapshot.kills_cost * 1.4):
        return "recovering", ["regroup", "economy", "defend"], "Recorded combat losses exceed the value you destroyed."
    known = bool(snapshot.visible_enemy_buildings or snapshot.remembered_enemy_buildings)
    if known and sum(unit.can_attack for unit in snapshot.units) >= 8:
        return "attack_ready", ["pressure", "economy", "balanced"], "You have a fighting force and a discovered enemy position; their full strength is unknown."
    if not known and snapshot.explored_percent < 70:
        return "opening" if snapshot.tick < 3000 else "searching", ["economy", "scout", "balanced"], "The enemy base has not been located."
    return "buildup", ["balanced", "economy", "defend"], "Build strength while protecting the income you have."


class ContextualStrategy:
    def __init__(self) -> None:
        self.active: str | None = None
        self.selected_tick = 0
        self.reserve = 0
        self.context = ""
        self.choices: list[str] = []
        self.reason = ""
        self.changed_tick = 0

    def select(self, strategy: str | None, reserve: int, snapshot: GameSnapshot) -> None:
        if strategy is not None and strategy not in STRATEGIES:
            raise ValueError("Unknown contextual strategy")
        if isinstance(reserve, bool) or not isinstance(reserve, int) or not 0 <= reserve <= 10000:
            raise ValueError("Credit reserve must be an integer from 0 to 10000")
        if snapshot.done or snapshot.mission_mode:
            raise ValueError("Strategies are available during an active skirmish")
        self.active, self.reserve, self.selected_tick = strategy, reserve, snapshot.tick

    def _train(self, advisor: Advisor, item: str, reason: str) -> Advice:
        entry = advisor.tree.items.get(base_type(item), {})
        if any(base_type(str(row.get("item", ""))) == base_type(item) or
               (entry.get("queue") and row.get("queue_type") == entry["queue"]) for row in advisor.queued()):
            return Advice(f"Wait for the current production queue before adding {advisor.name(item)}.", key="wait")
        action = "build" if entry.get("kind") == "building" else "train"
        return Advice(reason, f"{'Build' if action == 'build' else 'Train'} {advisor.name(item)}",
                      [{"action": action, "item_type": item}], f"{action}:{item}")

    def _counter(self, advisor: Advisor, role: str) -> Advice:
        catalog = load().get("catalog", {})
        roles = {"anti air", "mobile air defense"} if role == "anti air" else {"anti armor"}
        roster = [item for item, entry in advisor.tree.items.items()
                  if (str(catalog.get(base_type(item), {}).get("role", "")).lower() in roles
                      or role.replace(" ", "-") in entry.get("roles", []))
                  and entry.get("queue") in {"Infantry", "Vehicle", "Support", "Defense"}]
        matches = [item for item in advisor.available if base_type(item) in roster]
        owned = sum(base_type(unit.kind) in roster for unit in (*advisor.snapshot.units, *advisor.snapshot.buildings))
        if owned >= 4:
            return Advice("Four counter units are ready. Keep them protected and reassess new enemy contacts.", key="monitor:counter")
        if matches:
            item = min(matches, key=lambda name: advisor.tree.items.get(base_type(name), {}).get("cost", 100000))
            return self._train(advisor, item, f"Add {advisor.name(item)} to support the selected counter strategy.")
        for item in sorted(roster, key=lambda name: advisor.tree.items[name].get("cost", 100000)):
            requirement = advisor.tree.requirement(item)
            if requirement.state in {"build", "place"}:
                blocker = requirement.blocker
                return Advice(advisor.tree.explain(requirement), f"{'Place' if requirement.state == 'place' else 'Build'} {advisor.name(blocker)}",
                              [{"action": "place_building" if requirement.state == "place" else "build", "item_type": blocker}], "unlock:counter")
            if requirement.state == "wait":
                return Advice(advisor.tree.explain(requirement), key="wait:counter")
        # Do not invent capabilities from a display name or queue an unknown actor.
        return Advice("No matching counter is buildable yet. Unlock your faction's counter units before committing.", key="blocked:counter")

    def advice(self, snapshot: GameSnapshot, threat: ThreatAssessment, *, build_focus: bool = False) -> Advice | None:
        advisor = Advisor(snapshot, threat)
        fallback = advisor.next_step(build_focus=build_focus)
        if self.active is None or snapshot.done or snapshot.mission_mode:
            return fallback
        # Survival, building placement and the essential production opening outrank specialist plans.
        needed = {"power", "refinery", "barracks", "factory"}
        if self.active == "scout":
            needed = {"power", "barracks"}
        elif self.active in {"defend", "regroup", "anti_air", "anti_armor"}:
            needed = {"power", "refinery"}
        if fallback and (fallback.key in {"deploy", "place", "defend", "build:power"}
                         or not needed.issubset(advisor.owned_roles())):
            return self._budget(advisor, fallback)
        goal = self.active
        result: Advice | None = None
        fighters = [unit for unit in snapshot.units if unit.can_attack and unit.idle and "husk" not in unit.kind.lower()
                    and base_type(unit.kind) not in {"harv", "cmin", "mcv", "amcv", "smcv"}]
        force_count = sum(unit.can_attack for unit in snapshot.units)
        home = next((building for building in snapshot.buildings if "refinery" in advisor.roles(building.kind)),
                    snapshot.buildings[0] if snapshot.buildings else None)
        if goal == "economy":
            result = advisor._harvester()
            if result is None:
                target = desired_harvester_count(snapshot)
                result = Advice(f"Income goal: {snapshot.harvester_count}/{target} harvesters. Protect them while production completes.", key="monitor:economy")
        elif goal in {"anti_air", "anti_armor"}:
            result = self._counter(advisor, "anti air" if goal == "anti_air" else "anti armor")
        elif goal == "scout":
            cheap = sorted((unit for unit in fighters if 0 < unit.cost <= 400), key=lambda unit: (unit.cost, unit.actor_id))
            targets = scout_targets(snapshot, base_center(snapshot), 1) if snapshot.spatial_map else []
            if cheap and targets:
                x, y = targets[0]
                result = Advice("Send a cheap idle fighter along a reachable scouting route; keep the main army back.",
                                "Scout a reachable approach", [{"action": "attack_move", "actor_id": cheap[0].actor_id,
                                "target_x": x, "target_y": y}], "scout")
            else:
                item = advisor.basic_unit("Infantry", "infantry")
                scout_exists = any(unit.can_attack and 0 < unit.cost <= 400 for unit in snapshot.units)
                result = self._train(advisor, item, "Prepare one cheap scout before committing your main army.") if item and not scout_exists else Advice(
                    "Scouting is in progress, or no reachable scout route is known yet. Keep exploring before committing the army.", key="monitor:scout")
        elif goal in {"defend", "regroup"}:
            if home and fighters and not build_focus:
                moving = fighters[:6]
                action = "guard" if goal == "defend" else "move"
                anchor = rally_target(snapshot, home)
                if action == "move" and anchor is None:
                    return Advice("No explored, clear regrouping site is available near the economy yet.", key="blocked:regroup")
                commands = [{"action": action, "actor_id": unit.actor_id, **(
                    {"target_actor_id": home.actor_id} if action == "guard" else {"target_x": anchor[0], "target_y": anchor[1]})}
                    for unit in moving if (unit.cell_x - home.cell_x) ** 2 + (unit.cell_y - home.cell_y) ** 2 > 36]
                if commands:
                    result = Advice("Keep a home reserve while you command the rest of the army.", "Bring idle fighters back to the economy", commands, "reserve")
            if result is None:
                result = (advisor._army(build_focus=True) if force_count < 6 else None) or Advice("Hold the home reserve near your economy and watch the approaches while current orders finish.", key="monitor:reserve")
        elif goal == "pressure" and not build_focus:
            targets = snapshot.visible_enemy_buildings or snapshot.remembered_enemy_buildings
            if targets and len(fighters) >= 7:
                target = targets[0]
                moving = fighters[:min(8, len(fighters) - 2)]
                result = Advice("Pressure the discovered enemy position with idle fighters; leave other units under your control.",
                                "Attack-move the idle attack group", [{"action": "attack_move", "actor_id": unit.actor_id,
                                "target_x": target.cell_x, "target_y": target.cell_y} for unit in moving], "pressure")
            else:
                result = advisor._army(build_focus=True) or Advice("Gather an attack group plus two reserve fighters and locate an enemy position before attacking.", key="monitor:pressure")
        return self._budget(advisor, result or fallback)

    def cost(self, snapshot: GameSnapshot, commands: list[dict]) -> int | None:
        tree = Advisor(snapshot).tree
        total = 0
        for command in commands:
            if command.get("action") not in {"build", "train"}:
                continue
            entry = tree.items.get(base_type(command.get("item_type", "")))
            if entry is None or "cost" not in entry:
                return None
            total += int(entry["cost"])
        return total

    def _budget(self, advisor: Advisor, advice: Advice | None) -> Advice | None:
        if advice is None or not advice.commands or self.reserve == 0:
            return advice
        cost = self.cost(advisor.snapshot, advice.commands)
        if cost is None or (cost > 0 and advisor.snapshot.cash + advisor.snapshot.ore - cost < self.reserve):
            return Advice(f"Waiting to preserve your {self.reserve:,}-credit reserve. Lower the reserve to fund the next production step.", key="blocked:reserve")
        return advice

    def state(self, snapshot: GameSnapshot | None, threat: ThreatAssessment) -> dict:
        if snapshot is None:
            return {"active": None, "choices": [], "context": "connecting", "reason": "Waiting for the battlefield.", "reserve": self.reserve}
        context, choices, reason = situation(snapshot, threat)
        # Hold recommendations for 10 seconds of game time; urgent pressure and match end interrupt immediately.
        if not self.context or context in {"under_pressure", "finished", "mission"} or snapshot.tick - self.changed_tick >= 250:
            if context != self.context:
                self.changed_tick = snapshot.tick
            self.context, self.choices, self.reason = context, choices, reason
        def card(key: str) -> dict:
            name, intent, tradeoff = STRATEGIES[key]
            return {"id": key, "name": name, "intent": intent, "tradeoff": tradeoff}
        active = None
        if self.active:
            advice = self.advice(snapshot, threat)
            active = {**card(self.active), "selected_tick": self.selected_tick,
                      "next": advice.text if advice else "Wait for current production and orders to finish.",
                      "status": "finished" if snapshot.done else "blocked" if advice and advice.key.startswith("blocked") else "monitoring" if advice and advice.key.startswith("monitor") else "active",
                      "progress": f"{snapshot.harvester_count}/{desired_harvester_count(snapshot)} harvesters" if self.active == "economy"
                                  else f"{sum(unit.can_attack for unit in snapshot.units)} fighters · {round(snapshot.explored_percent)}% explored"}
        return {"active": active, "choices": [card(key) for key in self.choices], "all": [card(key) for key in STRATEGIES],
                "context": self.context, "reason": self.reason, "reserve": self.reserve, "tick": snapshot.tick,
                "available": not snapshot.done and not snapshot.mission_mode,
                "execution": "Proposed steps need your acceptance. You keep direct control."}
