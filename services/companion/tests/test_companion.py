from __future__ import annotations

import threading
import time
import unittest
import urllib.error
import urllib.request
import wave
import json
import struct
import zlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from openra_ai_companion.cli import _companion_action_loop_enabled, _match_started, _restart_auto_deadlines, _speak
from openra_ai_companion.core import Companion
from openra_ai_companion import game_mcp
from openra_ai_companion.game_runtime import GameRuntime
from openra_ai_companion.hotkeys import VoiceHotkeys, console_print, response_hud_state
from openra_ai_companion.insights import InsightEngine
from openra_ai_companion.learning import LearningStore
from openra_ai_companion.models import ActionCommand, ActionReceipt, GameSnapshot, Unit, VisionFrame
from openra_ai_companion.router import AIRouter, RouterError, RouterResult
from openra_ai_companion.server import create_server
from openra_ai_companion.settings import Settings
from openra_ai_companion.strategy import hybrid_force_plan, mission_plan, opening_scout_count, scout_targets, strategic_profile
from openra_ai_companion.tactical_vision import tactical_overview_png
from openra_ai_companion.threats import assess_threat
from openra_ai_companion.voice import _normalize_wav, _wav_bytes, playback_hold_seconds


class FakeRouter:
    def __init__(self, delay: float = 0):
        self.delay = delay
        self.calls = 0
        self.settings = Settings(router_url="http://127.0.0.1:4000", text_model="fake")

    def configure(self, values, persist=True):  # noqa: ANN001, ARG002
        self.settings = self.settings.with_updates(values)
        return self.settings.as_dict()

    def chat(self, messages, temperature=0.2):  # noqa: ANN001
        self.calls += 1
        time.sleep(self.delay)
        return RouterResult("Enemy armor is entering from the east.", round(self.delay * 1000), "fake")

    def health(self):
        return {"reachable": True, "url": "fake://router"}

    def usage_summary(self):
        return {
            "session_cost_usd": 0.001,
            "hourly_cost_usd": 0.01,
            "text_cost_usd": 0.0005,
            "speech_cost_usd": 0.0003,
            "transcription_cost_usd": 0.0002,
            "input_tokens": 100,
            "output_tokens": 20,
            "speech_characters": 30,
            "transcription_seconds": 3,
            "assumptions": ["test pricing"],
            "estimate_only": True,
        }

    def catalogue(self):
        return {
            "router_available": True,
            "detail": "test catalogue",
            "providers": [{"id": "openai", "label": "OpenAI", "requires_endpoint": False}],
            "models": [{"id": "fake", "label": "Fake", "provider": "openai", "mode": "chat", "local": False}],
            "voices": [{"id": "alloy", "label": "Alloy"}],
        }

    def transcribe(self, audio, filename="question.wav"):  # noqa: ANN001
        return RouterResult("Where is the threat?", 4, "fake-transcribe")

    def speech(self, text):  # noqa: ANN001
        return b"RIFFfake", 5, "audio/wav"

    def vision(self, prompt, image, media_type="image/png"):  # noqa: ANN001, ARG002
        return RouterResult(
            '{"biome":"desert","relief":"flat","vegetation_density":0.1,"urban_density":0.8,'
            '"water_confidence":0,"fidelity_notes":[],"summary":"Dense desert city.","confidence":0.9}',
            12,
            "fake-vision",
        )


class ScriptedRouter(FakeRouter):
    def __init__(self, response: dict, delay: float = 0):
        super().__init__(delay)
        self.response = response

    def chat(self, messages, temperature=0.2):  # noqa: ANN001, ARG002
        self.calls += 1
        time.sleep(self.delay)
        return RouterResult(json.dumps(self.response), round(self.delay * 1000), "fake-actions")


class VisionRouter(FakeRouter):
    def __init__(self, response: str = "The visible eastern approach is threatened."):
        super().__init__()
        self.response = response
        self.vision_requests = []

    def vision_many(self, prompt, images):  # noqa: ANN001
        self.calls += 1
        self.vision_requests.append((prompt, images))
        return RouterResult(self.response, 7, "fake-full-vision", vision_used=True)


class FakePlayer:
    def __init__(self):
        self.audio = b""

    def play(self, audio):  # noqa: ANN001
        self.audio = audio

    def stop(self):
        self.audio = b""


class FailingPlayer:
    def play(self, audio):  # noqa: ANN001, ARG002
        raise RuntimeError("output device unavailable")


def snapshot(**changes) -> GameSnapshot:
    base = {
        "tick": 1000,
        "cash": 3000,
        "power_provided": 100,
        "power_drained": 80,
        "harvester_count": 1,
        "units": [],
        "buildings": [],
        "visible_enemies": [],
        "visible_enemy_buildings": [],
        "production": [{"item": "1tnk", "progress": 0.5}],
    }
    base.update(changes)
    return GameSnapshot.from_dict(base)


def spatial_snapshot(width: int = 8, height: int = 8, **changes) -> GameSnapshot:
    channels = 9
    values = [0.0] * (width * height * channels)
    for cell in range(width * height):
        values[cell * channels + 3] = 1.0
        values[cell * channels + 4] = 0.5
    base = {
        "map_info": {"map_name": "Vision Test", "width": width, "height": height},
        "spatial_map": struct.pack(f"<{len(values)}f", *values),
        "spatial_channels": channels,
    }
    base.update(changes)
    return snapshot(**base)


