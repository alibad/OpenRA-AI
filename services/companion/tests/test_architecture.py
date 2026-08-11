from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openra_ai_companion.brain import BrainOwner, GoalBlackboard, GoalStatus
from openra_ai_companion.bridge import ACTION_TYPES
from openra_ai_companion.controller import TacticalController
from openra_ai_companion.core import Companion
from openra_ai_companion.learning import LearningStore
from openra_ai_companion.mission_goals import compile_mission_goal_graph
from openra_ai_companion.models import ActionCommand, ActionProposal, GameSnapshot
from openra_ai_companion.strategy import mission_plan
from openra_ai_companion.strategy_contracts import compile_strategy_program


def snapshot(**changes: object) -> GameSnapshot:
    value = {
        "tick": 100,
        "map_info": {"map_name": "Architecture Test", "width": 64, "height": 64},
        "units": [],
        "buildings": [{"actor_id": 100, "type": "fact", "cell_x": 5, "cell_y": 5}],
        "visible_enemies": [],
        "visible_enemy_buildings": [],
    }
    value.update(changes)
    return GameSnapshot.from_dict(value)


class BrainArchitectureTests(unittest.TestCase):
    def test_strategy_program_is_map_scaled_and_bounded(self) -> None:
        program = compile_strategy_program("rush", snapshot(map_info={"map_name": "Large", "width": 160, "height": 160}))

        self.assertEqual(program.profile, "rush")
        self.assertEqual(program.scout_count, 4)
        self.assertGreaterEqual(program.target_harvesters, 5)
        self.assertLessEqual(program.aggression, 1)

    def test_mission_objectives_compile_to_reusable_goal_primitives(self) -> None:
        current = snapshot(
            mission_mode=True,
            mission_briefing="Capture the command center and escape.",
            objectives=[
                {"id": 1, "description": "Capture the command center", "state": "incomplete", "required": True},
                {"id": 2, "description": "Reach the extraction zone", "state": "incomplete", "required": True},
            ],
            units=[{
                "actor_id": 7,
                "type": "engi",
                "can_capture": True,
                "valid_capture_targets": [50],
            }],
            visible_enemy_buildings=[{"actor_id": 50, "type": "atek", "cell_x": 30, "cell_y": 30}],
        )

        graph = compile_mission_goal_graph(current)

        self.assertEqual([node["primitive"] for node in graph["nodes"]], ["capture", "extract"])
        self.assertEqual(graph["ready"], ["objective-1"])
        self.assertEqual(graph["nodes"][0]["legal_target_ids"], [50])

    def test_fast_controller_prioritizes_spy_escape(self) -> None:
        current = snapshot(
            units=[{"actor_id": 1, "type": "spy", "cell_x": 20, "cell_y": 20, "hp_percent": 1}],
            visible_enemies=[{
                "actor_id": 9,
                "type": "dog",
                "cell_x": 22,
                "cell_y": 20,
                "hp_percent": 1,
                "detects_disguise": True,
            }],
        )

        decision = TacticalController().decide(current)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.key, "spy-dog-escape")
        self.assertEqual(decision.owner, "safety")
        self.assertEqual(decision.commands[0].actor_id, 1)

    def test_fast_controller_does_not_repeat_an_active_retreat(self) -> None:
        controller = TacticalController()
        current = snapshot(units=[{
            "actor_id": 2,
            "type": "1tnk",
            "cell_x": 20,
            "cell_y": 20,
            "hp_percent": 0.2,
            "can_attack": True,
            "idle": True,
        }])

        first = controller.decide(current)
        repeated = controller.decide(snapshot(
            tick=200,
            units=[{
                "actor_id": 2,
                "type": "1tnk",
                "cell_x": 18,
                "cell_y": 18,
                "hp_percent": 0.2,
                "can_attack": True,
                "idle": False,
                "move_target_x": 5,
                "move_target_y": 5,
            }],
        ))

        self.assertEqual(first.key, "retreat-damaged-armor")
        self.assertIsNone(repeated)

    def test_fast_controller_focuses_aircraft_with_real_anti_air(self) -> None:
        current = snapshot(
            units=[{
                "actor_id": 2,
                "type": "e3",
                "cell_x": 10,
                "cell_y": 10,
                "hp_percent": 1,
                "can_attack": True,
                "can_target_air": True,
            }],
            visible_enemies=[{
                "actor_id": 8,
                "type": "yak",
                "cell_x": 13,
                "cell_y": 10,
                "hp_percent": 1,
                "can_attack": True,
            }],
        )

        decision = TacticalController().decide(current)

        self.assertEqual(decision.key, "intercept-aircraft")
        self.assertEqual(decision.commands[0], ActionCommand("attack", actor_id=2, target_actor_id=8))

    def test_mission_exploration_does_not_loop_on_a_visible_wall(self) -> None:
        current = snapshot(
            mission_mode=True,
            mission_briefing="Find Einstein. Destroy the westmost power plant with Tanya.",
            objectives=[{
                "id": 1,
                "description": "Find Einstein.",
                "state": "incomplete",
                "required": True,
            }],
            units=[{
                "actor_id": 2,
                "type": "e1",
                "cell_x": 10,
                "cell_y": 10,
                "hp_percent": 1,
                "can_attack": True,
                "idle": True,
            }],
            visible_enemy_buildings=[
                {"actor_id": 8, "type": "fenc", "cell_x": 11, "cell_y": 10, "hp_percent": 1},
                {"actor_id": 9, "type": "powr", "cell_x": 20, "cell_y": 20, "hp_percent": 1},
            ],
        )

        plan = mission_plan(current)

        self.assertEqual(plan["phase"], "clear-objective-route")
        self.assertEqual(plan["recommended_commands"][0]["target_x"], 20)
        self.assertEqual(plan["recommended_commands"][0]["target_y"], 20)

    def test_mission_boards_einstein_into_scripted_extraction_transport(self) -> None:
        current = snapshot(
            mission_mode=True,
            objectives=[{
                "id": 4,
                "description": "Wait for the helicopter and extract Einstein.",
                "state": "incomplete",
                "required": True,
            }],
            units=[
                {"actor_id": 10, "type": "einstein", "cell_x": 20, "cell_y": 20, "hp_percent": 1, "idle": True},
                {
                    "actor_id": 11,
                    "type": "tran.extraction",
                    "cell_x": 15,
                    "cell_y": 15,
                    "hp_percent": 1,
                    "idle": True,
                    "passenger_count": -1,
                },
            ],
        )

        plan = mission_plan(current)

        self.assertEqual(plan["phase"], "extract-required-evacuee")
        self.assertEqual(
            plan["recommended_commands"],
            [{"action": "enter_transport", "actor_id": 10, "target_actor_id": 11}],
        )

    def test_support_power_requires_ready_state_and_friendly_fire_clearance(self) -> None:
        current = snapshot(
            units=[{"actor_id": 1, "type": "e1", "cell_x": 5, "cell_y": 5}],
            visible_enemy_buildings=[{"actor_id": 50, "type": "weap", "cell_x": 51, "cell_y": 50}],
            support_powers=[{
                "key": "NukePowerInfoOrder",
                "name": "Atom Bomb",
                "active": True,
                "ready": True,
            }],
        )
        command = {"action": "use_support_power", "item_type": "NukePowerInfoOrder", "target_x": 50, "target_y": 50}

        commands = Companion._validate_action_commands(current, [command])
        self.assertEqual(commands[0].action, "use_support_power")
        self.assertIn("use_support_power", ACTION_TYPES)

        unsafe = snapshot(
            units=[{"actor_id": 1, "type": "e1", "cell_x": 50, "cell_y": 50}],
            visible_enemy_buildings=[{"actor_id": 50, "type": "weap", "cell_x": 51, "cell_y": 50}],
            support_powers=current.support_powers,
        )
        with self.assertRaisesRegex(ValueError, "friendly-fire"):
            Companion._validate_action_commands(unsafe, [command])

    def test_goal_journal_survives_process_restart_without_replaying_orders(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "brain.jsonl"
            board = GoalBlackboard(journal_path=path)
            proposal = ActionProposal(
                proposal_id="durable-1",
                instruction="mission:auto-step",
                summary="Advance",
                expected_tick=100,
                commands=(ActionCommand("move", actor_id=1, target_x=20, target_y=20),),
                created_at=time.monotonic(),
            )
            goal = board.register(proposal, snapshot(units=[{"actor_id": 1, "type": "e1"}]), BrainOwner.MISSION, automatic=True)
            board.mark_dispatched(proposal.proposal_id, 100)

            restored = GoalBlackboard(journal_path=path)
            restored_goal = next(item for item in restored._goals.values() if item.goal_id == goal.goal_id)

            self.assertEqual(restored_goal.status, GoalStatus.FAILED)
            self.assertIn("restarted", restored_goal.last_error)
            self.assertIsNone(restored.next_retry())

    def test_learning_policy_promotes_only_after_verified_gates(self) -> None:
        with TemporaryDirectory() as directory:
            store = LearningStore(Path(directory))
            records = [
                {"attempt_id": f"base-{index}", "policy_id": "baseline", "won": index == 0, "safety_violations": 0}
                for index in range(3)
            ] + [
                {"attempt_id": f"candidate-{index}", "policy_id": "cohesive-v2", "won": True, "safety_violations": 0}
                for index in range(3)
            ]
            store.root.mkdir(parents=True, exist_ok=True)
            store.history_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
            )
            store.propose_policy("cohesive-v2", {"attack_squad_size": 10}, baseline_id="baseline")

            evaluation = store.evaluate_policy("cohesive-v2")

            self.assertTrue(evaluation["passed"])
            self.assertEqual(store.policies()["active_policy"], "cohesive-v2")


if __name__ == "__main__":
    unittest.main()
