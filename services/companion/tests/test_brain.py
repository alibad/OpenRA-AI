from __future__ import annotations

import time
import unittest

from openra_ai_companion.brain import BrainArbiter, BrainOwner, GoalBlackboard, GoalStatus
from openra_ai_companion.models import ActionCommand, ActionProposal, ActionReceipt, GameSnapshot


def snapshot(**changes: object) -> GameSnapshot:
    value = {
        "tick": 100,
        "map_info": {"map_name": "Brain Test", "width": 64, "height": 64},
        "production": [],
        "units": [],
        "buildings": [{"actor_id": 1, "type": "fact", "cell_x": 10, "cell_y": 10}],
    }
    value.update(changes)
    return GameSnapshot.from_dict(value)


def proposal(*commands: ActionCommand, instruction: str = "mission:auto-step") -> ActionProposal:
    return ActionProposal(
        proposal_id="proposal-1",
        instruction=instruction,
        summary="Place the completed structure",
        expected_tick=100,
        commands=commands,
        created_at=time.monotonic(),
    )


class GoalBlackboardTests(unittest.TestCase):
    def test_completed_structure_stays_active_until_snapshot_verifies_placement(self) -> None:
        board = GoalBlackboard()
        before = snapshot(production=[{"queue_type": "Building", "item": "silo", "progress": 1.0}])
        action = proposal(ActionCommand("place_building", item_type="silo"))

        goal = board.register(action, before, BrainOwner.MISSION, automatic=True)
        board.mark_dispatched(action.proposal_id, before.tick)
        board.apply_receipt(ActionReceipt(action.proposal_id, True, before.tick, "queued"))

        self.assertEqual(goal.status, GoalStatus.VERIFYING)
        self.assertEqual(board.reconcile(before), [])

        after = snapshot(
            tick=110,
            production=[],
            buildings=[
                {"actor_id": 1, "type": "fact", "cell_x": 10, "cell_y": 10},
                {"actor_id": 2, "type": "silo", "cell_x": 13, "cell_y": 10},
            ],
        )
        changed = board.reconcile(after)

        self.assertEqual(changed[0].status, GoalStatus.SUCCEEDED)
        self.assertTrue(changed[0].verification[0]["satisfied"])

    def test_automatic_goal_retries_when_no_effect_is_observed(self) -> None:
        board = GoalBlackboard(verify_timeout_ticks=25, max_attempts=2)
        before = snapshot(production=[{"queue_type": "Building", "item": "silo", "progress": 1.0}])
        action = proposal(ActionCommand("place_building", item_type="silo"))
        goal = board.register(action, before, BrainOwner.MISSION, automatic=True)
        board.mark_dispatched(action.proposal_id, before.tick)
        board.apply_receipt(ActionReceipt(action.proposal_id, True, before.tick, "queued"))

        board.reconcile(snapshot(
            tick=126,
            production=[{"queue_type": "Building", "item": "silo", "progress": 1.0}],
        ))

        self.assertEqual(goal.status, GoalStatus.RETRY_READY)
        self.assertEqual(board.next_retry(), goal)

    def test_manual_goal_fails_instead_of_retrying_automatically(self) -> None:
        board = GoalBlackboard(verify_timeout_ticks=25)
        before = snapshot(units=[{"actor_id": 3, "type": "e1", "is_idle": True}])
        action = proposal(ActionCommand("move", actor_id=3, target_x=20, target_y=20), instruction="Move the infantry")
        goal = board.register(action, before, BrainOwner.USER, automatic=False)
        board.mark_dispatched(action.proposal_id, before.tick)
        board.apply_receipt(ActionReceipt(action.proposal_id, True, before.tick, "queued"))

        board.reconcile(snapshot(tick=126, units=[{"actor_id": 3, "type": "e1", "is_idle": True}]))

        self.assertEqual(goal.status, GoalStatus.FAILED)
        self.assertIsNone(board.next_retry())

    def test_user_lease_preempts_native_and_cannot_be_stolen(self) -> None:
        arbiter = BrainArbiter()

        self.assertTrue(arbiter.claim("combat", BrainOwner.NATIVE, 100, ttl_ticks=100, reason="native squad"))
        self.assertTrue(arbiter.claim("combat", BrainOwner.USER, 101, ttl_ticks=100, reason="player order"))
        self.assertFalse(arbiter.claim("combat", BrainOwner.NATIVE, 102, ttl_ticks=100, reason="native retry"))
        self.assertEqual(arbiter.state(102)[0]["owner"], "user")


if __name__ == "__main__":
    unittest.main()