class CompanionTests(unittest.TestCase):
    def test_first_live_snapshot_and_rematch_kick_off_the_match(self) -> None:
        first = GameSnapshot(tick=12, map_name="Snow Pass", map_width=64, map_height=64)
        later = GameSnapshot(tick=100, map_name="Snow Pass", map_width=64, map_height=64)
        rematch = GameSnapshot(tick=4, map_name="Snow Pass", map_width=64, map_height=64)
        signature = (first.map_name, first.map_width, first.map_height)

        self.assertTrue(_match_started(None, -1, first))
        self.assertFalse(_match_started(signature, first.tick, later))
        self.assertTrue(_match_started(signature, later.tick, rematch))

    def test_auto_status_uses_the_first_snapshot_before_it_is_committed(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.configure(auto_act=True)
        mission = GameSnapshot(tick=1, mission_mode=True)

        state, message = companion.idle_status(mission)

        self.assertEqual(state, "auto-active:normal")
        self.assertIn("SCRIPTED MISSION BRAIN", message)

    def test_mission_snapshot_exposes_objectives_and_spy_capabilities(self) -> None:
        current = snapshot(
            mission_mode=True,
            mission_briefing="Disguise the spy, avoid dogs, and infiltrate the weapons factory.",
            objectives=[{"id": 2, "description": "Infiltrate the weapons factory", "type": "Secondary", "required": False}],
            units=[{
                "actor_id": 7,
                "type": "spy",
                "can_disguise": True,
                "can_infiltrate": True,
                "valid_disguise_targets": [21],
                "valid_infiltration_targets": [31],
            }],
        )

        context = current.action_context()

        self.assertTrue(context["mission"]["active"])
        self.assertEqual(context["mission"]["objectives"][0]["description"], "Infiltrate the weapons factory")
        self.assertEqual(context["own_units"][0]["valid_infiltration_targets"], [31])

    def test_mission_plan_captures_legal_objective_with_engineer(self) -> None:
        current = snapshot(
            mission_mode=True,
            objectives=[{"id": 0, "description": "Capture Radar Node Seven with an engineer."}],
            units=[{
                "actor_id": 19,
                "type": "e6",
                "is_idle": True,
                "can_capture": True,
                "valid_capture_targets": [8],
            }],
        )

        plan = mission_plan(current)

        self.assertEqual(plan["phase"], "capture-mission-objective")
        self.assertEqual(plan["recommended_commands"], [{
            "action": "capture",
            "actor_id": 19,
            "target_actor_id": 8,
        }])

    def test_mission_plan_places_completed_structure_before_objective_micro(self) -> None:
        current = snapshot(
            mission_mode=True,
            objectives=[{"id": 0, "description": "Capture Radar Node Seven with an engineer."}],
            production=[{
                "queue_type": "Building",
                "item": "silo",
                "progress": 1.0,
            }],
            units=[{
                "actor_id": 19,
                "type": "e6",
                "is_idle": True,
                "can_capture": True,
                "valid_capture_targets": [8],
            }],
        )

        plan = mission_plan(current)

        self.assertEqual(plan["phase"], "place-completed-structure")
        self.assertEqual(plan["recommended_commands"], [{
            "action": "place_building",
            "item_type": "silo",
        }])

    def test_mission_auto_executes_completed_structure_placement(self) -> None:
        executions = []
        companion = Companion(
            router=FakeRouter(),
            action_executor=lambda request_id, tick, commands: (
                executions.append(commands)
                or ActionReceipt(request_id, True, tick, "Completed structure placed.")
            ),
        )
        companion.latest_snapshot = snapshot(
            tick=1010,
            mission_mode=True,
            objectives=[{"id": 0, "description": "Capture Radar Node Seven with an engineer."}],
            production=[{
                "queue_type": "Building",
                "item": "silo",
                "progress": 1.0,
            }],
        )
        companion.configure(auto_act=True)

        response = companion.auto_act_once({"type": "production_complete", "item": "silo"})

        self.assertEqual(response.metadata["action"]["state"], "executed")
        self.assertTrue(response.metadata["auto_act"])
        self.assertEqual(executions[0][0].action, "place_building")
        self.assertEqual(executions[0][0].item_type, "silo")

    def test_mission_plan_disguises_spy_before_infiltration(self) -> None:
        current = snapshot(
            mission_mode=True,
            objectives=[{"id": 0, "description": "Rescue Tanya"}],
            units=[{
                "actor_id": 7,
                "type": "spy",
                "can_disguise": True,
                "can_infiltrate": True,
                "valid_disguise_targets": [21],
            }],
            visible_enemies=[{"actor_id": 21, "type": "e1", "cell_x": 12, "cell_y": 8}],
        )

        plan = mission_plan(current)

        self.assertEqual(plan["phase"], "establish-disguise")
        self.assertEqual(plan["recommended_commands"], [{"action": "disguise", "actor_id": 7, "target_actor_id": 21}])

    def test_whats_next_in_mission_creates_accept_ready_proposal(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.latest_snapshot = snapshot(
            mission_mode=True,
            objectives=[{"id": 0, "description": "Rescue Tanya"}],
            units=[{
                "actor_id": 7,
                "type": "spy",
                "can_disguise": True,
                "valid_disguise_targets": [21],
            }],
            visible_enemies=[{"actor_id": 21, "type": "e1", "cell_x": 12, "cell_y": 8}],
        )

        response = companion.handle_player_input("What's next?")

        self.assertEqual(response.source, "mission-next-step")
        self.assertEqual(response.metadata["action"]["state"], "pending")
        self.assertEqual(response.metadata["action"]["commands"][0]["action"], "disguise")

    def test_mission_infiltration_route_avoids_visible_dog_zone(self) -> None:
        current = spatial_snapshot(
            width=24,
            height=16,
            mission_mode=True,
            objectives=[{"id": 0, "description": "Infiltrate the weapons factory"}],
            units=[{
                "actor_id": 7,
                "type": "spy",
                "cell_x": 2,
                "cell_y": 8,
                "is_idle": True,
                "can_infiltrate": True,
                "is_disguised": True,
                "valid_infiltration_targets": [31],
            }],
            visible_enemies=[{
                "actor_id": 21,
                "type": "dog",
                "cell_x": 9,
                "cell_y": 5,
                "detects_disguise": True,
            }],
            visible_enemy_buildings=[{"actor_id": 31, "type": "weap", "cell_x": 20, "cell_y": 8}],
        )

        plan = mission_plan(current)

        self.assertEqual(plan["phase"], "stealth-infiltration")
        self.assertEqual(len(plan["recommended_commands"]), 1)
        self.assertEqual(plan["recommended_commands"][0]["action"], "move")
        self.assertFalse(plan["recommended_commands"][0].get("queued", False))
        for x, y in plan["route"]:
            self.assertGreater(((x - 9) ** 2 + (y - 5) ** 2) ** 0.5, 8)

    def test_mission_plan_uses_tanya_c4_for_sam_objective(self) -> None:
        current = snapshot(
            mission_mode=True,
            objectives=[{
                "id": 3,
                "description": "Destroy all SAM Sites blocking the extraction helicopter",
            }],
            units=[{
                "actor_id": 41,
                "type": "e7.noautotarget",
                "cell_x": 10,
                "cell_y": 10,
                "is_idle": True,
                "can_demolish": True,
                "valid_demolition_targets": [51],
            }],
            visible_enemy_buildings=[{
                "actor_id": 51,
                "type": "sam",
                "cell_x": 14,
                "cell_y": 10,
            }],
        )

        plan = mission_plan(current)

        self.assertEqual(plan["phase"], "destroy-mission-blockers")
        self.assertEqual(plan["recommended_commands"], [{
            "action": "demolish",
            "actor_id": 41,
            "target_actor_id": 51,
        }])

    def test_spy_holds_final_infiltration_until_dogs_clear_entrance(self) -> None:
        current = spatial_snapshot(
            width=24,
            height=20,
            mission_mode=True,
            objectives=[{"id": 0, "description": "Infiltrate the weapons factory"}],
            units=[{
                "actor_id": 7,
                "type": "spy",
                "cell_x": 18,
                "cell_y": 10,
                "is_idle": True,
                "can_infiltrate": True,
                "is_disguised": True,
                "valid_infiltration_targets": [31],
            }],
            visible_enemies=[{
                "actor_id": 21,
                "type": "dog",
                "cell_x": 18,
                "cell_y": 19,
                "detects_disguise": True,
            }],
            visible_enemy_buildings=[{"actor_id": 31, "type": "weap", "cell_x": 20, "cell_y": 10}],
        )

        plan = mission_plan(current)

        self.assertEqual(plan["phase"], "hold-for-infiltration-window")
        self.assertEqual(plan["recommended_commands"], [])

    def test_stealth_threat_scores_dog_proximity_not_visible_base_size(self) -> None:
        current = snapshot(
            mission_mode=True,
            units=[{
                "actor_id": 7,
                "type": "spy",
                "cell_x": 5,
                "cell_y": 5,
                "can_infiltrate": True,
                "is_disguised": True,
            }],
            visible_enemies=[
                *({"actor_id": 30 + index, "type": "e1", "cell_x": 20 + index, "cell_y": 20} for index in range(12)),
                {"actor_id": 90, "type": "dog", "cell_x": 25, "cell_y": 5, "detects_disguise": True},
            ],
            visible_enemy_buildings=[{"actor_id": 100 + index, "type": "weap"} for index in range(8)],
        )

        threat = assess_threat(current)

        self.assertEqual(threat.level, "calm")
        self.assertLess(threat.score, 20)

    def test_strategy_profile_adapts_to_map_scale_and_faction(self) -> None:
        current = spatial_snapshot(width=112, height=54)

        profile = strategic_profile(current, {"player_faction": "russia", "enemy_faction": "germany"})

        self.assertEqual(profile["map_scale"], "medium")
        self.assertEqual(profile["opening_scouts"], 3)
        self.assertEqual(profile["target_harvesters"], 3)
        self.assertIn("Tesla Tanks", profile["doctrine"]["priorities"])

    def test_voice_can_query_and_switch_the_native_openra_strategy(self) -> None:
        router = FakeRouter()
        companion = Companion(router=router)
        companion.latest_snapshot = snapshot()
        switched = []
        companion.set_strategy_controller(lambda profile: switched.append(profile) or True)

        explanation = companion.handle_player_input("What strategy are we using?")
        changed = companion.handle_player_input("Play aggressive strategy")

        self.assertEqual(explanation.source, "strategy-assistant")
        self.assertIn("Current strategy", explanation.text)
        self.assertEqual(changed.source, "strategy-changed")
        self.assertEqual(companion.native_strategy, "rush")
        self.assertEqual(companion.native_profile, "rush")
        self.assertEqual(switched, ["rush"])
        self.assertEqual(router.calls, 0)

    def test_adaptive_director_can_switch_native_profile_without_leaving_adaptive_mode(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.latest_snapshot = snapshot()
        switched = []
        companion.set_strategy_controller(lambda profile: switched.append(profile) or True)

        accepted = companion.apply_adaptive_profile("turtle")

        self.assertTrue(accepted)
        self.assertEqual(companion.native_strategy, "adaptive")
        self.assertEqual(companion.native_profile, "turtle")
        self.assertEqual(switched, ["turtle"])
        self.assertEqual(companion.idle_status()[0], "ready:turtle")

        explanation = companion.handle_player_input("What strategy are we using?")
        self.assertIn("Active native profile: Fortified defense", explanation.text)
        self.assertEqual(explanation.metadata["strategy"]["active_native_profile"], "turtle")

    def test_whats_next_returns_live_plan_and_accept_action_without_model_call(self) -> None:
        router = FakeRouter()
        executed = []

        def execute(request_id, tick, commands):  # noqa: ANN001
            executed.append((request_id, tick, commands))
            return ActionReceipt(
                request_id=request_id,
                accepted=True,
                game_tick=tick,
                detail="Queued test orders.",
            )

        companion = Companion(router=router, action_executor=execute)
        current = snapshot(
            map_info={"map_name": "Singles", "width": 112, "height": 54},
            resource_capacity=5000,
            ore=1200,
            harvester_count=3,
            units=[
                *(
                    {"actor_id": actor_id, "type": "e1", "cell_x": 20, "cell_y": 20,
                     "is_idle": True, "can_attack": True}
                    for actor_id in range(1, 9)
                ),
                *(
                    {"actor_id": actor_id, "type": "3tnk", "cell_x": 22, "cell_y": 20,
                     "is_idle": True, "can_attack": True}
                    for actor_id in range(20, 26)
                ),
            ],
            buildings=[
                {"actor_id": 40, "type": "fact", "cell_x": 18, "cell_y": 18},
                {"actor_id": 41, "type": "powr", "cell_x": 15, "cell_y": 18},
                {"actor_id": 42, "type": "barr", "cell_x": 21, "cell_y": 18},
                {"actor_id": 43, "type": "proc", "cell_x": 14, "cell_y": 22},
                {"actor_id": 44, "type": "weap", "cell_x": 23, "cell_y": 22},
            ],
            visible_enemy_buildings=[
                {"actor_id": 90, "type": "weap", "cell_x": 50, "cell_y": 40},
            ],
            production=[],
            available_production=[],
            kills_cost=9000,
            deaths_cost=5000,
        )
        companion.update_snapshot(current)

        response = companion.handle_player_input(
            "Okay, so what are we gonna do next what's next what's remaining in this game"
        )

        self.assertEqual(response.source, "strategy-next-step")
        self.assertIn("Next:", response.text)
        self.assertIn("Remaining:", response.text)
        self.assertIn("ACCEPT", response.text)
        self.assertEqual(response.metadata["action"]["state"], "pending")
        self.assertEqual(router.calls, 0)

        confirmed = companion.handle_player_input("do it")
        self.assertEqual(confirmed.metadata["action"]["state"], "executed")
        self.assertTrue(executed)

    def test_whats_next_reports_native_execution_without_creating_proposal_in_auto(self) -> None:
        router = FakeRouter()
        companion = Companion(router=router)
        companion.auto_act_enabled = True
        companion.set_strategy_controller(lambda _profile: True)
        companion.update_snapshot(snapshot(production=[]))

        response = companion.handle_player_input("What now?")

        self.assertEqual(response.source, "strategy-next-step")
        self.assertIn("AUTO is executing this plan now", response.text)
        self.assertNotIn("action", response.metadata)
        self.assertEqual(router.calls, 0)

    def test_hybrid_force_plan_corrects_a_grenadier_monoculture(self) -> None:
        current = snapshot(
            map_info={"map_name": "Singles", "width": 112, "height": 54},
            units=[
                *({"actor_id": actor_id, "type": "e2", "is_idle": True, "can_attack": True}
                  for actor_id in range(1, 13)),
                *({"actor_id": actor_id, "type": "3tnk", "is_idle": True, "can_attack": True}
                  for actor_id in range(20, 26)),
            ],
            production=[],
            available_production=["e1", "e2", "e3", "3tnk", "v2rl"],
        )

        plan = hybrid_force_plan(current)
        selected = plan["next_production_types"]

        self.assertEqual(selected[0], "v2rl")
        self.assertEqual(set(selected[1:]), {"e1", "e3"})
        self.assertNotIn("e2", selected)
        self.assertTrue(plan["squad"]["attack_ready"])

    def test_hybrid_force_plan_rotates_around_a_busy_vehicle_queue(self) -> None:
        current = snapshot(
            units=[{"actor_id": 1, "type": "e1", "is_idle": True, "can_attack": True}],
            production=[{"queue_type": "Vehicle", "item": "3tnk", "progress": 0.4}],
            available_production=["e1", "e2", "e3", "3tnk", "v2rl"],
        )

        plan = hybrid_force_plan(current)

        self.assertTrue(plan["next_production"])
        self.assertTrue(all(command["item_type"] in {"e1", "e2", "e3"} for command in plan["next_production"]))
        self.assertEqual(len({command["item_type"] for command in plan["next_production"]}), 2)

    def test_hybrid_force_plan_resumes_reconnaissance_when_enemy_location_is_unknown(self) -> None:
        current = spatial_snapshot(
            width=40,
            height=40,
            explored_percent=35,
            units=[
                {"actor_id": actor_id, "type": "e1", "cell_x": 20, "cell_y": 20, "is_idle": True, "can_attack": True}
                for actor_id in range(1, 4)
            ],
            buildings=[{"actor_id": 20, "type": "fact", "cell_x": 20, "cell_y": 20}],
            production=[],
        )

        plan = hybrid_force_plan(current)
        commands = plan["recon"]["commands"]

        self.assertEqual(len(commands), 3)
        self.assertEqual(len({(command["target_x"], command["target_y"]) for command in commands}), 3)
        self.assertTrue(all(command["action"] == "attack_move" for command in commands))

    def test_hybrid_force_plan_keeps_siege_behind_a_mixed_assault(self) -> None:
        current = snapshot(
            map_info={"map_name": "Assault", "width": 64, "height": 64},
            explored_percent=60,
            units=[
                *({"actor_id": actor_id, "type": "e1", "cell_x": 10, "cell_y": 10, "is_idle": True, "can_attack": True}
                  for actor_id in range(1, 7)),
                *({"actor_id": actor_id, "type": "3tnk", "cell_x": 11, "cell_y": 10, "is_idle": True, "can_attack": True}
                  for actor_id in range(10, 15)),
                {"actor_id": 30, "type": "v2rl", "cell_x": 9, "cell_y": 10, "is_idle": True, "can_attack": True},
            ],
            buildings=[{"actor_id": 40, "type": "fact", "cell_x": 10, "cell_y": 10}],
            visible_enemy_buildings=[{"actor_id": 90, "type": "weap", "cell_x": 50, "cell_y": 50}],
            production=[],
        )

        plan = hybrid_force_plan(current)
        commands = plan["assault"]["commands"]
        siege_command = next(command for command in commands if command["actor_id"] == 30)

        self.assertTrue(plan["squad"]["attack_ready"])
        self.assertLessEqual(len(commands), 12)
        self.assertEqual(siege_command["action"], "attack")
        self.assertEqual(siege_command["target_actor_id"], 90)
        self.assertNotEqual((siege_command.get("target_x", 0), siege_command.get("target_y", 0)), (50, 50))
        self.assertTrue(any((command.get("target_x", 0), command.get("target_y", 0)) == (50, 50) for command in commands))

    def test_hybrid_force_plan_concentrates_the_army_while_retaining_reserve(self) -> None:
        current = snapshot(
            map_info={"map_name": "Concentration", "width": 112, "height": 54},
            units=[
                *({"actor_id": actor_id, "type": "e1", "is_idle": True, "can_attack": True}
                  for actor_id in range(1, 25)),
                *({"actor_id": actor_id, "type": "1tnk", "is_idle": True, "can_attack": True}
                  for actor_id in range(30, 40)),
            ],
            visible_enemy_buildings=[{"actor_id": 90, "type": "fact", "cell_x": 90, "cell_y": 20}],
        )

        plan = hybrid_force_plan(current)

        self.assertEqual(len(plan["assault"]["commands"]), 24)
        self.assertGreaterEqual(
            plan["squad"]["idle_eligible_units"] - len(plan["assault"]["commands"]),
            plan["squad"]["defense_reserve"],
        )

    def test_hybrid_force_plan_requires_a_rearm_building_per_aircraft(self) -> None:
        current = snapshot(
            units=[{"actor_id": 1, "type": "yak", "is_idle": True, "can_attack": True}],
            buildings=[{"actor_id": 10, "type": "afld"}],
            production=[],
            available_production=["e1", "e3", "yak", "mig"],
        )

        plan = hybrid_force_plan(current)
        selected = plan["next_production_types"]

        self.assertNotIn("yak", selected)
        self.assertNotIn("mig", selected)
        self.assertEqual(set(selected), {"e1", "e3"})

    def test_hybrid_force_plan_includes_red_sea_faction_specialists(self) -> None:
        current = snapshot(
            units=[{"actor_id": 1, "type": "e1", "is_idle": True, "can_attack": True}],
            buildings=[{"actor_id": 10, "type": "dome"}, {"actor_id": 11, "type": "afld"}],
            production=[],
            available_production=["e1", "e3", "sads", "tech", "ymlr", "samad"],
        )

        plan = hybrid_force_plan(current, batch_size=5)

        self.assertIn("ymlr", plan["adjusted_available_weights"])
        self.assertIn("tech", plan["adjusted_available_weights"])
        self.assertTrue({"sads", "tech", "ymlr"} & set(plan["next_production_types"]))

    def test_scout_targets_fan_out_in_distinct_directions(self) -> None:
        current = spatial_snapshot(width=20, height=20)

        targets = scout_targets(current, (10, 10), opening_scout_count(current))

        self.assertEqual(len(targets), 2)
        self.assertEqual(len(set(targets)), 2)
        self.assertTrue(any(target[0] < 10 for target in targets))
        self.assertTrue(any(target[0] > 10 for target in targets))

    def test_auto_opening_trains_map_scaled_rifle_scouts(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.latest_snapshot = spatial_snapshot(
            width=112,
            height=54,
            tick=1200,
            explored_percent=8,
            harvester_count=1,
            buildings=[
                {"actor_id": 10, "type": "fact", "cell_x": 20, "cell_y": 20},
                {"actor_id": 11, "type": "barr", "cell_x": 23, "cell_y": 20, "rally_x": 25, "rally_y": 26},
            ],
            available_production=["e1", "proc"],
            production=[],
        )

        proposal = companion.propose_routine_action()

        commands = proposal.metadata["action"]["commands"]
        self.assertEqual(len(commands), 3)
        self.assertTrue(all(command["action"] == "train" and command["item_type"] == "e1" for command in commands))

    def test_auto_opening_sends_rifle_scouts_to_distinct_targets(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.latest_snapshot = spatial_snapshot(
            width=20,
            height=20,
            tick=1200,
            explored_percent=8,
            harvester_count=1,
            buildings=[
                {"actor_id": 10, "type": "fact", "cell_x": 10, "cell_y": 10},
                {"actor_id": 11, "type": "barr", "cell_x": 12, "cell_y": 10, "rally_x": 12, "rally_y": 16},
            ],
            units=[
                {"actor_id": 21, "type": "e1", "cell_x": 12, "cell_y": 13, "is_idle": True, "can_attack": True},
                {"actor_id": 22, "type": "e1", "cell_x": 13, "cell_y": 13, "is_idle": True, "can_attack": True},
            ],
            available_production=["e1", "proc"],
            production=[],
        )

        proposal = companion.propose_routine_action()

        commands = proposal.metadata["action"]["commands"]
        self.assertEqual(len(commands), 2)
        self.assertTrue(all(command["action"] == "attack_move" for command in commands))
        self.assertEqual(len({(command["target_x"], command["target_y"]) for command in commands}), 2)

    def test_auto_sets_production_rally_into_open_space(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.latest_snapshot = spatial_snapshot(
            width=20,
            height=20,
            tick=900,
            explored_percent=20,
            harvester_count=1,
            buildings=[
                {"actor_id": 10, "type": "fact", "cell_x": 8, "cell_y": 8},
                {"actor_id": 11, "type": "weap", "cell_x": 9, "cell_y": 10, "rally_x": -1, "rally_y": -1},
            ],
            production=[],
        )

        proposal = companion.propose_routine_action()

        command = proposal.metadata["action"]["commands"][0]
        self.assertEqual(command["action"], "set_rally_point")
        self.assertEqual(command["actor_id"], 11)
        self.assertGreater(command["target_y"], 12)

    def test_console_print_survives_non_cp1252_voice_text(self) -> None:
        failure = UnicodeEncodeError("charmap", "đ", 0, 1, "character maps to undefined")
        with mock.patch("builtins.print", side_effect=[failure, None]) as output:
            console_print("što mi sugerišete đ")
        self.assertEqual(output.call_count, 2)
        self.assertIn("\\u0111", output.call_args_list[1].args[0])

    def test_tactical_feed_states_track_action_lifecycle(self):
        response = mock.Mock(metadata={"action": {"state": "pending"}})
        self.assertEqual(response_hud_state(response, "speaking"), "action-pending")
        response.metadata = {"action": {"state": "executed"}}
        self.assertEqual(response_hud_state(response, "speaking"), "action-executed")
        response.metadata = {"action": {"state": "rejected"}}
        self.assertEqual(response_hud_state(response, "speaking"), "action-rejected")
        response.metadata = {}
        self.assertEqual(response_hud_state(response, "speaking"), "speaking")

    @staticmethod
    def action_snapshot(tick: int = 100) -> GameSnapshot:
        return GameSnapshot.from_dict({
            "tick": tick,
            "map_info": {"map_name": "Action Test", "width": 64, "height": 64},
            "units": [
                {"actor_id": 1, "type": "1tnk", "cell_x": 20, "cell_y": 20, "can_attack": True},
                {"actor_id": 2, "type": "e1", "cell_x": 21, "cell_y": 20, "can_attack": True},
            ],
            "buildings": [
                {"actor_id": 10, "type": "weap", "cell_x": 10, "cell_y": 10, "hp_percent": 0.5},
            ],
            "available_production": ["1tnk", "e1"],
        })

    def test_action_proposal_requires_confirmation_and_executes_once(self) -> None:
        router = ScriptedRouter({
            "mode": "action",
            "summary": "Train two tanks",
            "commands": [
                {"action": "train", "item_type": "1tnk"},
                {"action": "train", "item_type": "1tnk"},
            ],
        })
        executions = []

        def execute(request_id, expected_tick, commands):  # noqa: ANN001
            executions.append((request_id, expected_tick, commands))
            return ActionReceipt(request_id, True, 104, "Queued 2 confirmed player orders.")

        companion = Companion(router=router, action_executor=execute)
        companion.latest_snapshot = self.action_snapshot()
        proposal = companion.handle_player_input("Train two tanks")
        self.assertEqual(proposal.source, "action-proposal")
        self.assertEqual(proposal.metadata["action"]["state"], "pending")
        self.assertEqual(executions, [])

        receipt = companion.handle_player_input("confirm")
        self.assertEqual(receipt.source, "action-receipt")
        self.assertEqual(receipt.metadata["action"]["state"], "executed")
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0][1], 100)
        self.assertEqual(len(executions[0][2]), 2)

        duplicate = companion.handle_player_input("confirm")
        self.assertEqual(duplicate.metadata["action"]["state"], "missing")
        self.assertEqual(len(executions), 1)

    def test_natural_confirmation_executes_visible_proposal(self) -> None:
        executions = []
        companion = Companion(
            router=ScriptedRouter({
                "mode": "action",
                "summary": "Repair the war factory",
                "commands": [{"action": "repair", "actor_id": 10}],
            }),
            action_executor=lambda request_id, _tick, _commands: (
                executions.append(request_id) or ActionReceipt(request_id, True, 110, "Repair order queued.")
            ),
        )
        companion.latest_snapshot = self.action_snapshot()
        companion.handle_player_input("Repair my war factory")

        response = companion.handle_player_input("Okay, confirm it please.")

        self.assertEqual(response.metadata["action"]["state"], "executed")
        self.assertEqual(len(executions), 1)

    def test_natural_cancellation_does_not_execute_proposal(self) -> None:
        executions = []
        companion = Companion(
            router=ScriptedRouter({
                "mode": "action",
                "summary": "Repair the war factory",
                "commands": [{"action": "repair", "actor_id": 10}],
            }),
            action_executor=lambda *args: executions.append(args),
        )
        companion.latest_snapshot = self.action_snapshot()
        companion.handle_player_input("Repair my war factory")

        response = companion.handle_player_input("No, don't confirm that.")

        self.assertEqual(response.metadata["action"]["state"], "cancelled")
        self.assertEqual(executions, [])

    def test_auto_mode_plans_and_executes_without_manual_confirmation(self) -> None:
        executions = []
        companion = Companion(
            router=ScriptedRouter({
                "mode": "action",
                "summary": "Move the armored force forward",
                "commands": [{"action": "attack_move", "actor_id": 1, "target_x": 30, "target_y": 30}],
            }),
            action_executor=lambda request_id, _tick, commands: (
                executions.append(commands) or ActionReceipt(request_id, True, 110, "Queued autonomous order.")
            ),
        )
        companion.latest_snapshot = self.action_snapshot()
        companion.configure(auto_act=True)

        response = companion.auto_act_once()

        self.assertEqual(response.metadata["action"]["state"], "executed")
        self.assertTrue(response.metadata["auto_act"])
        self.assertEqual(len(executions), 1)
        self.assertIsNone(companion.pending_action())

    def test_auto_mode_executes_free_routine_before_calling_model(self) -> None:
        router = FakeRouter()
        executions = []
        companion = Companion(
            router=router,
            action_executor=lambda request_id, _tick, commands: (
                executions.append(commands) or ActionReceipt(request_id, True, 30, "MCV deployed.")
            ),
        )
        companion.latest_snapshot = GameSnapshot.from_dict({
            "tick": 20,
            "map_info": {"width": 64, "height": 64},
            "units": [{"actor_id": 1, "type": "mcv", "cell_x": 20, "cell_y": 20}],
        })
        companion.update_snapshot(companion.latest_snapshot)
        companion.configure(auto_act=True)

        proposal = companion.propose_routine_action()
        response = companion.auto_act_once()

        self.assertEqual(proposal.metadata["action"]["commands"][0]["action"], "deploy")
        self.assertEqual(response.metadata["action"]["state"], "executed")
        self.assertEqual(router.calls, 0)
        self.assertEqual(len(executions), 1)

    def test_event_context_wakes_auto_planner_with_fresh_details(self) -> None:
        instructions = []
        executions = []
        companion = Companion(
            router=FakeRouter(),
            action_executor=lambda request_id, _tick, commands: (
                executions.append(commands) or ActionReceipt(request_id, True, 110, "Orders queued.")
            ),
        )
        companion.latest_snapshot = self.action_snapshot()
        companion.set_action_planner(lambda instruction: (
            instructions.append(instruction)
            or {
                "message": "Move the armored force forward.",
                "summary": "Move the armored force forward",
                "commands": [{"action": "attack_move", "actor_id": 1, "target_x": 30, "target_y": 30}],
            }
        ))
        companion.configure(auto_act=True)

        response = companion.auto_act_once({"type": "enemy_spotted", "tick": 100, "battlefield": {"cash": 2000}})

        self.assertEqual(response.metadata["action"]["state"], "executed")
        self.assertIn("priority game event", instructions[0])
        self.assertIn('"type":"enemy_spotted"', instructions[0])
        self.assertEqual(len(executions), 1)

    def test_event_cycle_restarts_periodic_deadlines(self) -> None:
        routine_due, planner_due = _restart_auto_deadlines(10.0, "calm")
        self.assertEqual(routine_due, 13.0)
        self.assertEqual(planner_due, 70.0)

        _, heated_planner_due = _restart_auto_deadlines(10.0, "critical")
        self.assertEqual(heated_planner_due, 14.0)

    def test_mission_auto_uses_companion_loop_even_when_native_brain_exists(self) -> None:
        self.assertTrue(_companion_action_loop_enabled(
            mission_mode=True,
            native_brain_available=True,
        ))
        self.assertFalse(_companion_action_loop_enabled(
            mission_mode=False,
            native_brain_available=True,
        ))

    def test_auto_routine_does_not_stack_the_building_queue(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.latest_snapshot = GameSnapshot.from_dict({
            "tick": 800,
            "map_info": {"width": 64, "height": 64},
            "buildings": [{"actor_id": 10, "type": "fact"}],
            "available_production": ["proc", "tent"],
            "production": [{
                "queue_type": "Building",
                "item": "proc",
                "progress": 0.5,
                "remaining_ticks": 200,
            }],
        })

        self.assertIsNone(companion.propose_routine_action())
        self.assertIsNone(companion.pending_action())

    def test_interactive_mcp_plan_creates_confirmable_proposal(self) -> None:
        router = FakeRouter()
        companion = Companion(router=router)
        companion.latest_snapshot = self.action_snapshot()
        companion.set_action_planner(lambda _instruction: {
            "message": "Add one tank to the main force.",
            "summary": "Train one tank",
            "commands": [{"action": "train", "item_type": "1tnk", "queued": True}],
            "model": "fake-mcp-agent",
            "latency_ms": 12,
            "mcp": {"connected": True, "tools": 22, "proposal_only": True},
        })

        response = companion.handle_player_input("What action do you suggest?")

        self.assertEqual(response.source, "action-proposal")
        self.assertEqual(response.metadata["action"]["state"], "pending")
        self.assertEqual(response.metadata["mcp"]["tools"], 22)
        self.assertTrue(response.metadata["mcp"]["proposal_only"])
        self.assertEqual(router.calls, 0)

    def test_mcp_proposal_mode_never_dispatches_commands(self) -> None:
        class FakeBridge:
            session_id = ""

            def __init__(self) -> None:
                self.fast_advance_calls = 0

            def observe(self):
                return GameSnapshot.from_dict({
                    "tick": 100,
                    "map_info": {"width": 64, "height": 64},
                    "available_production": ["1tnk"],
                })

            def fast_advance(self, *args, **kwargs):  # noqa: ANN002, ANN003
                self.fast_advance_calls += 1
                raise AssertionError("proposal mode must not execute")

        runtime = GameRuntime("127.0.0.1:1", "")
        runtime.bridge = FakeBridge()
        command = ActionCommand(action="train", item_type="1tnk", queued=True)
        previous_runtime = game_mcp.runtime
        previous_mode = game_mcp.proposal_mode
        try:
            game_mcp.runtime = runtime
            game_mcp.proposal_mode = True
            proposed = game_mcp._submit((command,))
        finally:
            game_mcp.runtime = previous_runtime
            game_mcp.proposal_mode = previous_mode

        self.assertTrue(proposed["proposal_mode"])
        self.assertTrue(proposed["requires_confirmation"])
        self.assertEqual(proposed["proposed"][0]["action"], "train")
        self.assertEqual(runtime.bridge.fast_advance_calls, 0)

    def test_mcp_production_commands_wait_for_engine_queue_visibility(self) -> None:
        class FakeRuntime:
            def __init__(self) -> None:
                self.ticks = 0

            def issue(self, commands, *, ticks=1):  # noqa: ANN001
                self.ticks = ticks
                return {"action": commands[0].action}

        runtime = FakeRuntime()
        previous_runtime = game_mcp.runtime
        previous_mode = game_mcp.proposal_mode
        try:
            game_mcp.runtime = runtime
            game_mcp.proposal_mode = False
            game_mcp._submit((ActionCommand(action="train", item_type="e1", queued=True),))
            self.assertEqual(runtime.ticks, 8)
            game_mcp._submit((ActionCommand(action="move", actor_id=1, target_x=2, target_y=3),))
            self.assertEqual(runtime.ticks, 1)
        finally:
            game_mcp.runtime = previous_runtime
            game_mcp.proposal_mode = previous_mode

    def test_construction_yard_cannot_be_packed_by_deploy_tool(self) -> None:
        state = GameSnapshot(
            tick=100,
            buildings=(Unit(actor_id=7, kind="fact", is_building=True),),
        )

        with self.assertRaisesRegex(ValueError, "not an owned deployable unit"):
            GameRuntime._validate(state, (ActionCommand(action="deploy", actor_id=7),))

    def test_building_cannot_be_placed_before_production_completes(self) -> None:
        state = GameSnapshot(
            tick=100,
            production=({"queue_type": "Building", "item": "proc", "progress": 0.5},),
        )

        with self.assertRaisesRegex(ValueError, "has not completed production"):
            GameRuntime._validate(state, (ActionCommand(action="place_building", item_type="proc"),))

        complete = GameSnapshot(
            tick=200,
            production=({"queue_type": "Building", "item": "proc", "progress": 1.0},),
        )
        GameRuntime._validate(complete, (ActionCommand(action="place_building", item_type="proc"),))

    def test_auto_action_guardrails_reject_decoys_and_powering_down_base(self) -> None:
        state = GameSnapshot(
            tick=100,
            buildings=(Unit(actor_id=7, kind="fact", is_building=True),),
            available_production=("facf",),
        )

        with self.assertRaisesRegex(ValueError, "decoy building"):
            GameRuntime._validate(state, (ActionCommand(action="build", item_type="facf"),))
        with self.assertRaisesRegex(ValueError, "essential building"):
            GameRuntime._validate(state, (ActionCommand(action="power_down", actor_id=7),))
        with self.assertRaisesRegex(ValueError, "Construction Yard cannot be sold"):
            GameRuntime._validate(state, (ActionCommand(action="sell", actor_id=7),))

    def test_harvester_training_stops_at_map_scaled_target(self) -> None:
        state = GameSnapshot(
            tick=2000,
            map_width=112,
            map_height=54,
            harvester_count=3,
            available_production=("harv",),
        )
        command = ActionCommand(action="train", item_type="harv")

        with self.assertRaisesRegex(ValueError, "harvester target of 3"):
            GameRuntime._validate(state, (command,))
        with self.assertRaisesRegex(ValueError, "harvester target of 3"):
            Companion._validate_action_commands(state, [command.as_dict()])

    def test_silo_building_stops_at_map_scaled_limit(self) -> None:
        state = GameSnapshot(
            tick=2000,
            map_width=112,
            map_height=54,
            buildings=tuple(Unit(actor_id=actor_id, kind="silo", is_building=True) for actor_id in range(1, 4)),
            available_production=("silo",),
        )
        command = ActionCommand(action="build", item_type="silo")

        with self.assertRaisesRegex(ValueError, "silo limit of 3"):
            GameRuntime._validate(state, (command,))
        with self.assertRaisesRegex(ValueError, "silo limit of 3"):
            Companion._validate_action_commands(state, [command.as_dict()])

    def test_silo_building_is_rejected_without_storage_pressure(self) -> None:
        state = GameSnapshot(
            tick=2000,
            map_width=112,
            map_height=54,
            ore=1200,
            resource_capacity=5000,
            available_production=("silo",),
        )
        command = ActionCommand(action="build", item_type="silo")

        with self.assertRaisesRegex(ValueError, "only needed above 80% storage"):
            GameRuntime._validate(state, (command,))
        with self.assertRaisesRegex(ValueError, "only needed above 80% storage"):
            Companion._validate_action_commands(state, [command.as_dict()])

    def test_same_building_cannot_be_requeued_while_in_production(self) -> None:
        state = GameSnapshot(
            tick=100,
            available_production=("proc",),
            production=({"queue_type": "Building", "item": "proc", "progress": 0.5},),
        )

        with self.assertRaisesRegex(ValueError, "already queued"):
            GameRuntime._validate(state, (ActionCommand(action="build", item_type="proc"),))

    def test_invented_actor_is_rejected_before_confirmation(self) -> None:
        companion = Companion(router=ScriptedRouter({
            "mode": "action",
            "summary": "Move a tank",
            "commands": [{"action": "move", "actor_id": 999, "target_x": 30, "target_y": 30}],
        }))
        companion.latest_snapshot = self.action_snapshot()
        response = companion.handle_player_input("Move the tank north")
        self.assertEqual(response.source, "action-rejected")
        self.assertIn("not owned", response.metadata["action"]["reason"])
        self.assertIsNone(companion.pending_action())

    def test_action_with_disappeared_actor_is_not_sent_to_engine(self) -> None:
        executions = []
        companion = Companion(
            router=ScriptedRouter({
                "mode": "action",
                "summary": "Move the tank",
                "commands": [{"action": "move", "actor_id": 1, "target_x": 30, "target_y": 30}],
            }),
            action_executor=lambda *args: executions.append(args),
        )
        companion.latest_snapshot = self.action_snapshot(100)
        companion.handle_player_input("Move the tank")
        companion.latest_snapshot = GameSnapshot.from_dict({
            "tick": 5000,
            "map_info": {"map_name": "Action Test", "width": 64, "height": 64},
            "units": [{"actor_id": 2, "type": "e1", "cell_x": 21, "cell_y": 20, "can_attack": True}],
            "buildings": [{"actor_id": 10, "type": "weap", "cell_x": 10, "cell_y": 10}],
            "available_production": ["1tnk", "e1"],
        })
        response = companion.confirm_action()
        self.assertEqual(response.metadata["action"]["state"], "rejected")
        self.assertEqual(executions, [])

    def test_confirmation_refreshes_live_snapshot_before_engine_dispatch(self) -> None:
        dispatched_ticks = []
        companion = Companion(
            router=ScriptedRouter({
                "mode": "action",
                "summary": "Move the tank",
                "commands": [{"action": "move", "actor_id": 1, "target_x": 30, "target_y": 30}],
            }),
            action_executor=lambda request_id, tick, _commands: (
                dispatched_ticks.append(tick) or ActionReceipt(request_id, True, tick, "Fresh order queued.")
            ),
        )
        companion.latest_snapshot = self.action_snapshot(100)
        companion.handle_player_input("Move the tank")
        companion.set_snapshot_provider(lambda: self.action_snapshot(5000))

        response = companion.confirm_action()

        self.assertEqual(response.metadata["action"]["state"], "executed")
        self.assertEqual(dispatched_ticks, [5000])

    def test_structured_question_does_not_create_action(self) -> None:
        companion = Companion(router=ScriptedRouter({
            "mode": "answer",
            "answer": "Your eastern approach has the strongest visible defense.",
        }))
        companion.latest_snapshot = self.action_snapshot()
        response = companion.handle_player_input("Where am I strongest?")
        self.assertEqual(response.source, "ai-layer")
        self.assertIsNone(companion.pending_action())

    def test_interrupted_planning_cannot_leave_a_hidden_proposal(self) -> None:
        companion = Companion(router=ScriptedRouter({
            "mode": "action",
            "summary": "Move the tank",
            "commands": [{"action": "move", "actor_id": 1, "target_x": 30, "target_y": 30}],
        }, delay=0.05))
        companion.latest_snapshot = self.action_snapshot()
        responses = []
        worker = threading.Thread(target=lambda: responses.append(companion.handle_player_input("Move the tank")))
        worker.start()
        time.sleep(0.01)
        companion.interrupt()
        worker.join()
        self.assertTrue(responses[0].interrupted)
        self.assertEqual(responses[0].text, "")
        self.assertIsNone(companion.pending_action())

    def test_action_http_endpoints_preserve_confirmation_boundary(self) -> None:
        executions = []

        def execute(request_id, expected_tick, commands):  # noqa: ANN001
            executions.append((request_id, expected_tick, commands))
            return ActionReceipt(request_id, True, 105, "Queued 1 confirmed player order.")

        companion = Companion(
            router=ScriptedRouter({
                "mode": "action",
                "summary": "Repair the war factory",
                "commands": [{"action": "repair", "actor_id": 10}],
            }),
            action_executor=execute,
        )
        companion.latest_snapshot = self.action_snapshot()
        server = create_server("127.0.0.1", 0, companion, FakePlayer())
        statuses = []
        server.status_publisher = lambda state, message: statuses.append((state, message))
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            request = urllib.request.Request(
                base + "/v1/actions/propose",
                data=b'{"instruction":"Repair my war factory"}',
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                proposal = json.loads(response.read())
            self.assertEqual(proposal["metadata"]["action"]["state"], "pending")
            self.assertEqual(executions, [])
            self.assertEqual(statuses[-1][0], "action-pending")

            proposal_id = proposal["metadata"]["action"]["proposal_id"]
            request = urllib.request.Request(
                base + "/v1/actions/confirm",
                data=json.dumps({"proposal_id": proposal_id}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                receipt = json.loads(response.read())
            self.assertEqual(receipt["metadata"]["action"]["state"], "executed")
            self.assertEqual(len(executions), 1)
            self.assertEqual(statuses[-1][0], "action-executed")
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_native_remappable_voice_hotkey_endpoints_forward_press_and_release(self) -> None:
        server = create_server("127.0.0.1", 0, Companion(router=FakeRouter()), FakePlayer())
        controller = mock.Mock()
        controller.start_question.return_value = True
        controller.stop_question.return_value = True
        server.voice_controller = controller
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            for operation in ("start", "stop"):
                request = urllib.request.Request(
                    f"{base}/v1/voice/{operation}",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.assertTrue(json.loads(response.read())["ok"])
            controller.start_question.assert_called_once_with()
            controller.stop_question.assert_called_once_with()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_model_called_only_for_salient_event(self) -> None:
        router = FakeRouter()
        companion = Companion(router=router)
        self.assertIsNone(companion.observe(snapshot()))
        self.assertEqual(router.calls, 0)
        response = companion.observe(snapshot(tick=1010, visible_enemies=[{"actor_id": 9, "type": "3tnk", "cell_x": 51, "cell_y": 12}]))
        self.assertIsNotNone(response)
        self.assertEqual(response.insight.key, "enemy_spotted")
        self.assertEqual(router.calls, 1)

    def test_repeated_event_is_deduplicated(self) -> None:
        router = FakeRouter()
        companion = Companion(router=router)
        enemy = [{"actor_id": 9, "type": "3tnk"}]
        self.assertIsNotNone(companion.observe(snapshot(visible_enemies=enemy)))
        self.assertIsNone(companion.observe(snapshot(tick=1020, visible_enemies=enemy)))

    def test_persistent_harvester_outage_is_local_and_fires_once(self) -> None:
        router = FakeRouter()
        companion = Companion(router=router)

        warning = companion.observe(snapshot(
            tick=1000,
            harvester_count=0,
            buildings=[{"actor_id": 14, "type": "proc"}],
        ))
        self.assertEqual(warning.insight.key, "no_harvester")
        self.assertEqual(warning.insight.importance, "important")
        self.assertEqual(warning.source, "deterministic-local")
        self.assertEqual(warning.metadata["model"], "none")
        self.assertEqual(router.calls, 0)

        self.assertIsNone(companion.observe(snapshot(
            tick=5000,
            harvester_count=0,
            buildings=[{"actor_id": 14, "type": "proc"}],
        )))
        self.assertEqual(router.calls, 0)

        companion.observe(snapshot(tick=5010, harvester_count=1))
        recurring = companion.observe(snapshot(tick=7000, harvester_count=0))
        self.assertEqual(recurring.insight.key, "no_harvester")
        self.assertEqual(router.calls, 0)

    def test_harvester_outage_waits_for_an_established_economy(self) -> None:
        router = FakeRouter()
        companion = Companion(router=router)

        self.assertIsNone(companion.observe(snapshot(tick=400, harvester_count=0)))
        self.assertIsNone(companion.observe(snapshot(tick=401, harvester_count=0)))
        warning = companion.observe(snapshot(
            tick=402,
            harvester_count=0,
            buildings=[{"actor_id": 14, "type": "proc"}],
        ))
        self.assertEqual(warning.insight.key, "no_harvester")
        self.assertEqual(warning.source, "deterministic-local")
        self.assertEqual(router.calls, 0)

    def test_persistent_power_deficit_fires_only_on_transition(self) -> None:
        router = FakeRouter()
        companion = Companion(router=router)

        warning = companion.observe(snapshot(tick=1000, power_provided=20, power_drained=100))
        self.assertEqual(warning.insight.key, "low_power")
        self.assertEqual(warning.source, "deterministic-local")
        self.assertIsNone(companion.observe(snapshot(tick=5000, power_provided=20, power_drained=100)))
        self.assertEqual(router.calls, 0)

    def test_changed_situation_gets_a_periodic_update(self) -> None:
        companion = Companion(router=FakeRouter(), insights=InsightEngine(situation_interval_ticks=250))
        self.assertIsNone(companion.observe(snapshot(tick=1000)))
        response = companion.observe(snapshot(
            tick=1250,
            production=[{"item": "1tnk", "progress": 0.9, "remaining_ticks": 80}],
        ))
        self.assertIsNotNone(response)
        self.assertEqual(response.insight.key, "situation_update")
        self.assertEqual(response.insight.importance, "routine")
        self.assertIn("active production: Light Tank", response.insight.fact)

    def test_voice_is_reserved_for_selected_importance(self) -> None:
        companion = Companion(router=FakeRouter())
        routine = companion.observe(snapshot(tick=1000))
        self.assertIsNone(routine)
        critical = companion.observe(snapshot(tick=1010, power_provided=20, power_drained=100))
        self.assertEqual(critical.insight.importance, "critical")
        self.assertTrue(companion.should_speak(critical.insight))
        companion.router.configure({"voice_priority": "off"}, persist=False)
        self.assertFalse(companion.should_speak(critical.insight))

    def test_visible_enemy_change_clears_stale_banner(self) -> None:
        companion = Companion(router=FakeRouter())
        response = companion.observe(snapshot(visible_enemies=[{"actor_id": 9, "type": "harv"}]))
        self.assertEqual(response.insight.key, "enemy_spotted")
        cleared = companion.observe(snapshot(tick=1010, visible_enemies=[]))
        self.assertIsNotNone(cleared)
        self.assertTrue(cleared.metadata["clear"])
        self.assertEqual(cleared.text, "")

    def test_snapshot_distinguishes_visible_and_remembered_enemy_buildings(self) -> None:
        current = snapshot(
            explored_percent=62.5,
            power_provided=600,
            power_drained=510,
            visible_enemy_buildings=[{"actor_id": 20, "type": "tsla"}],
            remembered_enemy_buildings=[{"actor_id": 21, "type": "weap", "cell_x": 50, "cell_y": 40}],
        ).compact()
        self.assertEqual(current["explored_percent"], 62.5)
        self.assertEqual(current["economy"]["power_balance"], 90)
        self.assertEqual(current["visible_enemy_buildings"], ["Tesla Coil"])
        self.assertEqual(current["remembered_enemy_buildings"][0]["type"], "War Factory")

    def test_player_messages_never_leak_openra_type_codes(self) -> None:
        situation = InsightEngine._situation_fact(snapshot(production=[
            {"item": "proc", "progress": 0.2},
            {"item": "proc", "progress": 0.1},
        ]))
        self.assertIn("Ore Refinery ×2", situation)
        self.assertNotIn("active production: proc", situation.lower())

        companion = Companion(router=FakeRouter())
        damaged = companion.observe(snapshot(
            tick=1000,
            units=[{"actor_id": 1, "type": "e1", "hp_percent": 0.1}],
            production=[],
        ))
        self.assertIn("Rifle Infantry", damaged.text)
        self.assertNotIn("e1", damaged.text.lower())

    def test_voice_question_shows_transcript_before_answer(self) -> None:
        statuses = []
        companion = Companion(router=FakeRouter())
        companion.latest_snapshot = snapshot()
        hotkeys = VoiceHotkeys(
            companion,
            FakePlayer(),
            lambda _text: None,
            lambda state, message: statuses.append((state, message)),
        )
        with (
            mock.patch("openra_ai_companion.hotkeys.record_while", return_value=b"audio"),
            mock.patch.object(hotkeys._stop, "wait", return_value=False),
        ):
            hotkeys._voice_question()
        transcript_index = next(i for i, status in enumerate(statuses) if status[0] == "transcript")
        speaking_index = next(i for i, status in enumerate(statuses) if status[0] == "speaking")
        self.assertLess(transcript_index, speaking_index)
        self.assertIn("Where is the threat?", statuses[transcript_index][1])

    def test_player_turn_defers_events_without_losing_their_context(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.begin_user_turn()
        try:
            response = companion.observe(snapshot(
                tick=1000,
                harvester_count=0,
                buildings=[{"actor_id": 14, "type": "proc"}],
            ))
            self.assertIsNone(response)
            self.assertIsNone(companion.take_event_context())
        finally:
            companion.end_user_turn(grace_seconds=0)

        event = companion.take_event_context()
        self.assertIsNotNone(event)
        self.assertEqual(event["type"], "no_harvester")

    def test_event_observation_cannot_interrupt_player_generation(self) -> None:
        router = FakeRouter(delay=0.04)
        companion = Companion(router=router)
        companion.latest_snapshot = snapshot()
        companion.begin_user_turn()
        responses = []
        worker = threading.Thread(target=lambda: responses.append(companion.handle_player_input("Where is the threat?")))
        worker.start()
        time.sleep(0.01)
        self.assertIsNone(companion.observe(snapshot(
            tick=1000,
            harvester_count=0,
            buildings=[{"actor_id": 14, "type": "proc"}],
        )))
        worker.join(timeout=1)
        companion.end_user_turn(grace_seconds=0)

        self.assertEqual(len(responses), 1)
        self.assertFalse(responses[0].interrupted)
        self.assertTrue(responses[0].text)

    def test_voice_priority_remains_active_for_reported_playback_duration(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.latest_snapshot = snapshot()
        priority_during_speech = []
        waits = []
        hotkeys = VoiceHotkeys(
            companion,
            FakePlayer(),
            lambda _text: priority_during_speech.append(companion.user_turn_active) or 9.5,
            lambda _state, _message: None,
        )
        with (
            mock.patch("openra_ai_companion.hotkeys.record_while", return_value=b"audio"),
            mock.patch.object(hotkeys._stop, "wait", side_effect=lambda seconds: waits.append(seconds) or False),
        ):
            hotkeys._voice_question()

        self.assertEqual(priority_during_speech, [True])
        self.assertIn(9.85, waits)

    def test_hud_message_hold_never_ends_before_speech(self) -> None:
        self.assertEqual(playback_hold_seconds(12.0, 8.0), 12.35)
        self.assertEqual(playback_hold_seconds(3.0, 8.0), 8.0)
        self.assertEqual(playback_hold_seconds(True, 8.0), 8.0)

    def test_calm_automatic_messages_are_capped_at_one_per_minute(self) -> None:
        companion = Companion(router=FakeRouter())
        warning = companion.observe(snapshot(
            tick=1000,
            harvester_count=0,
            buildings=[{"actor_id": 14, "type": "proc"}],
        ))
        self.assertEqual(warning.insight.key, "no_harvester")
        recovered = companion.observe(snapshot(
            tick=1010,
            harvester_count=1,
            units=[{"actor_id": 12, "type": "harv"}],
            production=[],
        ))
        self.assertIsNone(recovered)
        self.assertIsNone(companion.observe(snapshot(
            tick=2499,
            buildings=[{"actor_id": 14, "type": "weap", "hp_percent": 0.2}],
        )))
        next_message = companion.observe(snapshot(
            tick=2500,
            buildings=[{"actor_id": 14, "type": "weap", "hp_percent": 0.2}],
        ))
        self.assertIsNotNone(next_message)
        self.assertEqual(next_message.insight.key, "critical_damage")

    def test_heated_threat_escalation_bypasses_calm_message_budget(self) -> None:
        companion = Companion(router=FakeRouter())
        self.assertIsNotNone(companion.observe(snapshot(
            tick=1000,
            power_provided=20,
            power_drained=100,
        )))
        escalated = companion.observe(snapshot(
            tick=1010,
            power_provided=20,
            power_drained=100,
            buildings=[{"actor_id": 10, "type": "weap", "cell_x": 10, "cell_y": 10}],
            visible_enemies=[{"actor_id": 90, "type": "3tnk", "cell_x": 12, "cell_y": 10}],
        ))
        self.assertIsNotNone(escalated)
        self.assertEqual(escalated.insight.key, "enemy_spotted")
        self.assertIn(companion.current_threat.level, {"high", "critical"})

    def test_threat_detector_reports_calm_guarded_high_and_critical(self) -> None:
        self.assertEqual(assess_threat(snapshot()).level, "calm")
        opening = assess_threat(snapshot(tick=1000, harvester_count=0, buildings=[]))
        self.assertEqual(opening.score, 0)
        self.assertEqual(opening.level, "calm")
        self.assertEqual(assess_threat(snapshot(
            visible_enemies=[{"actor_id": 90, "type": "e1", "cell_x": 50, "cell_y": 50}],
        )).level, "guarded")
        high = assess_threat(snapshot(
            buildings=[{"actor_id": 10, "type": "weap", "cell_x": 10, "cell_y": 10}],
            units=[{"actor_id": 1, "type": "e1", "cell_x": 11, "cell_y": 10, "can_attack": True}],
            visible_enemies=[{"actor_id": 90, "type": "3tnk", "cell_x": 13, "cell_y": 10}],
        ))
        self.assertEqual(high.level, "high")
        critical = assess_threat(snapshot(
            buildings=[{"actor_id": 10, "type": "weap", "cell_x": 10, "cell_y": 10}],
            visible_enemies=[
                {"actor_id": actor_id, "type": "3tnk", "cell_x": 12 + actor_id, "cell_y": 10}
                for actor_id in range(1, 5)
            ],
        ))
        self.assertEqual(critical.level, "critical")
        self.assertGreaterEqual(critical.score, 70)

    def test_heated_context_suggests_defense_but_waits_for_confirmation(self) -> None:
        executions = []

        def execute(request_id, expected_tick, commands):  # noqa: ANN001
            executions.append((request_id, expected_tick, commands))
            return ActionReceipt(request_id, True, expected_tick, "Queued confirmed defensive orders.")

        companion = Companion(router=FakeRouter(), action_executor=execute)
        response = companion.observe(snapshot(
            tick=1000,
            map_info={"map_name": "Threat Test", "width": 64, "height": 64},
            units=[
                {"actor_id": 1, "type": "e1", "cell_x": 11, "cell_y": 10, "is_idle": True, "can_attack": True},
                {"actor_id": 2, "type": "1tnk", "cell_x": 12, "cell_y": 10, "is_idle": True, "can_attack": True},
            ],
            buildings=[{"actor_id": 10, "type": "weap", "cell_x": 10, "cell_y": 10}],
            visible_enemies=[{"actor_id": 90, "type": "3tnk", "cell_x": 14, "cell_y": 10}],
        ))
        self.assertEqual(response.source, "contextual-action-suggestion")
        self.assertEqual(response.metadata["action"]["state"], "pending")
        self.assertEqual(executions, [])
        self.assertTrue(all(command["action"] == "attack_move" for command in response.metadata["action"]["commands"]))

        receipt = companion.handle_player_input("confirm")
        self.assertEqual(receipt.metadata["action"]["state"], "executed")
        self.assertEqual(len(executions), 1)

    def test_low_power_context_suggests_available_power_plant(self) -> None:
        companion = Companion(router=FakeRouter())
        response = companion.observe(snapshot(
            tick=1000,
            power_provided=20,
            power_drained=100,
            available_production=["powr", "barr"],
        ))
        self.assertEqual(response.source, "contextual-action-suggestion")
        self.assertEqual(response.metadata["action"]["commands"][0]["item_type"], "powr")

    def test_opening_mcv_is_immediately_suggested_but_not_auto_executed(self) -> None:
        executions = []
        companion = Companion(router=FakeRouter(), action_executor=lambda *args: executions.append(args))

        response = companion.observe(snapshot(
            tick=30,
            map_info={"width": 64, "height": 64},
            harvester_count=0,
            units=[{"actor_id": 119, "type": "mcv", "cell_x": 20, "cell_y": 20}],
            buildings=[],
            production=[],
        ))

        self.assertEqual(response.source, "contextual-action-suggestion")
        self.assertEqual(response.metadata["action"]["commands"][0]["action"], "deploy")
        self.assertEqual(response.metadata["action"]["commands"][0]["actor_id"], 119)
        self.assertEqual(executions, [])

    def test_routine_situation_suggests_second_harvester(self) -> None:
        companion = Companion(router=FakeRouter(), insights=InsightEngine(situation_interval_ticks=1))
        self.assertIsNone(companion.observe(snapshot(
            tick=100,
            available_production=["harv", "e1"],
        )))

        response = companion.observe(snapshot(
            tick=1600,
            available_production=["harv", "e1"],
            buildings=[{"actor_id": 10, "type": "weap"}],
        ))

        self.assertEqual(response.source, "contextual-action-suggestion")
        self.assertEqual(response.metadata["action"]["commands"][0]["item_type"], "harv")

    def test_routine_opening_suggests_power_before_units(self) -> None:
        companion = Companion(router=FakeRouter(), insights=InsightEngine(situation_interval_ticks=1))
        self.assertIsNone(companion.observe(snapshot(tick=100)))

        response = companion.observe(snapshot(
            tick=1600,
            buildings=[{"actor_id": 10, "type": "fact"}],
            available_production=["powr", "e1"],
        ))

        self.assertEqual(response.source, "contextual-action-suggestion")
        command = response.metadata["action"]["commands"][0]
        self.assertEqual(command["action"], "build")
        self.assertEqual(command["item_type"], "powr")

    def test_storage_warning_queues_silo_before_optional_production(self) -> None:
        companion = Companion(router=FakeRouter())
        live = snapshot(
            tick=1800,
            ore=1700,
            resource_capacity=2000,
            harvester_count=1,
            buildings=[{"actor_id": 10, "type": "fact"}, {"actor_id": 11, "type": "proc"}],
            available_production=["silo", "powr", "e1"],
        )
        companion.update_snapshot(live)

        response = companion.propose_routine_action()

        self.assertEqual(response.insight.key, "storage_pressure")
        self.assertEqual(response.metadata["action"]["commands"][0]["item_type"], "silo")

    def test_unresolved_storage_pressure_retries_as_an_event_without_feed_spam(self) -> None:
        companion = Companion(router=FakeRouter())
        first = companion.observe(snapshot(
            tick=1800,
            ore=1900,
            resource_capacity=2000,
            production=[],
            available_production=["silo"],
        ))
        first_event = companion.take_event_context()

        suppressed = companion.observe(snapshot(
            tick=1900,
            ore=1950,
            resource_capacity=2000,
            production=[],
            available_production=["silo"],
        ))
        retry_event = companion.take_event_context()

        self.assertEqual(first.insight.key, "storage_pressure")
        self.assertEqual(first_event["storage"]["percent"], 95.0)
        self.assertIsNone(suppressed)
        self.assertEqual(retry_event["type"], "storage_pressure")
        self.assertFalse(retry_event["storage"]["silo_queued"])

    def test_saturated_storage_converts_reserves_to_combat_instead_of_more_silos(self) -> None:
        companion = Companion(router=FakeRouter())
        response = companion.observe(snapshot(
            tick=3000,
            map_info={"map_name": "Singles", "width": 112, "height": 54},
            ore=9500,
            resource_capacity=10000,
            harvester_count=3,
            buildings=[
                {"actor_id": 10, "type": "fact"},
                {"actor_id": 11, "type": "proc"},
                {"actor_id": 12, "type": "weap"},
                {"actor_id": 20, "type": "silo"},
                {"actor_id": 21, "type": "silo"},
                {"actor_id": 22, "type": "silo"},
            ],
            available_production=["silo", "3tnk"],
            production=[],
        ))

        command = response.metadata["action"]["commands"][0]
        self.assertEqual(response.insight.key, "storage_pressure")
        self.assertEqual(command["action"], "train")
        self.assertEqual(command["item_type"], "3tnk")
        self.assertEqual(response.metadata["event"]["storage"]["maximum_silos"], 3)

        routine_companion = Companion(router=FakeRouter())
        routine_companion.update_snapshot(snapshot(
            tick=3100,
            map_info={"map_name": "Singles", "width": 112, "height": 54},
            ore=9500,
            resource_capacity=10000,
            harvester_count=3,
            buildings=[
                {"actor_id": 10, "type": "fact"},
                {"actor_id": 11, "type": "proc"},
                {"actor_id": 12, "type": "weap"},
                {"actor_id": 20, "type": "silo"},
                {"actor_id": 21, "type": "silo"},
                {"actor_id": 22, "type": "silo"},
            ],
            available_production=["silo", "3tnk"],
            production=[],
        ))
        routine = routine_companion.propose_routine_action()
        self.assertEqual(routine.metadata["action"]["commands"][0]["item_type"], "3tnk")

    def test_saturated_storage_uses_a_distinct_mixed_openra_batch(self) -> None:
        companion = Companion(router=FakeRouter())
        response = companion.observe(snapshot(
            tick=3000,
            map_info={"map_name": "Singles", "width": 112, "height": 54},
            ore=9500,
            resource_capacity=10000,
            harvester_count=3,
            units=[
                *({"actor_id": actor_id, "type": "e2", "is_idle": True, "can_attack": True}
                  for actor_id in range(1, 13)),
                *({"actor_id": actor_id, "type": "3tnk", "is_idle": True, "can_attack": True}
                  for actor_id in range(20, 26)),
            ],
            buildings=[
                {"actor_id": 40, "type": "fact"},
                {"actor_id": 41, "type": "proc"},
                {"actor_id": 42, "type": "weap"},
                {"actor_id": 43, "type": "silo"},
                {"actor_id": 44, "type": "silo"},
                {"actor_id": 45, "type": "silo"},
            ],
            production=[],
            available_production=["silo", "e1", "e2", "e3", "3tnk", "v2rl"],
        ))

        items = [command["item_type"] for command in response.metadata["action"]["commands"]]

        self.assertEqual(items[0], "v2rl")
        self.assertEqual(set(items[1:]), {"e1", "e3"})
        self.assertNotIn("silo", items)

    def test_learning_store_reviews_and_persists_match_feedback(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "attempt-1"
            evidence.mkdir()
            events = [
                {"event": "decision", "tick": 100, "decision": "Build economy", "evidence": "One harvester", "expected_result": "Stable income"},
                {"event": "commands", "tick": 110, "queued": [{"action": "build", "item_type": "proc"}], "economy": {"cash": 3000, "harvesters": 1, "storage_percent": 0}},
                {"event": "commands", "tick": 900, "queued": [{"action": "train", "item_type": "e1"}], "economy": {"cash": 500, "harvesters": 1, "storage_percent": 92}},
                {"event": "commands", "tick": 1200, "queued": [{"action": "train", "item_type": "v2rl"}], "counts": {"own_units": {"V2 Rocket Launcher": 1}}},
                {"event": "advance", "tick": 3000, "done": True, "result": "loss", "economy": {"cash": 0, "harvesters": 1, "storage_percent": 100}, "military": {"army_value": 6000}},
            ]
            (evidence / "tool-events.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
            (evidence / "agent-rounds.jsonl").write_text(json.dumps({"round": 1, "tick": 3000, "turn_budget_exhausted": True}) + "\n", encoding="utf-8")
            outcome = {
                "won": False,
                "result": "loss",
                "tick": 3000,
                "rounds": 1,
                "map_name": "singles.oramap",
                "opponent": "beginner",
                "model": "fake",
                "seed": 7,
                "state": {"player_faction": "ukraine", "enemy_faction": "france"},
                "snapshot": {"economy": {"cash": 0, "harvesters": 1}, "military": {"army_value": 6000, "buildings_killed": 4, "units_lost": 20, "kills_cost": 0, "deaths_cost": 2000}},
            }

            store = LearningStore(root / "learning")
            record = store.record(evidence, outcome)
            dashboard = store.dashboard()

            self.assertFalse(record["won"])
            self.assertEqual(record["decisions"]["logged_rationales"], 1)
            self.assertTrue(any("silo" in lesson.lower() for lesson in record["assessment"]["improvements"]))
            self.assertTrue(any("two protected siege" in lesson.lower() for lesson in record["assessment"]["improvements"]))
            self.assertEqual(record["visual_evidence"]["frame_count"], 0)
            self.assertEqual(dashboard["attempts"], 1)
            self.assertEqual(dashboard["by_difficulty"]["beginner"]["wins"], 0)
            self.assertIn("silo", store.context("singles.oramap", "beginner").lower())
            self.assertIn("silo", store.context("singles.oramap", "normal").lower())

            outcome["tick"] = 3100
            store.record(evidence, outcome)
            updated = store.dashboard()
            self.assertEqual(updated["attempts"], 1)
            self.assertEqual(updated["latest_attempt"]["tick"], 3100)

    def test_completed_production_replaces_progress_message(self) -> None:
        companion = Companion(router=FakeRouter())
        self.assertIsNone(companion.observe(snapshot(
            tick=1000,
            production=[{"item": "proc", "progress": 0.95, "remaining_ticks": 20}],
        )))
        completed = companion.observe(snapshot(
            tick=1010,
            buildings=[{"actor_id": 14, "type": "proc"}],
            production=[],
        ))
        self.assertIsNotNone(completed)
        self.assertEqual(completed.insight.key, "production_complete:proc")

    def test_completed_combat_unit_does_not_interrupt_the_feed_or_planner(self) -> None:
        companion = Companion(router=FakeRouter())
        self.assertIsNone(companion.observe(snapshot(
            tick=1000,
            production=[{"queue_type": "Infantry", "item": "e2", "progress": 0.95}],
        )))

        completed = companion.observe(snapshot(
            tick=1010,
            units=[{"actor_id": 50, "type": "e2"}],
            production=[],
        ))

        self.assertIsNone(completed)
        self.assertIsNone(companion.take_event_context())

    def test_completed_building_in_queue_emits_full_event_and_place_action(self) -> None:
        companion = Companion(router=FakeRouter())
        self.assertIsNone(companion.observe(snapshot(
            tick=1000,
            map_info={"map_name": "Event Test", "width": 64, "height": 64},
            buildings=[{"actor_id": 10, "type": "fact", "cell_x": 20, "cell_y": 20}],
            production=[{
                "queue_type": "Building",
                "item": "proc",
                "progress": 0.95,
                "remaining_ticks": 20,
            }],
        )))

        completed = companion.observe(snapshot(
            tick=1010,
            map_info={"map_name": "Event Test", "width": 64, "height": 64},
            buildings=[{"actor_id": 10, "type": "fact", "cell_x": 20, "cell_y": 20}],
            visible_enemies=[{"actor_id": 90, "type": "e1", "cell_x": 40, "cell_y": 40}],
            production=[{
                "queue_type": "Building",
                "item": "proc",
                "progress": 1.0,
                "remaining_ticks": 0,
            }],
        ))

        self.assertEqual(completed.insight.key, "production_complete:proc")
        self.assertEqual(completed.source, "contextual-action-suggestion")
        self.assertEqual(completed.metadata["action"]["commands"][0]["action"], "place_building")
        event = completed.metadata["event"]
        self.assertEqual(event["type"], "production_complete:proc")
        self.assertEqual(event["battlefield"]["tick"], 1010)
        self.assertEqual(event["battlefield"]["economy"]["harvesters"], 1)
        self.assertEqual(event["battlefield"]["visible_enemies"][0]["actor_id"], 90)
        self.assertIn("tactical_plan", event)
        self.assertEqual(event["direct_action"]["state"], "pending")

    def test_completed_defense_is_immediately_placeable(self) -> None:
        companion = Companion(router=FakeRouter())

        completed = companion.observe(snapshot(
            tick=1000,
            buildings=[{"actor_id": 10, "type": "fact"}],
            production=[{
                "queue_type": "Defense",
                "item": "gun",
                "progress": 1.0,
                "remaining_ticks": 0,
            }],
        ))

        self.assertEqual(completed.insight.key, "production_complete:gun")
        self.assertEqual(completed.metadata["action"]["commands"][0]["action"], "place_building")

    def test_priority_completion_bypasses_calm_message_interval(self) -> None:
        companion = Companion(router=FakeRouter())
        first = companion.observe(snapshot(
            tick=1000,
            power_provided=50,
            power_drained=100,
            production=[{
                "queue_type": "Building",
                "item": "proc",
                "progress": 0.95,
                "remaining_ticks": 20,
            }],
        ))
        self.assertEqual(first.insight.key, "low_power")

        completed = companion.observe(snapshot(
            tick=1010,
            power_provided=50,
            power_drained=100,
            production=[{
                "queue_type": "Building",
                "item": "proc",
                "progress": 1.0,
                "remaining_ticks": 0,
            }],
        ))

        self.assertEqual(completed.insight.key, "production_complete:proc")

    def test_suppressed_ui_alert_still_exposes_event_context_to_auto_mode(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.observe(snapshot(
            tick=1000,
            power_provided=20,
            power_drained=100,
        ))
        companion.take_event_context()

        suppressed = companion.observe(snapshot(
            tick=1010,
            power_provided=20,
            power_drained=100,
            buildings=[{"actor_id": 14, "type": "weap", "hp_percent": 0.2}],
        ))
        event = companion.take_event_context()

        self.assertIsNone(suppressed)
        self.assertEqual(event["type"], "critical_damage")
        self.assertEqual(event["battlefield"]["own_buildings"][0]["actor_id"], 14)

    def test_interrupt_discards_inflight_result(self) -> None:
        companion = Companion(router=FakeRouter(delay=0.1))
        output = []
        worker = threading.Thread(target=lambda: output.append(companion.observe(snapshot(visible_enemies=[{"actor_id": 9, "type": "3tnk"}]))))
        worker.start()
        time.sleep(0.02)
        companion.interrupt()
        worker.join()
        self.assertTrue(output[0].interrupted)
        self.assertEqual(output[0].text, "")

    def test_power_alert_and_controls(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.configure(muted=True)
        response = companion.observe(snapshot(power_provided=50, power_drained=125))
        self.assertEqual(response.insight.key, "low_power")
        self.assertTrue(response.text)
        audio, metadata = companion.speech("test")
        self.assertEqual(audio, b"")
        self.assertTrue(metadata["disabled"])

    def test_voice_off_keeps_transcription_and_text_answers(self) -> None:
        companion = Companion(router=FakeRouter())
        companion.latest_snapshot = snapshot()
        companion.configure(muted=True)
        self.assertEqual(companion.transcribe(b"audio").text, "Where is the threat?")
        self.assertTrue(companion.ask("Where is the threat?").text)
        self.assertEqual(companion.idle_status(), ("muted", "AI VOICE OFF  •  TEXT INSIGHTS STAY ON"))

    def test_voice_routes_share_same_router(self) -> None:
        companion = Companion(router=FakeRouter())
        self.assertEqual(companion.transcribe(b"audio").text, "Where is the threat?")
        audio, metadata = companion.speech("Hold the center")
        self.assertEqual(audio, b"RIFFfake")
        self.assertFalse(metadata["interrupted"])

    def test_mission_draft_does_not_require_a_live_game_snapshot(self) -> None:
        companion = Companion(router=FakeRouter())
        response = companion.draft_mission({
            "location": "Riyadh",
            "archetype": "River Crossing",
            "map": {"spawns": 2, "resource_cells": 140},
        })
        self.assertEqual(response.source, "ai-layer")
        self.assertTrue(response.text)
        self.assertEqual(companion.router.calls, 1)

    def test_terrain_analysis_uses_router_vision(self) -> None:
        result = Companion(router=FakeRouter()).analyze_terrain({"location": "Riyadh"}, b"PNG")
        self.assertEqual(result["biome"], "desert")
        self.assertTrue(result["vision_used"])
        self.assertEqual(result["model"], "fake-vision")

    def test_full_vision_combines_live_viewport_and_tactical_overview(self) -> None:
        router = VisionRouter()
        companion = Companion(router=router)
        companion.latest_snapshot = spatial_snapshot(tick=1200)
        companion.set_frame_provider(lambda: VisionFrame(b"viewport-png", 1201, 1280, 720))

        response = companion.ask("What can you see?")

        self.assertTrue(response.metadata["vision"]["used"])
        self.assertEqual(len(response.metadata["vision"]["views"]), 2)
        self.assertEqual(response.metadata["vision"]["views"][0]["scope"], "rendered-player-viewport-fog-respecting")
        self.assertEqual(response.metadata["vision"]["views"][1]["scope"], "full-map-tactical-overview-fog-respecting")
        self.assertEqual(len(router.vision_requests[0][1]), 2)

    def test_action_interpretation_uses_vision_but_keeps_confirmation_boundary(self) -> None:
        router = VisionRouter(json.dumps({
            "mode": "action",
            "summary": "Move the visible tank east",
            "commands": [{"action": "move", "actor_id": 1, "target_x": 7, "target_y": 4}],
        }))
        companion = Companion(router=router)
        companion.latest_snapshot = spatial_snapshot(
            tick=1200,
            units=[{"actor_id": 1, "type": "1tnk", "cell_x": 4, "cell_y": 4, "can_attack": True}],
        )

        response = companion.handle_player_input("Move that tank east")

        self.assertEqual(response.source, "action-proposal")
        self.assertTrue(response.metadata["vision"]["used"])
        self.assertEqual(response.metadata["action"]["state"], "pending")

    def test_tactical_overview_keeps_hidden_cells_black(self) -> None:
        channels = 9
        values = [0.0] * (2 * channels)
        values[2] = 10.0
        values[8] = 3.0
        values[channels + 3] = 1.0
        values[channels + 4] = 1.0
        values[channels + 5] = 1.0
        current = snapshot(
            map_info={"map_name": "Fog Test", "width": 2, "height": 1},
            spatial_map=struct.pack(f"<{len(values)}f", *values),
            spatial_channels=channels,
        )

        png = tactical_overview_png(current)

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual((width, height), (12, 6))
        offset = 8
        compressed = b""
        while offset < len(png):
            length = struct.unpack(">I", png[offset : offset + 4])[0]
            kind = png[offset + 4 : offset + 8]
            data = png[offset + 8 : offset + 8 + length]
            if kind == b"IDAT":
                compressed += data
            offset += 12 + length
        scanline = zlib.decompress(compressed)
        self.assertEqual(scanline[1:4], bytes((5, 7, 11)))
        self.assertEqual(scanline[1 + 6 * 3 : 1 + 7 * 3], bytes((72, 224, 224)))

    def test_live_frame_failure_falls_back_to_tactical_vision(self) -> None:
        router = VisionRouter()
        companion = Companion(router=router)
        companion.latest_snapshot = spatial_snapshot(tick=1200)

        def unavailable():
            raise RuntimeError("renderer unavailable")

        companion.set_frame_provider(unavailable)
        response = companion.ask("Where are my forces?")
        self.assertEqual(len(response.metadata["vision"]["views"]), 1)
        self.assertEqual(response.metadata["vision"]["views"][0]["scope"], "full-map-tactical-overview-fog-respecting")
        self.assertIn("renderer unavailable", companion.status()["vision"]["last_frame_error"])

    def test_router_sends_terrain_as_multimodal_image_content(self) -> None:
        router = AIRouter(Settings(text_model="text-route", vision_model="vision-route"))
        captured = {}

        def request(path, body, content_type):  # noqa: ANN001
            captured.update({"path": path, "body": json.loads(body), "content_type": content_type})
            return b'{"choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":8,"completion_tokens":1}}', 9, "application/json"

        with mock.patch.object(router, "_request", side_effect=request):
            result = router.vision("Read this terrain", b"\x89PNG\r\n\x1a\nimage")
        self.assertEqual(result.model, "vision-route")
        self.assertEqual(captured["body"]["model"], "vision-route")
        content = captured["body"]["messages"][0]["content"]
        self.assertEqual(content[0]["text"], "Read this terrain")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(content[1]["image_url"]["detail"], "high")

    def test_text_only_local_vision_route_falls_back_to_structured_context(self) -> None:
        router = AIRouter(Settings(text_model="local-coder", vision_model="local-coder"))
        requests = []

        def request(path, body, content_type):  # noqa: ANN001
            payload = json.loads(body)
            requests.append(payload)
            if len(requests) == 1:
                raise RouterError("AI router returned HTTP 400: model is not a multimodal model")
            return b'{"choices":[{"message":{"content":"Hold the ridge."}}]}', 8, "application/json"

        with mock.patch.object(router, "_request", side_effect=request):
            result = router.vision_many("CONTEXT: structured snapshot", [(b"PNG", "image/png")])

        self.assertEqual(result.text, "Hold the ridge.")
        self.assertEqual(result.model, "local-coder")
        self.assertFalse(result.vision_used)
        self.assertEqual(len(requests), 2)
        self.assertIsInstance(requests[0]["messages"][0]["content"], list)
        self.assertEqual(requests[1]["messages"][1]["content"], "CONTEXT: structured snapshot")

    def test_transcription_is_pinned_to_the_configured_app_language(self) -> None:
        router = AIRouter(Settings(transcribe_language="en"))
        captured = {}
        audio = _wav_bytes([b"\x00\x00" * 160], 16_000)

        def request(path, body, content_type):  # noqa: ANN001
            captured.update({"path": path, "body": body, "content_type": content_type})
            return b'{"text":"Okay, what can you do?"}', 8, "application/json"

        with mock.patch.object(router, "_request", side_effect=request):
            result = router.transcribe(audio)

        self.assertEqual(result.text, "Okay, what can you do?")
        self.assertEqual(captured["path"], "/v1/audio/transcriptions")
        self.assertIn(b'name="language"\r\n\r\nen\r\n', captured["body"])

    def test_router_catalogue_groups_hosted_and_local_models(self) -> None:
        router = AIRouter(Settings())
        payload = {
            "data": [
                {
                    "model_name": "gpt-5.5",
                    "litellm_params": {"model": "openai/gpt-5.5"},
                    "model_info": {"mode": "chat", "litellm_provider": "openai"},
                },
                {
                    "model_name": "local-small",
                    "litellm_params": {"model": "openai/qwen-small", "api_base": "http://localhost:8006/v1"},
                    "model_info": {"mode": "chat", "litellm_provider": "openai"},
                },
            ]
        }
        with mock.patch.object(router, "_get_json", return_value=payload):
            catalogue = router.catalogue()
        models = {model["id"]: model for model in catalogue["models"]}
        self.assertEqual(models["gpt-5.5"]["provider"], "openai")
        self.assertEqual(models["local-small"]["provider"], "local")
        self.assertTrue(models["local-small"]["local"])
        self.assertFalse(next(provider for provider in catalogue["providers"] if provider["id"] == "openai")["requires_endpoint"])
        self.assertTrue(next(provider for provider in catalogue["providers"] if provider["id"] == "custom")["requires_endpoint"])

    def test_local_routes_report_zero_provider_cost(self) -> None:
        usage = AIRouter(Settings()).usage_summary()
        self.assertEqual(usage["session_cost_usd"], 0.0)
        self.assertEqual(usage["hourly_cost_usd"], 0.0)
        self.assertTrue(usage["pricing_known"])
        self.assertTrue(all("Local" in assumption for assumption in usage["assumptions"]))

    def test_playback_failure_does_not_terminate_the_companion(self) -> None:
        companion = Companion(router=FakeRouter())
        self.assertFalse(_speak(companion, "Hold the center", FailingPlayer()))

    def test_speech_route_rejects_non_wav_payloads(self) -> None:
        router = AIRouter(Settings())
        with mock.patch.object(router, "_request", return_value=(b'{"error":"bad route"}', 4, "application/json")):
            with self.assertRaises(RouterError):
                router.speech("Test")

    def test_push_to_talk_frames_are_packaged_as_mono_wav(self) -> None:
        audio = _wav_bytes([b"\x00\x00" * 160], 16_000)
        self.assertTrue(audio.startswith(b"RIFF"))
        with wave.open(BytesIO(audio), "rb") as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getframerate(), 16_000)
            self.assertEqual(wav.getnframes(), 160)

    def test_streaming_wav_lengths_are_normalized_for_windows(self) -> None:
        audio = bytearray(_wav_bytes([b"\x00\x00" * 160], 24_000))
        audio[4:8] = b"\xff\xff\xff\xff"
        data = audio.index(b"data")
        audio[data + 4 : data + 8] = b"\xff\xff\xff\xff"
        normalized = _normalize_wav(bytes(audio))
        with wave.open(BytesIO(normalized), "rb") as wav:
            self.assertEqual(wav.getnframes(), 160)
            self.assertEqual(wav.getframerate(), 24_000)

    def test_settings_are_validated_and_saved_outside_the_repository(self) -> None:
        with TemporaryDirectory() as directory, mock.patch.dict("os.environ", {"APPDATA": directory}, clear=True):
            updated = Settings().with_updates({"text_model": "local-companion", "timeout_seconds": 12})
            path = updated.save()
            self.assertEqual(path.parent.name, "OpenRA-AI")
            self.assertEqual(Settings.from_env().text_model, "local-companion")
            with self.assertRaises(ValueError):
                updated.with_updates({"router_url": "not-a-url"})

    def test_product_launch_forces_companion_enabled_for_each_session(self) -> None:
        with TemporaryDirectory() as directory, mock.patch.dict(
            "os.environ",
            {"APPDATA": directory, "OPENRA_AI_COMPANION_ENABLED": "1"},
            clear=True,
        ):
            Settings(companion_enabled=False).save()
            self.assertTrue(Settings.from_env().companion_enabled)

    def test_transcription_language_follows_app_language_and_falls_back_to_english(self) -> None:
        with TemporaryDirectory() as directory, mock.patch.dict(
            "os.environ",
            {"APPDATA": directory, "OPENRA_AI_APP_LANGUAGE": "en-US"},
            clear=True,
        ):
            self.assertEqual(Settings.from_env().transcribe_language, "en")

        self.assertEqual(Settings(transcribe_language="not-a-language").validated().transcribe_language, "en")

    def test_companion_console_and_full_diagnostic_http_path(self) -> None:
        router = FakeRouter()
        player = FakePlayer()
        server = create_server("127.0.0.1", 0, Companion(router=router), player)
        statuses = []
        server.status_publisher = lambda state, message: statuses.append((state, message))
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/", timeout=3) as response:
                console = response.read()
            self.assertIn(b"Companion Console", console)
            self.assertIn(b"AI WAR ROOM", console)
            self.assertIn(b"Learning Lab", console)
            self.assertIn(b"Brain Inspector", console)
            with urllib.request.urlopen(base + "/v1/state", timeout=3) as response:
                state = response.read()
            self.assertIn(b'"session_cost_usd": 0.001', state)
            self.assertIn(b'"snapshot": null', state)
            self.assertIn(b'"threat":', state)
            with urllib.request.urlopen(base + "/v1/catalog", timeout=3) as response:
                catalogue = response.read()
            self.assertIn(b'"requires_endpoint": false', catalogue)
            with TemporaryDirectory() as learning_directory, mock.patch.dict(
                "os.environ", {"OPENRA_AI_LEARNING_DIR": learning_directory}
            ):
                with urllib.request.urlopen(base + "/v1/learning", timeout=3) as response:
                    learning = response.read()
                self.assertIn(b'"attempts": 0', learning)
                with urllib.request.urlopen(base + "/v1/war-room", timeout=3) as response:
                    war_room = json.loads(response.read())
                self.assertEqual(war_room["contract_version"], 1)
                self.assertFalse(war_room["live"]["active"])
                self.assertEqual(war_room["learning"]["attempts"], 0)
                self.assertEqual(war_room["settings"]["text_model"], "fake")
                evidence = Path(learning_directory) / "evidence"
                frames = evidence / "frames"
                matches = Path(learning_directory) / "matches"
                frames.mkdir(parents=True)
                matches.mkdir()
                image = b"\x89PNG\r\n\x1a\nwar-room-frame"
                (frames / "known.png").write_bytes(image)
                (matches / "attempt-1.json").write_text(json.dumps({
                    "attempt_id": "attempt-1",
                    "evidence_dir": str(evidence),
                    "visual_evidence": {"recent_frames": [{"file": "frames/known.png", "tick": 500}]},
                }), encoding="utf-8")
                with urllib.request.urlopen(
                    base + "/v1/learning/matches/attempt-1/frames/known.png", timeout=3
                ) as response:
                    self.assertEqual(response.headers["Content-Type"], "image/png")
                    self.assertEqual(response.read(), image)
                with self.assertRaises(urllib.error.HTTPError) as missing:
                    urllib.request.urlopen(
                        base + "/v1/learning/matches/attempt-1/frames/unlisted.png", timeout=3
                    )
                self.assertEqual(missing.exception.code, 404)
            request = urllib.request.Request(
                base + "/v1/state",
                data=b'{"notification_pace":"balanced","voice_priority":"important","transcribe_language":"en"}',
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                state = response.read()
            self.assertIn(b'"notification_pace": "balanced"', state)
            self.assertIn(b'"transcribe_language": "en"', state)
            request = urllib.request.Request(base + "/v1/test/full", data=b"{}", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = response.read()
            self.assertIn(b'"ok": true', payload)
            self.assertEqual(player.audio, b"RIFFfake")
            request = urllib.request.Request(
                base + "/v1/design/mission",
                data=b'{"location":"Riyadh","archetype":"River Crossing"}',
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = response.read()
            self.assertIn(b'"source": "ai-layer"', payload)
            request = urllib.request.Request(
                base + "/v1/control",
                data=b'{"muted":true}',
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = response.read()
            self.assertIn(b'"muted": true', payload)
            self.assertEqual(player.audio, b"")
            self.assertEqual(statuses[-1][0], "muted")
            request = urllib.request.Request(
                base + "/v1/control",
                data=b'{"auto_act":true}',
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = response.read()
            self.assertIn(b'"auto_act": true', payload)
            self.assertEqual(statuses[-1][0], "auto-active:normal")
            self.assertEqual(player.audio, b"")
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
