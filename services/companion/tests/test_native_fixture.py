from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import native_fixture as nf


@dataclass
class Unit:
    kind: str
    actor_id: int
    cell_x: int
    cell_y: int
    idle: bool = False


@dataclass
class Receipt:
    accepted: bool = True

    def as_dict(self):
        return {"accepted": self.accepted}


class Bridge:
    def __init__(self, accept=True):
        self.orders = []
        self.accept = accept

    def execute_actions(self, label, tick, commands):
        self.orders.append((label, tick, [(c.actor_id, c.target_x, c.target_y) for c in commands]))
        return Receipt(self.accept)


def units(*items):
    return {u.kind: u for u in items}


class ExactMoveCheckTests(unittest.TestCase):
    def setUp(self):
        self.bridge = Bridge()
        self.check = nf.ExactMoveCheck("water", {"ship": (30, 115), "sub": (35, 115)}, settle_ticks=50)
        self.check.dispatch(self.bridge, 100, units(Unit("ship", 1, 24, 110), Unit("sub", 2, 25, 111)))

    def test_dispatch_orders_every_actor_to_its_exact_cell(self):
        self.assertEqual([o[2] for o in self.bridge.orders], [[(1, 30, 115)], [(2, 35, 115)]])
        self.assertEqual(self.check.origin, {"ship": (24, 110), "sub": (25, 111)})

    def test_arrival_is_recorded_once_and_survives_native_nudging(self):
        self.assertFalse(self.check.update(self.bridge, 200, units(Unit("ship", 1, 30, 115, True), Unit("sub", 2, 30, 114))))
        # A passing friendly nudges the arrived ship; the arrival remains proven.
        self.assertTrue(self.check.update(self.bridge, 260, units(Unit("ship", 1, 31, 116, True), Unit("sub", 2, 35, 115))))
        summary = self.check.as_dict()
        self.assertEqual(summary["arrival_ticks"], {"ship": 100, "sub": 160})
        self.assertEqual(summary["displaced_after_arrival"], {"ship": [31, 116]})
        self.assertEqual(len(self.bridge.orders), 2)

    def test_unobserved_arrival_repeats_the_same_order_after_settling(self):
        stalled = units(Unit("ship", 1, 31, 116, True), Unit("sub", 2, 28, 113))
        self.check.update(self.bridge, 120, stalled)  # Too early: order may not have started.
        self.assertEqual(len(self.bridge.orders), 2)
        self.check.update(self.bridge, 150, stalled)
        self.assertEqual(self.bridge.orders[-1][2], [(1, 30, 115)])
        self.assertEqual(self.check.as_dict()["repeated_orders"], {"ship": [[50, [31, 116]]]})
        # Arrival after the repeat is still exact-cell native movement.
        self.check.update(self.bridge, 240, units(Unit("ship", 1, 30, 115, True), Unit("sub", 2, 35, 115)))
        self.assertEqual(set(self.check.arrived), {"ship", "sub"})

    def test_a_moving_actor_is_never_reordered(self):
        for tick in range(150, 1000, 50):
            self.check.update(self.bridge, tick, units(Unit("ship", 1, 29, 115), Unit("sub", 2, 28, 113)))
        self.assertEqual(len(self.bridge.orders), 2)

    def test_unreachable_destination_fails_after_bounded_repeats(self):
        with self.assertRaisesRegex(ValueError, "ship stopped at"):
            for tick in range(150, 1000, 50):
                self.check.update(self.bridge, tick, units(Unit("ship", 1, 29, 110, True), Unit("sub", 2, 35, 115)))
        self.assertEqual(len(self.check.reissues["ship"]), 3)

    def test_missing_actor_and_rejected_orders_fail(self):
        with self.assertRaisesRegex(ValueError, "disappeared"):
            self.check.update(self.bridge, 200, units(Unit("ship", 1, 30, 115)))
        with self.assertRaisesRegex(ValueError, "rejected"):
            nf.ExactMoveCheck("x", {"ship": (1, 1)}).dispatch(Bridge(False), 0, units(Unit("ship", 1, 0, 0)))
        with self.assertRaisesRegex(ValueError, "missing"):
            nf.ExactMoveCheck("x", {"ship": (1, 1)}).dispatch(Bridge(), 0, {})

    def test_destinations_must_be_distinct(self):
        with self.assertRaises(ValueError):
            nf.ExactMoveCheck("x", {"a": (1, 1), "b": (1, 1)})


