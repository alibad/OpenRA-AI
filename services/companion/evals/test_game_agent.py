from __future__ import annotations

import struct
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openra_ai_companion.agent_models import (
    LOCAL_PROMPT_TRUNCATION_TOKENS,
    agent_model_settings,
)
from openra_ai_companion.autonomous import (
    LOCAL_AUTOPLAY_MAX_TOKENS,
    _extract_text_tool_calls,
    _game_child_environment,
    _priority_production_cancellations,
)
from openra_ai_companion.bridge import ACTION_TYPES
from openra_ai_companion import game_mcp
from openra_ai_companion.game_mcp import mcp
from openra_ai_companion.game_runtime import GameRuntime
from openra_ai_companion.models import ActionCommand, GameSnapshot, SAFE_ACTIONS, Unit
from openra_ai_companion.strategy import tactical_plan


EXPECTED_ACTIONS = {
    "move",
    "attack_move",
    "attack",
    "demolish",
    "capture",
    "infiltrate",
    "disguise",
    "stop",
    "harvest",
    "build",
    "train",
    "deploy",
    "sell",
    "repair",
    "place_building",
    "cancel_production",
    "set_rally_point",
    "guard",
    "set_stance",
    "enter_transport",
    "unload",
    "power_down",
    "set_primary",
    "use_support_power",
}


def snapshot(**updates: object) -> GameSnapshot:
    value = {
        "tick": 100,
        "map_info": {"map_name": "Eval", "width": 64, "height": 64},
        "economy": {"cash": 5000},
        "units": [
            {"actor_id": 1, "type": "mcv", "cell_x": 8, "cell_y": 8},
            {"actor_id": 2, "type": "1tnk", "cell_x": 10, "cell_y": 10, "can_attack": True},
            {"actor_id": 3, "type": "lst", "cell_x": 11, "cell_y": 10, "passenger_count": 0},
        ],
        "buildings": [{"actor_id": 10, "type": "fact", "cell_x": 8, "cell_y": 8}],
        "visible_enemies": [{"actor_id": 90, "type": "3tnk", "cell_x": 20, "cell_y": 20}],
        "visible_enemy_buildings": [{"actor_id": 91, "type": "powr", "cell_x": 25, "cell_y": 25}],
        "available_production": ["powr", "e1"],
        "production": [{"item": "proc", "progress": 1.0}],
    }
    value.update(updates)
    return GameSnapshot.from_dict(value)


