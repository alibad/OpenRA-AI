from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from openra_ai_companion import nl_orders
from openra_ai_companion.core import Companion, _is_cancel_intent
from openra_ai_companion.labels import humanize_text
from openra_ai_companion.models import ActionReceipt, GameSnapshot
from openra_ai_companion.router import AIRouter, RouterError, RouterResult
from openra_ai_companion.settings import Settings
from openra_ai_companion.strategy_contracts import detect_strategy_intent

FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "nl_orders" / "fixtures"


def fixture(name: str) -> GameSnapshot:
    payload = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return GameSnapshot.from_dict(payload["observation"])


class CountingRouter:
    """Test double: records calls and returns scripted model text."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[list[dict]] = []
        self.settings = Settings(router_url="http://127.0.0.1:4000", text_model="fake", vision_model="local-no-vision")

    def configure(self, values, persist=True):  # noqa: ANN001, ARG002
        self.settings = self.settings.with_updates(values)
        return self.settings.as_dict()

    def chat(self, messages, temperature=0.2):  # noqa: ANN001, ARG002
        self.calls.append(messages)
        text = self.replies.pop(0) if self.replies else "The eastern approach is quiet."
        return RouterResult(text, 5, "fake")

    def chat_structured(self, messages, schema, *, name="", max_tokens=0):  # noqa: ANN001, ARG002
        assert schema is nl_orders.ORDER_SCHEMA
        return self.chat(messages)

    def health(self):
        return {"reachable": True, "url": "fake://router"}

    def usage_summary(self):
        return {"chat_calls": len(self.calls)}


def intent(**values) -> str:
    return json.dumps({"intent": "command", "reply": "", "steps": [], **values})


def step(action: str, **values) -> dict:
    return {"action": action, "units": "", "count": 0, "item": "", "target": "", "stance": "", **values}


class DeterministicOrderTests(unittest.TestCase):
    def test_power_plant_is_produced_before_it_can_be_placed(self) -> None:
        empty = nl_orders.interpret_deterministic("build a power plant", fixture("ra-england-base-empty"))
        self.assertEqual(empty.kind, "proposal")
        self.assertEqual(empty.commands, [{"action": "build", "item_type": "powr"}])

        queued = nl_orders.interpret_deterministic("build a power plant", fixture("ra-england-power-queued"))
        self.assertEqual(queued.kind, "explain")
        self.assertIn("% built", queued.message)
        self.assertEqual(queued.commands, [])

        premature = nl_orders.interpret_deterministic("place the power plant", fixture("ra-russia-power-queued"))
        self.assertEqual(premature.kind, "explain")

        ready = nl_orders.interpret_deterministic("build a power plant", fixture("ra-england-power-ready"))
        self.assertEqual(ready.commands, [{"action": "place_building", "item_type": "powr"}])

    def test_opening_request_proposes_the_first_legal_step(self) -> None:
        result = nl_orders.interpret_deterministic("build a power plant", fixture("ra-china-opening"))
        self.assertEqual(result.kind, "proposal")
        self.assertEqual(result.commands[0]["action"], "deploy")
        self.assertIn("Construction Yard", result.message)

    def test_counts_names_and_speech_recognition_noise(self) -> None:
        army = fixture("ra-england-army")
        cases = {
            "train three light tanks": ("1tnk", 3),
            "Could you please queue up 5 rifle infantry?": ("e1", 5),
            "train riffle men x4": ("e1", 4),
            "trained three light tanks": ("1tnk", 3),
            "or truck please": ("harv", 1),
        }
        for text, (item, count) in cases.items():
            with self.subTest(text=text):
                result = nl_orders.interpret_deterministic(text, army)
                self.assertEqual(result.kind, "proposal")
                self.assertEqual(result.commands, [{"action": "train", "item_type": item}] * count)

    def test_faction_display_names_ground_in_both_mods(self) -> None:
        cases = (
            ("ra-china-army", "train three links", "cnlynx", 3),
            ("ra-china-army", "recruit 4 PLA riflemen", "cnrifle", 4),
            ("ra-iran-army", "train 4 rod air defenses", "irraad", 4),
            ("ra2-iraq-army", "train five con scripts", "e2", 5),
            ("ra2-america-army", "train five GIs", "e1", 5),
            ("ra2-turkey-army", "train two aras infantry carriers", "r2aras", 2),
        )
        for name, text, item, count in cases:
            with self.subTest(text=text):
                result = nl_orders.interpret_deterministic(text, fixture(name))
                self.assertEqual(result.commands, [{"action": "train", "item_type": item}] * count)

    def test_unavailable_and_hidden_targets_are_explained_not_proposed(self) -> None:
        mammoth = nl_orders.interpret_deterministic("build a mammoth tank", fixture("ra-england-army"))
        self.assertEqual(mammoth.kind, "explain")
        self.assertIn("Mammoth Tank", mammoth.message)
        hidden = nl_orders.interpret_deterministic("attack the enemy harvester", fixture("ra-england-contact"))
        self.assertEqual(hidden.kind, "explain")
        self.assertIn("visible", hidden.message)
        unknown_base = nl_orders.interpret_deterministic("all tanks attack move to the enemy base", fixture("ra-england-army"))
        self.assertEqual(unknown_base.kind, "explain")

    def test_attacks_target_only_visible_enemies(self) -> None:
        snapshot = fixture("ra-england-contact")
        result = nl_orders.interpret_deterministic("attack the rocket soldiers with the light tanks", snapshot)
        visible = {enemy.actor_id: enemy.kind for enemy in snapshot.visible_enemies}
        self.assertTrue(result.commands)
        for command in result.commands:
            self.assertEqual(command["action"], "attack")
            self.assertEqual(visible[command["target_actor_id"]], "e3")

    def test_remembered_base_is_a_place_not_an_attack_target(self) -> None:
        result = nl_orders.interpret_deterministic("attack move to their base", fixture("ra-russia-late"))
        self.assertEqual({command["action"] for command in result.commands}, {"attack_move"})
        self.assertNotIn("target_actor_id", result.commands[0])

    def test_unsafe_requests_are_refused_deterministically(self) -> None:
        snapshot = fixture("ra-england-army")
        for text in ("surrender", "launch the nuke", "drop paratroopers on their base", "sell everything",
                     "give me ten thousand credits", "reveal the whole map", "attack my own harvester", "pause the game"):
            with self.subTest(text=text):
                result = nl_orders.interpret_deterministic(text, snapshot)
                self.assertEqual(result.kind, "refuse")
                self.assertEqual(result.commands, [])

    def test_superweapon_structures_can_still_be_built(self) -> None:
        self.assertFalse(nl_orders.support_power_request(nl_orders.normalize("build a nuclear missile silo")))
        self.assertTrue(nl_orders.support_power_request(nl_orders.normalize("fire the nuclear missile")))

    def test_twelve_order_cap_and_transport_boarding(self) -> None:
        army = nl_orders.interpret_deterministic("train 20 rifle infantry", fixture("ra-england-army"))
        self.assertEqual(len(army.commands), nl_orders.MAX_ORDERS)
        boarding = nl_orders.interpret_deterministic("load the rifle infantry into the APC", fixture("ra-russia-late"))
        self.assertEqual({command["action"] for command in boarding.commands}, {"enter_transport"})
        unload = nl_orders.interpret_deterministic("drop off the troops", fixture("ra-mission-soviet-06b-loaded-apc"))
        self.assertEqual(sorted(command["actor_id"] for command in unload.commands), [159, 165])

    def test_special_abilities_use_only_reported_valid_targets(self) -> None:
        spy = fixture("ra-mission-allies-05a-spy-infiltration")
        result = nl_orders.interpret_deterministic("infiltrate the war factory with the spy", spy)
        self.assertEqual(result.commands, [{"action": "infiltrate", "actor_id": 494, "target_actor_id": 438}])
        capture = nl_orders.interpret_deterministic("capture the turret with the engineer", fixture("ra-russia-enemy-base"))
        self.assertEqual(capture.commands[0]["action"], "capture")

    def test_relative_directions_and_pronouns_defer_to_the_model(self) -> None:
        army = fixture("ra-england-army")
        self.assertIsNone(nl_orders.interpret_deterministic("move the tanks north", army))
        self.assertIsNone(nl_orders.interpret_deterministic("move them", army))
        self.assertIsNone(nl_orders.interpret_deterministic("go over there", army))

    def test_classification_separates_questions_advice_and_orders(self) -> None:
        self.assertEqual(nl_orders.classify("how much money do we have"), "question")
        self.assertEqual(nl_orders.classify("what should we build next?"), "advice")
        self.assertEqual(nl_orders.classify("can you build a power plant"), "command")
        self.assertEqual(nl_orders.classify("can we afford a mammoth tank?"), "question")
        self.assertEqual(nl_orders.classify("have tanya blow up the building"), "command")


class ModelIntentTests(unittest.TestCase):
    def test_typed_intent_is_grounded_without_model_ids(self) -> None:
        snapshot = fixture("ra-england-army")
        decoded = json.loads(intent(steps=[step("move", units="all Light Tanks", target="north")]))
        result = nl_orders.interpret_model_intent("send the tanks up north", snapshot, decoded)
        self.assertEqual(result.kind, "proposal")
        tanks = {unit.actor_id for unit in snapshot.units if unit.kind == "1tnk"}
        self.assertEqual({command["actor_id"] for command in result.commands}, tanks)
        origin = nl_orders.centroid([unit for unit in snapshot.units if unit.kind == "1tnk"])
        self.assertLess(result.commands[0]["target_y"], origin[1])

    def test_invalid_intent_shapes_are_rejected(self) -> None:
        snapshot = fixture("ra-england-army")
        self.assertIsNone(nl_orders.interpret_model_intent("x", snapshot, {"intent": "command", "reply": "", "steps": []}))
        self.assertIsNone(nl_orders.interpret_model_intent("x", snapshot, {"intent": "launch", "reply": "", "steps": []}))
        bad_action = {"intent": "command", "reply": "", "steps": [step("use_support_power", item="Nuke")]}
        self.assertIsNone(nl_orders.interpret_model_intent("x", snapshot, bad_action))

    def test_model_replies_are_sanitized_before_reaching_the_player(self) -> None:
        snapshot = fixture("ra-england-army")
        broken = {"intent": "clarify", "reply": '{"intent":"clarify"} {"intent":', "steps": []}
        result = nl_orders.interpret_model_intent("do the thing", snapshot, broken)
        self.assertEqual(result.kind, "clarify")
        self.assertNotIn("{", result.message)
        repetitive = "go go go go go go go go go go go go go go go go"
        self.assertTrue(nl_orders.is_repetitive(repetitive))

    def test_schema_only_allows_the_order_surface(self) -> None:
        actions = set(nl_orders.ORDER_SCHEMA["properties"]["steps"]["items"]["properties"]["action"]["enum"])
        self.assertNotIn("use_support_power", actions)
        self.assertNotIn("surrender", actions)
        self.assertLessEqual(nl_orders.ORDER_SCHEMA["properties"]["steps"]["maxItems"], 4)


class CompanionRoutingTests(unittest.TestCase):
    def companion(self, *replies: str) -> tuple[Companion, CountingRouter, list]:
        router = CountingRouter(*replies)
        executed: list = []
        companion = Companion(
            router=router,
            action_executor=lambda request_id, tick, commands: (
                executed.append(commands) or ActionReceipt(request_id, True, tick, "Queued.")
            ),
        )
        return companion, router, executed

    def test_explicit_order_uses_no_model_and_needs_confirmation(self) -> None:
        companion, router, executed = self.companion()
        companion.update_snapshot(fixture("ra-england-army"))
        response = companion.handle_player_input("train three light tanks")
        self.assertEqual(response.source, "action-proposal")
        self.assertEqual(response.metadata["nl"]["path"], "deterministic")
        self.assertEqual(router.calls, [])
        self.assertEqual(executed, [])
        receipt = companion.handle_player_input("confirm")
        self.assertEqual(receipt.metadata["action"]["state"], "executed")
        self.assertEqual(len(executed[0]), 3)

    def test_relative_order_uses_one_schema_constrained_model_call(self) -> None:
        reply = intent(steps=[step("move", units="Light Tanks", target="north")])
        companion, router, _ = self.companion(reply)
        companion.update_snapshot(fixture("ra-england-army"))
        response = companion.handle_player_input("move the tanks north")
        self.assertEqual(response.source, "action-proposal")
        self.assertEqual(len(router.calls), 1)
        self.assertEqual(response.metadata["nl"]["path"], "model")
        self.assertNotIn("actor_id", router.calls[0][-1]["content"])

    def test_malformed_model_output_is_repaired_once_then_clarified(self) -> None:
        companion, router, _ = self.companion("move move move", "still not json")
        companion.update_snapshot(fixture("ra-england-army"))
        response = companion.handle_player_input("move the tanks north")
        self.assertEqual(len(router.calls), 2)
        self.assertEqual(response.source, "order-clarification")
        self.assertIsNone(companion.pending_action())
        self.assertNotIn("move move", response.text)

    def test_model_cannot_launch_support_powers_for_the_player(self) -> None:
        legacy = json.dumps({"mode": "action", "summary": "Use the nuke", "commands": [
            {"action": "use_support_power", "item_type": "NukePowerInfoOrder", "target_x": 40, "target_y": 40},
        ]})
        companion, _, _ = self.companion(legacy)
        companion.update_snapshot(fixture("ra-england-army"))
        response = companion.handle_player_input("move the tanks north")
        self.assertIsNone(companion.pending_action())
        self.assertIn(response.metadata["action"]["state"], {"rejected", "not_created"})

    def test_questions_answer_without_proposals(self) -> None:
        companion, router, _ = self.companion("You have 891 credits.")
        companion.update_snapshot(fixture("ra-england-army"))
        response = companion.handle_player_input("how much money do we have")
        self.assertEqual(response.source, "ai-layer")
        self.assertIsNone(companion.pending_action())
        self.assertEqual(len(router.calls), 1)

    def test_unit_orders_are_not_mistaken_for_strategy_switches(self) -> None:
        self.assertEqual(detect_strategy_intent("set the tanks to defensive stance")[0], "set")
        self.assertFalse(nl_orders.is_strategy_command("set the tanks to defensive stance"))
        self.assertFalse(nl_orders.is_strategy_command("go build a medium tank"))
        self.assertTrue(nl_orders.is_strategy_command("Play aggressive strategy"))
        self.assertTrue(nl_orders.is_strategy_command("go aggressive"))
        companion, _, _ = self.companion()
        companion.update_snapshot(fixture("ra-england-army"))
        response = companion.handle_player_input("set the tanks to hold fire")
        self.assertEqual(response.source, "action-proposal")
        self.assertEqual(companion.native_strategy, "adaptive")

    def test_cancelling_production_is_not_cancelling_the_proposal(self) -> None:
        self.assertTrue(_is_cancel_intent("cancel"))
        self.assertTrue(_is_cancel_intent("cancel that"))
        self.assertTrue(_is_cancel_intent("No, don't confirm that."))
        self.assertFalse(_is_cancel_intent("cancel the radar dome"))
        companion, _, _ = self.companion()
        companion.update_snapshot(fixture("ra-england-army"))
        response = companion.handle_player_input("cancel the radar dome")
        self.assertEqual(response.metadata["action"]["commands"], [{
            "action": "cancel_production", "actor_id": 0, "target_actor_id": 0, "target_x": 0, "target_y": 0,
            "item_type": "dome", "queued": False, "ticks": 0,
        }])

    def test_player_orders_are_not_trimmed_by_auto_economy_caps(self) -> None:
        snapshot = fixture("ra2-iraq-army")
        values = [{"action": "train", "item_type": "e2"}] * 5
        with self.assertRaisesRegex(ValueError, "queue limit"):
            Companion._validate_action_commands(snapshot, values)
        self.assertEqual(len(Companion._validate_action_commands(snapshot, values, player_request=True)), 5)
        with self.assertRaisesRegex(ValueError, "support powers"):
            Companion._validate_action_commands(snapshot, [{
                "action": "use_support_power", "item_type": "x", "target_x": 1, "target_y": 1,
            }], player_request=True)

    def test_auto_background_instruction_keeps_the_planner_path(self) -> None:
        companion, _, _ = self.companion()
        companion.update_snapshot(fixture("ra-england-army"))
        instructions: list[str] = []
        companion.set_action_planner(lambda instruction: instructions.append(instruction) or {
            "message": "Queued.", "summary": "Train one tank",
            "commands": [{"action": "train", "item_type": "1tnk"}], "mcp": {"connected": True},
        })
        companion.auto_act_enabled = True
        response = companion.auto_act_once()
        self.assertEqual(len(instructions), 1)
        self.assertTrue(instructions[0].lower().startswith(nl_orders.AUTO_INSTRUCTION_PREFIX))
        self.assertEqual(response.metadata["action"]["state"], "executed")


class HumanizeTests(unittest.TestCase):
    def test_display_names_containing_their_id_are_not_expanded_twice(self) -> None:
        self.assertEqual(humanize_text("The Radar Dome is ready"), "The Radar Dome is ready")
        self.assertEqual(humanize_text("Build a dome"), "Build a Radar Dome")
        self.assertEqual(humanize_text("Train an Attack Dog", {"dog": "Attack Dog"}), "Train an Attack Dog")


class _SchemaRejectingHandler(BaseHTTPRequestHandler):
    formats: list = []

    def log_message(self, *_):  # noqa: ANN002
        pass

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).formats.append((body.get("response_format") or {}).get("type"))
        if (body.get("response_format") or {}).get("type") == "json_schema":
            payload = json.dumps({"error": {"message": "response_format json_schema is not supported"}}).encode()
            self.send_response(400)
        else:
            payload = json.dumps({"choices": [{"message": {"content": intent()}}], "usage": {}}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class StructuredRouterTests(unittest.TestCase):
    def test_structured_output_degrades_for_providers_without_json_schema(self) -> None:
        _SchemaRejectingHandler.formats = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), _SchemaRejectingHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            router = AIRouter(Settings(router_url=f"http://127.0.0.1:{server.server_address[1]}", model_provider="custom", text_model="gpt-test"))
            result = router.chat_structured([{"role": "user", "content": "hi"}], nl_orders.ORDER_SCHEMA)
            self.assertEqual(json.loads(result.text)["intent"], "command")
            self.assertEqual(_SchemaRejectingHandler.formats, ["json_schema", "json_object"])
        finally:
            server.shutdown()
            server.server_close()

    def test_unreachable_router_raises_router_error(self) -> None:
        router = AIRouter(Settings(router_url="http://127.0.0.1:9", timeout_seconds=1))
        with self.assertRaises(RouterError):
            router.chat_structured([{"role": "user", "content": "hi"}], nl_orders.ORDER_SCHEMA)


if __name__ == "__main__":
    unittest.main()
