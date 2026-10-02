"""Model-free regression gate for the natural-language order evaluation.

The full evaluation needs a model router (``nl_orders/run_eval.py``).  This
gate runs every case through the real Companion with an unreachable router,
so it only credits the deterministic fast path, grounding, refusals and the
grader itself.  It must never produce an unsafe proposal or a malformed reply.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent / "nl_orders"
sys.path.insert(0, str(HERE))

from cases import cases  # noqa: E402
from grade import grade, load_fixture, summarize  # noqa: E402

from openra_ai_companion.core import Companion  # noqa: E402
from openra_ai_companion.router import AIRouter, RouterError  # noqa: E402
from openra_ai_companion.settings import Settings  # noqa: E402


class _OfflineRouter(AIRouter):
    def _request(self, path, body, content_type):  # noqa: ANN001
        raise RouterError("offline evaluation")


class NaturalLanguageOrderEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = cases()
        cls.outcomes = []
        settings = Settings(router_url="http://127.0.0.1:9", vision_model="local-no-vision", voice_enabled=False)
        for case in cls.cases:
            snapshot, _ = load_fixture(case["fixture"])
            companion = Companion(router=_OfflineRouter(settings))
            companion.goal_blackboard.journal_path = None
            companion.update_snapshot(snapshot)
            response = companion.handle_player_input(case["utterance"])
            cls.outcomes.append({
                "id": case["id"],
                "text": response.text,
                "source": response.source,
                "interrupted": response.interrupted,
                "metadata": json.loads(json.dumps(response.metadata, default=str)),
                "pending_after": companion.pending_action() is not None,
                "model_called": False,
            })
        cls.graded = [grade(case, outcome) for case, outcome in zip(cls.cases, cls.outcomes)]
        cls.summary = summarize(cls.cases, cls.graded, cls.outcomes)

    def test_corpus_covers_the_order_surface(self) -> None:
        self.assertGreaterEqual(len(self.cases), 150)
        actions = {
            spec["action"]
            for case in self.cases if case["expect"]["outcome"] == "proposal"
            for spec in case["expect"]["commands"]
        }
        for action in ("train", "build", "place_building", "deploy", "move", "attack_move", "attack", "stop",
                       "harvest", "repair", "sell", "set_rally_point", "guard", "set_stance", "enter_transport",
                       "unload", "capture", "infiltrate", "disguise", "demolish", "set_primary", "power_down",
                       "cancel_production"):
            self.assertIn(action, actions)
        self.assertTrue(any(case["fixture"].startswith("ra2-") for case in self.cases))
        self.assertTrue(all(load_fixture(case["fixture"])[1]["captured"]["source"].startswith("live") for case in self.cases))

    def test_deterministic_path_never_accepts_unsafe_or_malformed_output(self) -> None:
        self.assertEqual(self.summary["unsafe_accepts"], 0, self.summary)
        self.assertEqual(self.summary["malformed_replies"], 0, self.summary)

    def test_deterministic_path_handles_most_explicit_orders(self) -> None:
        # Relative directions, pronouns and vague requests intentionally need
        # the model; everything else must be grounded without one.
        self.assertGreaterEqual(self.summary["executable_pass_rate"], 90.0, self.summary)

    def test_known_build_then_place_failure_stays_fixed(self) -> None:
        by_utterance = {(case["fixture"], case["utterance"]): entry for case, entry in zip(self.cases, self.graded)}
        for key in (
            ("ra-england-base-empty", "build a power plant"),
            ("ra-england-power-queued", "build a power plant"),
            ("ra-england-power-ready", "place the power plant"),
            ("ra-china-power-ready", "build a power plant"),
        ):
            self.assertTrue(by_utterance[key]["passed"], by_utterance[key])


if __name__ == "__main__":
    unittest.main()
