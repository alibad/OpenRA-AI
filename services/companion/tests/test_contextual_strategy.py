from dataclasses import replace
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from openra_ai_companion.contextual_strategy import ContextualStrategy, situation
from openra_ai_companion.models import GameSnapshot, ThreatAssessment, Unit
from openra_ai_companion.server import create_server
from test_cocommander_live_fixes import companion, iran


def mature(**changes):
    original = iran(production=[])
    return replace(original, tick=4000, cash=10000, ore=0, power_provided=1000, power_drained=100,
                   buildings=tuple(Unit(100+i, kind, 10+i*5, 10, is_building=True) for i, kind in enumerate(
                       ("nacnst", "napowr", "narefn", "nahand", "naweap"))),
                   units=tuple(Unit(200+i, "r2zulfiqar", 40+i, 40, idle=True, can_attack=True, cost=900) for i in range(10)),
                   available_production=("r2zulfiqar", "harv"), harvester_count=4, **changes)


def test_contexts_and_urgent_change():
    plan = ContextualStrategy()
    start = replace(mature(), tick=100, explored_percent=0)
    state = plan.state(start, ThreatAssessment())
    assert [item["id"] for item in state["choices"]] == ["economy", "scout", "balanced"]
    air = replace(start, tick=110, visible_enemies=(Unit(99, "jet", target_types=("Air",), can_attack=True),))
    assert plan.state(air, ThreatAssessment())["context"] == "opening"
    assert plan.state(replace(air, tick=400), ThreatAssessment())["context"] == "air_contact"
    critical = ThreatAssessment(level="critical", score=90)
    assert plan.state(replace(air, tick=401), critical)["context"] == "under_pressure"
    assert plan.state(replace(air, tick=402, done=True), critical)["available"] is False


def test_armor_and_loss_context_use_observed_evidence():
    snap = mature(visible_enemies=(Unit(999, "tank", armor_type="Heavy"),))
    assert situation(snap, ThreatAssessment())[0] == "armor_contact"
    assert situation(mature(deaths_cost=3000, kills_cost=100), ThreatAssessment())[0] == "recovering"
    assert situation(mature(visible_enemy_buildings=(Unit(998, "factory"),)), ThreatAssessment())[0] == "attack_ready"


def test_economy_does_not_suggest_an_attack():
    snap = mature(visible_enemy_buildings=(Unit(999, "factory", 60, 60),))
    plan = ContextualStrategy()
    plan.select("economy", 0, snap)
    assert plan.advice(snap, ThreatAssessment()).key == "monitor:economy"
    plan.select("pressure", 0, snap)
    advice = plan.advice(snap, ThreatAssessment())
    assert advice.key == "pressure"
    assert len(advice.commands) == 8  # two idle fighters remain at home
    assert all(command["target_x"] == 60 for command in advice.commands)


def test_defense_and_regroup_never_fall_back_to_attacking_enemy_base():
    snap = mature(visible_enemy_buildings=(Unit(999, "factory", 60, 60),))
    plan = ContextualStrategy()
    plan.select("defend", 0, snap)
    assert all(command["action"] == "guard" for command in plan.advice(snap, ThreatAssessment()).commands)
    plan.select("regroup", 0, snap)
    assert plan.advice(snap, ThreatAssessment()).key == "blocked:regroup"  # no spatial data, no invented move target


@pytest.mark.parametrize("goal,item", [("anti_air", "r2raad"), ("anti_armor", "r2toophan")])
def test_counter_production_uses_full_rule_authored_roles(goal, item):
    snap = replace(mature(), available_production=(item,))
    plan = ContextualStrategy()
    plan.select(goal, 0, snap)
    assert plan.advice(snap, ThreatAssessment()).commands == [{"action": "train", "item_type": item}]
    snap = replace(snap, units=tuple(Unit(700+i, item, can_attack=True) for i in range(4)))
    assert plan.advice(snap, ThreatAssessment()).key == "monitor:counter"


def test_counter_uses_missing_prerequisite_without_inventing_actor():
    snap = replace(mature(), buildings=tuple(building for building in mature().buildings if building.kind != "nahand"),
                   available_production=("nahand",))
    plan = ContextualStrategy()
    plan.select("anti_armor", 0, snap)
    advice = plan.advice(snap, ThreatAssessment())
    assert advice.commands == [{"action": "build", "item_type": "nahand"}]


def test_emergency_power_and_placement_outrank_goal():
    snap = iran()
    plan = ContextualStrategy()
    plan.select("pressure", 0, snap)
    assert plan.advice(snap, ThreatAssessment()).key == "place"
    snap = replace(mature(), power_provided=0, available_production=("napowr",))
    assert plan.advice(snap, ThreatAssessment()).key == "build:power"


def test_invalid_selection_and_reserve_are_atomic():
    plan = ContextualStrategy()
    snap = mature()
    plan.select("economy", 500, snap)
    for strategy, reserve in [("unknown", 0), ("defend", -1), ("defend", True), ("defend", 10001), ("defend", 0.5)]:
        with pytest.raises(ValueError):
            plan.select(strategy, reserve, snap)
        assert plan.active == "economy" and plan.reserve == 500
    with pytest.raises(ValueError):
        plan.select("defend", 0, replace(snap, mission_mode=True))