class GameAgentEvalTests(unittest.TestCase):
    def test_local_autoplay_reserves_context_headroom_for_mcp_tools(self) -> None:
        self.assertLessEqual(LOCAL_AUTOPLAY_MAX_TOKENS, 512)
        settings = agent_model_settings(
            local=True,
            max_tokens=LOCAL_AUTOPLAY_MAX_TOKENS,
            reasoning_effort="medium",
        )
        self.assertEqual(
            settings.extra_body,
            {"truncate_prompt_tokens": LOCAL_PROMPT_TRUNCATION_TOKENS},
        )
        self.assertLess(
            LOCAL_PROMPT_TRUNCATION_TOKENS + LOCAL_AUTOPLAY_MAX_TOKENS,
            32_768,
        )

    def test_priority_tech_refunds_expendable_queues_before_deadlock(self) -> None:
        current = snapshot(
            economy={"cash": 0, "ore": 0, "resource_capacity": 2000},
            production=[
                {"queue_type": "Building", "item": "dome", "progress": 0.25},
                {"queue_type": "Vehicle", "item": "1tnk"},
                {"queue_type": "Infantry", "item": "e1"},
                {"queue_type": "Vehicle", "item": "harv"},
            ],
        )

        commands = _priority_production_cancellations(current, target="dome")

        self.assertEqual(
            commands,
            (
                ActionCommand("cancel_production", item_type="1tnk"),
                ActionCommand("cancel_production", item_type="e1"),
            ),
        )

    def test_rolling_queue_caps_reject_one_type_resource_lockups(self) -> None:
        vehicle_locked = snapshot(
            available_production=["1tnk", "e1"],
            production=[
                {"queue_type": "Vehicle", "item": "1tnk"},
                {"queue_type": "Vehicle", "item": "1tnk"},
            ],
        )
        infantry_batch = tuple(
            ActionCommand("train", item_type="e1", queued=True)
            for _ in range(5)
        )

        with self.assertRaisesRegex(ValueError, "rolling queue limit of 2"):
            GameRuntime._validate(
                vehicle_locked,
                (ActionCommand("train", item_type="1tnk", queued=True),),
            )
        with self.assertRaisesRegex(ValueError, "rolling queue limit of 4"):
            GameRuntime._validate(vehicle_locked, infantry_batch)

    def test_literal_local_tool_markup_is_recovered(self) -> None:
        output = """<tool_call>
        {"name":"train","arguments":{"item_type":"e1","count":2}}
        <tool_call>
        {"name":"advance","arguments":{"ticks":500}}
        </tool_call>"""

        calls = _extract_text_tool_calls(output)

        self.assertEqual(calls, (
            ("train", {"item_type": "e1", "count": 2}),
            ("advance", {"ticks": 500}),
        ))

    def test_complete_safe_gameplay_surface_is_mapped(self) -> None:
        self.assertEqual(set(SAFE_ACTIONS), EXPECTED_ACTIONS)
        self.assertEqual(set(ACTION_TYPES), EXPECTED_ACTIONS)
        self.assertNotIn("surrender", SAFE_ACTIONS)

    def test_mcp_publishes_every_safe_action_and_no_match_loss_tool(self) -> None:
        names = {tool.name for tool in mcp._tool_manager.list_tools()}
        self.assertTrue(EXPECTED_ACTIONS.issubset(names))
        self.assertTrue({"battlefield", "match_status", "advance"}.issubset(names))
        self.assertNotIn("surrender", names)
        self.assertNotIn("destroy_match", names)

    def test_hidden_or_invented_attack_targets_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a visible enemy"):
            GameRuntime._validate(snapshot(), (ActionCommand("attack", actor_id=2, target_actor_id=999),))

    def test_visible_enemy_units_and_buildings_are_valid_attack_targets(self) -> None:
        GameRuntime._validate(snapshot(), (ActionCommand("attack", actor_id=2, target_actor_id=90),))
        GameRuntime._validate(snapshot(), (ActionCommand("attack", actor_id=2, target_actor_id=91),))

    def test_unowned_actors_and_out_of_bounds_moves_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not an owned unit"):
            GameRuntime._validate(snapshot(), (ActionCommand("move", actor_id=999, target_x=5, target_y=5),))
        with self.assertRaisesRegex(ValueError, "outside the map"):
            GameRuntime._validate(snapshot(), (ActionCommand("move", actor_id=2, target_x=100, target_y=5),))

    def test_production_and_placement_use_observed_exact_ids(self) -> None:
        GameRuntime._validate(snapshot(), (ActionCommand("build", item_type="powr"),))
        GameRuntime._validate(snapshot(), (ActionCommand("place_building", item_type="proc"),))
        with self.assertRaisesRegex(ValueError, "not currently available"):
            GameRuntime._validate(snapshot(), (ActionCommand("train", item_type="4tnk"),))

    def test_runtime_rejects_duplicate_silo_in_same_storage_episode(self) -> None:
        live = snapshot(
            economy={"cash": 5000, "ore": 1900, "resource_capacity": 2000},
            available_production=["silo"],
            production=[],
        )

        class FakeBridge:
            session_id = "eval"

            def fast_advance(self, ticks: int, commands: object, **kwargs: object) -> GameSnapshot:
                return live

        runtime = object.__new__(GameRuntime)
        runtime.bridge = FakeBridge()
        runtime.evidence_log = None
        runtime._snapshot = live
        runtime._lock = threading.Lock()
        runtime._last_interrupt_ticks = {}
        runtime._silo_episode_active = False
        runtime._silo_episode_capacity = 0

        runtime.issue((ActionCommand("build", item_type="silo"),))
        with self.assertRaisesRegex(ValueError, "already queued"):
            runtime.issue((ActionCommand("build", item_type="silo"),))

    def test_tactical_evidence_is_periodic_and_forced_at_decisions(self) -> None:
        values = [0.0] * (4 * 3 * 9)
        for cell in range(4 * 3):
            values[cell * 9 + 3] = 1.0
            values[cell * 9 + 4] = 1.0
        live = GameSnapshot(
            tick=250,
            map_width=4,
            map_height=3,
            spatial_channels=9,
            spatial_map=struct.pack(f"<{len(values)}f", *values),
        )

        class FakeBridge:
            session_id = "eval"

        with TemporaryDirectory() as directory:
            runtime = object.__new__(GameRuntime)
            runtime.bridge = FakeBridge()
            runtime.evidence_log = Path(directory) / "tool-events.jsonl"
            runtime._last_tactical_capture_tick = -125
            runtime._tactical_capture_sequence = 0

            self.assertIsNotNone(runtime._capture_tactical_evidence(live, "periodic"))
            self.assertIsNone(runtime._capture_tactical_evidence(live, "periodic"))
            self.assertIsNotNone(runtime._capture_tactical_evidence(live, "decision", force=True))

            self.assertEqual(len(list((Path(directory) / "frames").glob("*.png"))), 2)
            metadata = (Path(directory) / "frames.jsonl").read_text(encoding="utf-8")
            self.assertIn('"reason":"periodic"', metadata)
            self.assertIn('"reason":"decision"', metadata)

    def test_tactical_plan_protects_spies_siege_and_damaged_armor(self) -> None:
        live = snapshot(
            units=[
                {"actor_id": 1, "type": "spy", "cell_x": 12, "cell_y": 12},
                {"actor_id": 2, "type": "v2rl", "cell_x": 14, "cell_y": 12, "hp_percent": 0.25},
                {"actor_id": 3, "type": "3tnk", "cell_x": 15, "cell_y": 12, "hp_percent": 1.0},
                {"actor_id": 4, "type": "e2", "cell_x": 16, "cell_y": 12, "hp_percent": 1.0},
            ],
            buildings=[{"actor_id": 10, "type": "fix", "cell_x": 8, "cell_y": 8}],
            visible_enemies=[
                {"actor_id": 90, "type": "dog", "cell_x": 13, "cell_y": 12},
                {"actor_id": 91, "type": "e3", "cell_x": 18, "cell_y": 12, "can_attack": True, "attack_range": 5120},
                {"actor_id": 92, "type": "yak", "cell_x": 20, "cell_y": 12, "can_attack": True, "attack_range": 4096},
            ],
            available_production=["ftrk", "sam"],
        )

        plan = tactical_plan(live)

        self.assertEqual(plan["immediate_safety"]["spy_dog_escapes"][0]["spy_actor_id"], 1)
        self.assertEqual(plan["immediate_safety"]["damaged_armor_retreats"][0]["actor_id"], 2)
        self.assertEqual(plan["immediate_safety"]["siege_threats"][0]["siege_actor_id"], 2)
        self.assertIn(91, plan["focus_priorities"]["anti_armor_enemy_ids"])
        self.assertEqual(plan["air_response"]["visible_aircraft_ids"], [92])
        self.assertEqual(plan["air_response"]["available_counter_production"], ["ftrk", "sam"])
        self.assertEqual(plan["armor_assessment"]["own"]["heavy"], [3])

    def test_surrender_cannot_be_deserialized_as_a_command(self) -> None:
        with self.assertRaisesRegex(ValueError, "not allowed"):
            ActionCommand.from_dict({"action": "surrender"})

    def test_action_context_includes_targetable_enemy_building_ids(self) -> None:
        context = snapshot().action_context()
        self.assertEqual(context["visible_enemy_buildings"][0]["actor_id"], 91)

    def test_repeated_threat_interrupts_are_debounced_for_agent_progress(self) -> None:
        class FakeBridge:
            enabled_interrupts: tuple[str, ...] = ()

            def fast_advance(self, ticks: int, **kwargs: object) -> GameSnapshot:
                self.enabled_interrupts = tuple(kwargs["enabled_interrupts"])
                return GameSnapshot(tick=100 + ticks, actual_ticks_advanced=ticks)

        runtime = object.__new__(GameRuntime)
        runtime.bridge = FakeBridge()
        runtime.evidence_log = None
        runtime._snapshot = GameSnapshot(tick=100)
        runtime._lock = threading.Lock()
        runtime._last_interrupt_ticks = {
            "under_attack": 100,
            "enemy_spotted": 100,
            "unit_destroyed": 100,
            "production_complete": 100,
        }

        runtime.advance(250)

        self.assertNotIn("under_attack", runtime.bridge.enabled_interrupts)
        self.assertNotIn("enemy_spotted", runtime.bridge.enabled_interrupts)
        self.assertNotIn("unit_destroyed", runtime.bridge.enabled_interrupts)
        self.assertNotIn("production_complete", runtime.bridge.enabled_interrupts)
        self.assertIn("game_over", runtime.bridge.enabled_interrupts)

    def test_opening_advance_is_capped_until_the_economy_exists(self) -> None:
        class FakeBridge:
            applied_ticks = 0

            def fast_advance(self, ticks: int, **kwargs: object) -> GameSnapshot:
                self.applied_ticks = ticks
                return GameSnapshot(tick=100 + ticks, actual_ticks_advanced=ticks)

        runtime = object.__new__(GameRuntime)
        runtime.bridge = FakeBridge()
        runtime.evidence_log = None
        runtime._snapshot = GameSnapshot(tick=100)
        runtime._lock = threading.Lock()
        runtime._last_interrupt_ticks = {}

        result = runtime.advance(1500)

        self.assertEqual(runtime.bridge.applied_ticks, 50)
        self.assertEqual(result["requested_ticks"], 1500)
        self.assertEqual(result["applied_tick_cap"], 50)

    def test_campaign_advance_is_not_subject_to_skirmish_economy_cap(self) -> None:
        class FakeBridge:
            applied_ticks = 0

            def fast_advance(self, ticks: int, **kwargs: object) -> GameSnapshot:
                self.applied_ticks = ticks
                return GameSnapshot(tick=100 + ticks, actual_ticks_advanced=ticks, mission_mode=True)

        runtime = object.__new__(GameRuntime)
        runtime.bridge = FakeBridge()
        runtime.evidence_log = None
        runtime._snapshot = GameSnapshot(tick=100, mission_mode=True)
        runtime._lock = threading.Lock()
        runtime._last_interrupt_ticks = {}

        result = runtime.advance(1500)

        self.assertEqual(runtime.bridge.applied_ticks, 1500)
        self.assertEqual(result["applied_tick_cap"], 1500)

    def test_autonomous_building_placement_always_uses_optimizer(self) -> None:
        class FakeRuntime:
            command: ActionCommand | None = None

            def issue(self, commands: tuple[ActionCommand, ...], *, ticks: int = 1) -> dict:
                self.command = commands[0]
                return {"ok": True}

        fake = FakeRuntime()
        with patch.object(game_mcp, "runtime", fake), patch.object(game_mcp, "proposal_mode", False):
            game_mcp.place_building("proc", 8, 8)

        self.assertIsNotNone(fake.command)
        self.assertEqual((fake.command.target_x, fake.command.target_y), (0, 0))

    def test_game_children_do_not_inherit_provider_credentials(self) -> None:
        with patch.dict("os.environ", {
            "OPENAI_API_KEY": "not-a-real-key",
            "GITHUB_TOKEN": "not-a-real-token",
            "PATH": "safe-path",
        }, clear=True):
            environment = _game_child_environment()

        self.assertEqual(environment, {"PATH": "safe-path"})

    def test_exploration_sectors_prioritize_fogged_map_areas(self) -> None:
        values = [0.0] * (4 * 3 * 5)
        for cell in range(4 * 3):
            values[cell * 5 + 3] = 1.0
        values[4] = 1.0
        sectors = GameRuntime._exploration_sectors(GameSnapshot(
            tick=1,
            map_width=4,
            map_height=3,
            spatial_channels=5,
            spatial_map=struct.pack(f"<{len(values)}f", *values),
        ))

        self.assertEqual(len(sectors), 12)
        self.assertEqual(sectors[0]["explored_percent"], 0.0)
        self.assertEqual(sectors[-1], {"center": [0, 0], "explored_percent": 100.0})

    def test_exploration_sectors_exclude_impassable_cells(self) -> None:
        values = [0.0] * (4 * 3 * 5)
        for cell in range(4 * 3):
            values[cell * 5 + 3] = 1.0
        values[3] = 0.0

        sectors = GameRuntime._exploration_sectors(GameSnapshot(
            tick=1,
            map_width=4,
            map_height=3,
            spatial_channels=5,
            spatial_map=struct.pack(f"<{len(values)}f", *values),
        ))

        self.assertEqual(len(sectors), 11)
        self.assertNotIn({"center": [0, 0], "explored_percent": 0.0}, sectors)

    def test_exploration_sectors_exclude_disconnected_passable_islands(self) -> None:
        values = [0.0] * (4 * 3 * 5)
        values[3] = 1.0
        values[(4 * 3 - 1) * 5 + 3] = 1.0

        sectors = GameRuntime._exploration_sectors(GameSnapshot(
            tick=1,
            map_width=4,
            map_height=3,
            units=(Unit(actor_id=1, kind="e1", cell_x=0, cell_y=0),),
            spatial_channels=5,
            spatial_map=struct.pack(f"<{len(values)}f", *values),
        ))

        self.assertEqual(sectors, [{"center": [0, 0], "explored_percent": 0.0}])

    def test_exploration_targets_return_exact_reachable_hidden_pockets(self) -> None:
        values = [0.0] * (4 * 3 * 5)
        for cell in range(4 * 3):
            values[cell * 5 + 3] = 1.0
            values[cell * 5 + 4] = 1.0
        values[5 * 5 + 4] = 0.0
        values[6 * 5 + 4] = 0.0

        targets = GameRuntime._exploration_targets(GameSnapshot(
            tick=1,
            map_width=4,
            map_height=3,
            units=(Unit(actor_id=1, kind="e1", cell_x=0, cell_y=0),),
            spatial_channels=5,
            spatial_map=struct.pack(f"<{len(values)}f", *values),
        ))

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["hidden_cells"], 2)
        self.assertIn(targets[0]["target"], ([1, 1], [2, 1]))


if __name__ == "__main__":
    unittest.main()