class TickBudgetTests(unittest.TestCase):
    def test_budget_is_game_time_not_wall_time(self):
        budget = nf.TickBudget.from_seconds(140)
        self.assertEqual(budget.ticks, 3500)
        budget.check(3500, "water")
        with self.assertRaisesRegex(nf.BudgetExceeded, "3500 ticks exceeded in water"):
            budget.check(3501, "water")
        self.assertTrue(budget.wall_ok())

    def test_failures_distinguish_hang_guard_from_exit(self):
        budget = nf.TickBudget(100, hang_guard_seconds=0)
        self.assertFalse(budget.wall_ok())
        self.assertIn("Hang guard", budget.failure("water", True))
        self.assertIn("exited", budget.failure("water", False))


class StartupRetryTests(unittest.TestCase):
    def fake_run(self, outcomes):
        calls = []

        def run(resources, binaries, content, output, *extra):
            report = {"passed": outcomes[len(calls)], "extra": list(extra)}
            if not report["passed"] and len(calls) < len(outcomes) - 1:
                nf.startup_failure(report, Path(output) / "missing-profile")
            calls.append(extra)
            (Path(output) / "result.json").write_text(json.dumps(report))
            return report["passed"]

        return run, calls

    def test_only_startup_failures_are_relaunched_and_evidence_is_kept(self):
        with tempfile.TemporaryDirectory() as root:
            run, calls = self.fake_run([False, True])
            self.assertTrue(nf.run_with_startup_retry(run, "r", "b", "c", root, "visual", pause_seconds=0))
            self.assertEqual(len(calls), 2)
            self.assertTrue(json.loads((Path(root) / "result-startup-failure-1.json").read_text())["startup_failure"])
            self.assertEqual(json.loads((Path(root) / "result.json").read_text())["startup_attempts"], 2)

    def test_gameplay_failures_are_not_retried(self):
        with tempfile.TemporaryDirectory() as root:
            run, calls = self.fake_run([False])
            self.assertFalse(nf.run_with_startup_retry(run, "r", "b", "c", root, pause_seconds=0))
            self.assertEqual(len(calls), 1)

    def test_repeated_startup_failure_fails(self):
        with tempfile.TemporaryDirectory() as root:
            calls = []

            def run(resources, binaries, content, output):
                calls.append(1)
                report = {"passed": False}
                nf.startup_failure(report, Path(output))
                (Path(output) / "result.json").write_text(json.dumps(report))
                return False

            self.assertFalse(nf.run_with_startup_retry(run, "r", "b", "c", root, attempts=2, pause_seconds=0))
            self.assertEqual(len(calls), 2)


class LinkDirectoryTests(unittest.TestCase):
    def test_link_exposes_content_and_unlink_preserves_target(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "Content"
            (target / "ra2").mkdir(parents=True)
            (target / "ra2" / "ra2.mix").write_bytes(b"owned")
            link = Path(root) / "profile" / "Content"
            link.parent.mkdir()
            nf.link_directory(link, target)
            self.assertEqual((link / "ra2" / "ra2.mix").read_bytes(), b"owned")
            nf.unlink_directory(link)
            self.assertFalse(link.exists())
            self.assertEqual((target / "ra2" / "ra2.mix").read_bytes(), b"owned")


if __name__ == "__main__":
    unittest.main()