def test_select_offer_confirm_and_switch_preserve_player_orders():
    bot, router, executed = companion()
    snap = iran(production=[])
    bot.update_snapshot(snap)
    bot.select_contextual_strategy("economy")
    response = bot.contextual_strategy_step()
    assert response.metadata["action"]["state"] == "pending"
    assert not executed
    own_id = response.metadata["action"]["proposal_id"]
    player = bot.handle_player_input("Send the tanks east.")
    player_id = player.metadata["action"]["proposal_id"]
    bot.select_contextual_strategy("defend")
    ids = [proposal["proposal_id"] for proposal in bot.pending_actions()]
    assert own_id not in ids and player_id in ids
    bot.select_contextual_strategy(None)
    assert player_id in [proposal["proposal_id"] for proposal in bot.pending_actions()]
    assert bot.auto_act_enabled is False
    assert not router.calls


def test_rejected_step_is_not_reoffered_until_state_changes():
    bot, _, _ = companion()
    bot.update_snapshot(iran(production=[]))
    bot.select_contextual_strategy("economy")
    response = bot.contextual_strategy_step(automatic=True)
    bot.cancel_action(response.metadata["action"]["proposal_id"])
    assert "action" not in bot.contextual_strategy_step(automatic=True).metadata
    assert "action" in bot.contextual_strategy_step().metadata  # explicit request can retry


def test_reserve_is_checked_again_at_confirmation():
    bot, _, executed = companion()
    snap = replace(iran(production=[]), cash=5000, ore=0)
    bot.update_snapshot(snap)
    bot.select_contextual_strategy("economy", 1000)
    response = bot.contextual_strategy_step()
    bot.update_snapshot(replace(snap, tick=snap.tick+1, cash=1000))
    receipt = bot.confirm_action(response.metadata["action"]["proposal_id"])
    assert receipt.metadata["action"]["state"] == "rejected"
    assert not executed


def test_reserve_does_not_block_free_deployment():
    bot, _, executed = companion()
    snap = GameSnapshot(tick=10, cash=100, map_width=64, map_height=64, units=(Unit(1, "smcv"),))
    bot.update_snapshot(snap)
    bot.select_contextual_strategy("economy", 10000)
    response = bot.contextual_strategy_step()
    assert response.metadata["action"]["commands"][0]["action"] == "deploy"
    receipt = bot.confirm_action(response.metadata["action"]["proposal_id"])
    assert receipt.metadata["action"]["state"] == "executed"
    assert len(executed) == 1


def test_new_match_resets_selection_and_offers():
    bot, _, _ = companion()
    snap = iran(production=[])
    bot.update_snapshot(snap)
    bot.select_contextual_strategy("economy", 500)
    bot.contextual_strategy_step()
    bot.update_snapshot(replace(snap, tick=0))
    assert bot.contextual_strategy_state()["active"] is None
    assert bot.contextual_strategy_state()["reserve"] == 0
    assert bot.pending_actions() == []


def test_voice_selection_and_advice_use_goal():
    bot, router, _ = companion()
    bot.update_snapshot(mature(visible_enemy_buildings=(Unit(999, "factory", 60, 60),)))
    response = bot.handle_player_input("Choose expand economy")
    assert response.metadata["contextual_strategy"]["active"]["id"] == "economy"
    assert "Expand economy" in bot.handle_player_input("What strategy are we using?").text
    assert "Income goal" in bot.handle_player_input("What should I do next?").text
    assert not router.calls


def test_open_questions_include_player_selected_goal():
    bot, router, _ = companion("Protect the economy before attacking.")
    bot.update_snapshot(mature())
    bot.select_contextual_strategy("economy", 500)
    bot.ask("Should I commit the army now?")
    context = json.loads(router.calls[-1][-1]["content"])
    assert context["player_selected_strategy"]["active"]["id"] == "economy"
    assert context["player_selected_strategy"]["reserve"] == 500


def test_http_contract_and_bad_input():
    bot, _, _ = companion()
    bot.update_snapshot(iran(production=[]))
    server = create_server(port=0, companion=bot)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    root = f"http://127.0.0.1:{server.server_port}"
    def request(path, payload=None):
        req = Request(root + path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Content-Type": "application/json"})
        with urlopen(req) as response:
            return json.load(response)
    try:
        assert len(request("/v1/strategies")["choices"]) == 3
        assert len(request("/v1/state")["contextual_strategy"]["choices"]) == 3
        assert request("/v1/strategies", {"strategy": "economy", "reserve": 0})["active"]["id"] == "economy"
        assert request("/v1/strategies/step", {"automatic": False})["metadata"]["action"]["state"] == "pending"
        with pytest.raises(HTTPError) as error:
            request("/v1/strategies", {"strategy": "unknown"})
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
