"""Fixes from the first live co-commander test on real local models (RTSAI-WebGame, 7 October).

1. Offers survive unrelated questions (the Power Plant was never placed).
2. Items that are not buildable yet are recognised and their prerequisite is explained and offered.
3. "What should I build first?" no longer runs the multi-call planner.
4. Order parsing and grounding for the misses (generic "soldiers", compass directions, "the center").
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from openra_ai_companion import nl_orders
from openra_ai_companion.advisor import Advisor, is_next_step_question
from openra_ai_companion.core import Companion
from openra_ai_companion.models import ActionReceipt, GameSnapshot
from openra_ai_companion.router import RouterResult
from openra_ai_companion.settings import Settings
from openra_ai_companion.techtree import TechTree, load

FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "nl_orders" / "fixtures"


def fixture(name: str) -> GameSnapshot:
    payload = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return GameSnapshot.from_dict(payload["observation"])


class CountingRouter:
    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[list[dict]] = []
        self.settings = Settings(router_url="http://127.0.0.1:4000", text_model="fake", vision_model="local-no-vision")

    def configure(self, values, persist=True):  # noqa: ANN001, ARG002
        self.settings = self.settings.with_updates(values)
        return self.settings.as_dict()

    def chat(self, messages, temperature=0.2, max_tokens=None):  # noqa: ANN001, ARG002
        self.calls.append(messages)
        return RouterResult(self.replies.pop(0) if self.replies else "Hold the ridge and keep building.", 5, "fake")

    def chat_structured(self, messages, schema, *, name="", max_tokens=0):  # noqa: ANN001, ARG002
        return self.chat(messages)

    def health(self):
        return {"reachable": True, "url": "fake://router"}

    def usage_summary(self):
        return {"chat_calls": len(self.calls)}


def companion(*replies: str) -> tuple[Companion, CountingRouter, list]:
    router = CountingRouter(*replies)
    executed: list = []

    def execute(request_id, tick, commands):  # noqa: ANN001
        executed.append((request_id, tick, commands))
        return ActionReceipt(request_id, True, tick, "Queued.")

    planner = mock.Mock(side_effect=AssertionError("the multi-call planner must not run for these turns"))
    instance = Companion(router=router, action_executor=execute)
    instance.set_action_planner(planner)
    return instance, router, executed


def iran(**changes) -> GameSnapshot:
    """Iran, RTS AI standalone names, Construction Yard up, Power Plant finished and waiting."""
    payload = json.loads((FIXTURES / "ra2-iran-power-ready.json").read_text(encoding="utf-8"))["observation"]
    payload["mod_id"] = "rtsai"
    payload["actor_names"] = {**payload["actor_names"], "napowr": "Power Plant"}
    payload.update(changes)
    return GameSnapshot.from_dict(payload)


class OfferPersistenceTests(unittest.TestCase):
    def test_place_offer_survives_questions_and_unrelated_orders(self) -> None:
        bot, router, executed = companion("We have $4,800 and the Power Plant is ready.")
        bot.observe(iran())
        place = bot.pending_action()
        self.assertIsNotNone(place)
        self.assertEqual(place["commands"][0]["action"], "place_building")

        bot.handle_player_input("How is our economy?")
        order = bot.handle_player_input("Send the tanks east.")
        self.assertEqual(order.metadata["action"]["state"], "pending")
        offers = bot.pending_actions()
        self.assertEqual([offer["proposal_id"] for offer in offers],
                         [order.metadata["action"]["proposal_id"], place["proposal_id"]])

        # A bare "confirm" takes the newest card; the placement offer is still there afterwards.
        bot.handle_player_input("confirm")
        self.assertEqual(executed[-1][2][0].action, "move")
        self.assertEqual(bot.pending_action()["proposal_id"], place["proposal_id"])
        receipt = bot.confirm_action(place["proposal_id"])
        self.assertEqual(receipt.metadata["action"]["state"], "executed")
        self.assertEqual(executed[-1][2][0].action, "place_building")
        self.assertEqual(router.calls.__len__(), 1)  # the economy question only

    def test_offer_raised_during_a_question_is_held_not_lost(self) -> None:
        bot, _, _ = companion()
        queued = iran(production=[{"item": "napowr", "progress": 0.6, "queue_type": "Building"}])
        bot.observe(queued)
        bot.begin_user_turn()
        self.assertIsNone(bot.observe(iran()))  # the "ready" alert is not spoken mid-question...
        bot.end_user_turn(grace_seconds=0)
        self.assertEqual(bot.pending_action()["commands"][0]["item_type"], "napowr")  # ...but the offer is held

    def test_only_a_newer_offer_for_the_same_thing_replaces_an_offer(self) -> None:
        bot, _, _ = companion()
        bot.observe(iran())
        first = bot.pending_action()["proposal_id"]
        bot.handle_player_input("Send the tanks east.")  # another thing: both stay
        self.assertEqual(len(bot.pending_actions()), 2)
        again = bot.handle_player_input("Place the power plant.")  # the same thing: replaces it
        offers = bot.pending_actions()
        self.assertEqual(len(offers), 2)
        self.assertNotIn(first, [offer["proposal_id"] for offer in offers])
        self.assertEqual(offers[0]["proposal_id"], again.metadata["action"]["proposal_id"])

    def test_explicit_cancel_removes_one_offer_and_cancel_all_clears_them(self) -> None:
        bot, _, executed = companion()
        bot.observe(iran())
        bot.handle_player_input("Send the tanks east.")
        self.assertEqual(bot.handle_player_input("cancel").metadata["action"]["state"], "cancelled")
        self.assertEqual(len(bot.pending_actions()), 1)
        bot.handle_player_input("Send the tanks east.")
        cleared = bot.handle_player_input("cancel all of them")
        self.assertEqual(len(cleared.metadata["action"]["proposal_ids"]), 2)
        self.assertEqual(bot.pending_actions(), [])
        self.assertEqual(executed, [])

    def test_placed_building_retires_its_offer(self) -> None:
        bot, _, _ = companion()
        bot.observe(iran())
        self.assertIsNotNone(bot.pending_action())
        placed = iran(
            production=[],
            buildings=[*json.loads((FIXTURES / "ra2-iran-power-ready.json").read_text(encoding="utf-8"))["observation"]["buildings"],
                       {"actor_id": 900, "type": "napowr", "cell_x": 40, "cell_y": 40}],
        )
        bot.update_snapshot(placed)
        self.assertIsNone(bot.pending_action())

    def test_status_lists_every_waiting_offer(self) -> None:
        bot, _, _ = companion()
        bot.observe(iran())
        bot.handle_player_input("Send the tanks east.")
        status = bot.status()
        self.assertEqual(len(status["pending_actions"]), 2)
        self.assertEqual(status["pending_action"], status["pending_actions"][0])


class PrerequisiteTests(unittest.TestCase):
    def test_barracks_before_power_names_the_missing_building_and_offers_it(self) -> None:
        bot, router, _ = companion()
        bot.update_snapshot(fixture("ra2-iran-base-empty"))
        response = bot.handle_player_input("Build a barracks.")
        self.assertEqual(response.source, "action-proposal")
        self.assertIn("The Barracks needs a Tesla Reactor first.", response.text)
        self.assertNotIn("recognize", response.text)
        self.assertEqual(response.metadata["action"]["commands"], [
            {"action": "build", "actor_id": 0, "target_actor_id": 0, "target_x": 0, "target_y": 0,
             "item_type": "napowr", "queued": False, "ticks": 0},
        ])
        self.assertEqual(response.metadata["nl"]["prerequisite_for"], ["nahand"])
        self.assertEqual(router.calls, [])

    def test_finished_prerequisite_is_offered_for_placement(self) -> None:
        result = nl_orders.interpret_deterministic("build a refinery", fixture("ra2-iran-power-ready"))
        self.assertEqual(result.kind, "proposal")
        self.assertEqual(result.commands, [{"action": "place_building", "item_type": "napowr"}])
        self.assertIn("Ore Refinery needs a Tesla Reactor", result.message)

    def test_prerequisite_in_progress_is_explained_without_a_duplicate(self) -> None:
        result = nl_orders.interpret_deterministic("build a barracks", fixture("ra2-iran-power-queued"))
        self.assertEqual(result.kind, "explain")
        self.assertEqual(result.commands, [])
        self.assertIn("21% built", result.message)

    def test_deep_chain_walks_to_the_first_buildable_step(self) -> None:
        result = nl_orders.interpret_deterministic("train two tanks", fixture("ra2-iran-base-empty"))
        self.assertEqual(result.commands, [{"action": "build", "item_type": "napowr"}])
        self.assertIn("Karrar Battle Tank needs a War Factory, which needs an Ore Refinery, which needs a Tesla Reactor", result.message)

    def test_generic_soldiers_without_barracks_explains_the_barracks(self) -> None:
        result = nl_orders.interpret_deterministic("Train three soldiers.", fixture("ra2-iran-power-ready"))
        self.assertEqual(result.commands, [{"action": "place_building", "item_type": "napowr"}])
        self.assertIn("Basij Rifleman needs a Barracks", result.message)

    def test_other_factions_units_are_named_as_such(self) -> None:
        result = nl_orders.interpret_deterministic("build a grizzly tank", fixture("ra2-iran-army"))
        self.assertEqual(result.kind, "explain")
        self.assertIn("Iran can't build the Grizzly Battle Tank", result.message)
        self.assertIn("Karrar Battle Tank", result.message)

    def test_standalone_names_follow_the_snapshot(self) -> None:
        tree = TechTree(iran())
        self.assertEqual(tree.profile, "standalone")
        self.assertEqual(tree.faction, "iran")
        result = nl_orders.interpret_deterministic("build a radar", iran(production=[]))
        self.assertIn("The Radar Tower needs a Power Plant and an Ore Refinery first.", result.message)


class RosterRecognitionTests(unittest.TestCase):
    """Every unit and building of every faction resolves by its name, aliases and catalog names."""

    @staticmethod
    def faction_snapshot(profile: str, faction: str) -> GameSnapshot:
        tree = load()["profiles"][profile]["factions"][faction]
        others = [name for name in load()["profiles"][profile]["factions"] if name != faction]
        unique = next(item for item in tree["items"] if all(
            item not in load()["profiles"][profile]["factions"][other]["items"] for other in others
        ))
        yard = next(item for item in tree["start"] if tree["items"].get(item, {}).get("kind") == "building")
        names = {yard: tree["items"][yard]["name"], unique: tree["items"][unique]["name"]}
        # A name that differs between profiles pins the profile, as the live game's names do.
        other = next(name for name in load()["profiles"] if name != profile)
        other_items = load()["profiles"][other]["factions"].get(faction, {}).get("items", {})
        distinct = [item for item, entry in tree["items"].items()
                    if item in other_items and other_items[item]["name"] != entry["name"]]
        for item in distinct[:3]:
            names[item] = tree["items"][item]["name"]
        return GameSnapshot.from_dict({
            "tick": 500, "mod_id": "rtsai", "map_info": {"width": 96, "height": 96},
            "buildings": [{"actor_id": 1, "type": yard, "cell_x": 40, "cell_y": 40}],
            "units": [{"actor_id": 2, "type": unique, "cell_x": 42, "cell_y": 42, "can_attack": True, "speed": 50}],
            "available_production": distinct[:3], "actor_names": names,
        })

    def test_every_faction_item_is_recognised_by_name_and_catalog_name(self) -> None:
        catalog = load()["catalog"]
        for profile, data in load()["profiles"].items():
            for faction, tree in data["factions"].items():
                snapshot = self.faction_snapshot(profile, faction)
                grounder = nl_orders.Grounder(snapshot)
                self.assertEqual((grounder.vocabulary.tree.profile, grounder.vocabulary.tree.faction), (profile, faction))
                names: dict[str, set[str]] = {}
                for item, entry in tree["items"].items():
                    names.setdefault(entry["name"].lower(), set()).add(item)
                for item, entry in tree["items"].items():
                    if item in tree["start"]:
                        continue
                    with self.subTest(profile=profile, faction=faction, item=item, name=entry["name"]):
                        found = grounder.roster_item(entry["name"])
                        self.assertIn(found, names[entry["name"].lower()])
                    for alias in catalog.get(item, {}).get("names", ()):
                        with self.subTest(profile=profile, faction=faction, item=item, catalog=alias):
                            self.assertEqual(grounder.roster_item(alias), item)

    def test_common_aliases_reach_the_faction_building(self) -> None:
        snapshot = self.faction_snapshot("standalone", "iran")
        grounder = nl_orders.Grounder(snapshot)
        for spoken, item in (("rax", "nahand"), ("war factory", "naweap"), ("refinery", "narefn"),
                             ("radar", "naradr"), ("power plant", "napowr"), ("service depot", "nadept")):
            with self.subTest(spoken=spoken):
                self.assertEqual(grounder.roster_item(spoken), item)

    def test_tech_tree_data_is_consistent(self) -> None:
        data = load()
        self.assertEqual(sorted(data["profiles"]["standalone"]["factions"]),
                         ["china", "hezbollah", "iran", "israel", "saudi", "turkey", "yemen"])
        for profile in data["profiles"].values():
            for faction, tree in profile["factions"].items():
                with self.subTest(faction=faction):
                    self.assertTrue(any(tree["items"].get(item, {}).get("kind") == "building" for item in tree["start"]))
                    for item, entry in tree["items"].items():
                        for group in entry["needs"]:
                            self.assertTrue(set(group) <= set(tree["items"]), (item, group))


class AdviceLatencyTests(unittest.TestCase):
    def test_what_should_i_build_first_is_decided_without_any_model_call(self) -> None:
        bot, router, _ = companion()
        bot.update_snapshot(fixture("ra2-iran-base-empty"))
        response = bot.handle_player_input("What should I build first?")
        self.assertEqual(router.calls, [])
        self.assertTrue(response.metadata["advice"]["deterministic"])
        self.assertIn("Start with a Tesla Reactor", response.text)
        self.assertEqual(response.metadata["action"]["commands"][0]["item_type"], "napowr")

    def test_what_next_follows_the_opening_and_places_finished_buildings_first(self) -> None:
        bot, router, _ = companion()
        bot.update_snapshot(fixture("ra2-iran-power-ready"))
        response = bot.handle_player_input("What should I do next?")
        self.assertEqual(response.metadata["action"]["commands"][0]["action"], "place_building")
        built = fixture("ra2-iran-army")
        advice = Advisor(built).next_step(build_focus=True)
        self.assertIsNotNone(advice)
        self.assertEqual(router.calls, [])

    def test_open_advice_makes_exactly_one_short_model_call(self) -> None:
        bot, router, _ = companion("Not yet; build a War Factory first.")
        bot.update_snapshot(fixture("ra2-iran-army"))
        response = bot.handle_player_input("Should we attack now?")
        self.assertEqual(len(router.calls), 1)
        self.assertEqual(response.text, "Not yet; build a War Factory first.")
        prompt = router.calls[0][-1]["content"]
        self.assertIn("Can train:", prompt)
        self.assertNotIn("actor_id", prompt)

    def test_status_questions_are_answered_from_the_briefing(self) -> None:
        bot, router, _ = companion()
        bot.update_snapshot(fixture("ra2-iran-army"))
        response = bot.handle_player_input("What's the situation?")
        self.assertEqual(response.source, "strategy-next-step")
        self.assertIn("Next:", response.text)
        self.assertEqual(router.calls, [])

    def test_next_step_detection(self) -> None:
        for text in ("What should I build first?", "What should I do next?", "what now", "Any advice?",
                     "What do you recommend?", "What action do you suggest?"):
            with self.subTest(text=text):
                self.assertTrue(is_next_step_question(text))
        for text in ("Should we attack now?", "How do we beat their tanks?"):
            with self.subTest(text=text):
                self.assertFalse(is_next_step_question(text))


class OrderParsingTests(unittest.TestCase):
    def test_tanks_to_the_center_use_every_tank_and_the_map_centre(self) -> None:
        snapshot = fixture("ra2-china-army")
        tanks = {unit.actor_id for unit in snapshot.units if "tank" in snapshot.actor_name(unit.kind).lower()}
        for line in ("send the tanks to the center", "send the selected tanks to the centre", "move the tanks to the middle of the map"):
            with self.subTest(line=line):
                result = nl_orders.interpret_deterministic(line, snapshot)
                self.assertEqual(result.kind, "proposal")
                self.assertEqual({command["actor_id"] for command in result.commands}, tanks)
                self.assertEqual({(command["target_x"], command["target_y"]) for command in result.commands},
                                 {(snapshot.map_width // 2, snapshot.map_height // 2)})
                self.assertEqual({command["action"] for command in result.commands}, {"move"})

    def test_compass_directions_no_longer_wait_for_a_model_call(self) -> None:
        bot, router, _ = companion()
        bot.update_snapshot(fixture("ra2-iran-army"))
        for line, label in (("Send the tanks east.", "east"), ("Send the infantry north.", "north")):
            with self.subTest(line=line):
                response = bot.handle_player_input(line)
                self.assertEqual(response.metadata["action"]["state"], "pending")
                self.assertIn(f"to the {label}", response.metadata["action"]["summary"])
        self.assertEqual(router.calls, [])

    def test_generic_soldiers_pick_the_factions_rifleman(self) -> None:
        for name, item in (("ra2-china-army", "r2cnrifle"), ("ra2-iran-army", "r2basij")):
            with self.subTest(fixture=name):
                result = nl_orders.interpret_deterministic("Train three soldiers.", fixture(name))
                self.assertEqual(result.commands, [{"action": "train", "item_type": item}] * 3)

    def test_misses_from_the_benchmark_are_parsed(self) -> None:
        cases = (
            ("ra-yemen-army", "put four riflemen in the apc", "enter_transport"),
            ("ra-england-contact", "light tanks focus the rifleman", "attack"),
            ("ra-mission-allies-05a-spy-infiltration", "spy infiltrate the war factory", "infiltrate"),
            ("ra2-america-army", "gis deploy", "deploy"),
            ("ra-germany-radar", "turn the radar dome off", "power_down"),
            ("ra-iran-army", "start repairs on the factory", "repair"),
            ("ra-russia-enemy-base", "steal the turret with the engineer", "capture"),
            ("ra-iran-army", "train some basij", "train"),
        )
        for name, line, action in cases:
            with self.subTest(line=line):
                result = nl_orders.interpret_deterministic(line, fixture(name))
                self.assertIsNotNone(result)
                self.assertEqual(result.kind, "proposal")
                self.assertEqual({command["action"] for command in result.commands}, {action})
        basij = nl_orders.interpret_deterministic("train some basij", fixture("ra-iran-army"))
        self.assertEqual(basij.commands[0]["item_type"], "irbas")  # not the sound-alike "bazooka"

    def test_named_scout_unit_is_trained_not_sent_scouting(self) -> None:
        bot, _, _ = companion()
        bot.update_snapshot(fixture("ra2-china-army"))
        response = bot.handle_player_input("train a lynx command scout")
        self.assertEqual(response.metadata["action"]["commands"][0]["item_type"], "r2lynx")

    def test_order_format_is_unchanged_for_the_engine(self) -> None:
        bot, _, executed = companion()
        bot.update_snapshot(fixture("ra2-iran-army"))
        bot.handle_player_input("Send the tanks east.")
        bot.handle_player_input("confirm")
        command = executed[0][2][0]
        self.assertEqual(command.as_dict().keys(), {
            "action", "actor_id", "target_actor_id", "target_x", "target_y", "item_type", "queued", "ticks",
        })


if __name__ == "__main__":
    unittest.main()
