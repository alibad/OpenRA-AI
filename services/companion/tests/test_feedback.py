from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import urllib.request
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openra_ai_companion.core import Companion
from openra_ai_companion.models import GameSnapshot, VisionFrame
from openra_ai_companion.server import create_server


class FeedbackTests(unittest.TestCase):
    def test_feedback_store_round_trip_stays_local(self) -> None:
        from openra_ai_companion.feedback import FeedbackStore

        with TemporaryDirectory() as directory:
            store = FeedbackStore(Path(directory))
            record = store.capture(
                frame_png=b"\x89PNG\r\n\x1a\nframe",
                frame={"tick": 42, "scope": "rendered-player-viewport-fog-respecting"},
                snapshot={"mod_id": "ra2", "tick": 42},
                companion={"enabled": True},
            )
            self.assertEqual(store.screenshot_path(record["feedback_id"]).read_bytes(), b"\x89PNG\r\n\x1a\nframe")
            updated = store.update(record["feedback_id"], {
                "category": "voice",
                "title": "Voice input stopped",
                "description": "The push-to-talk press was not recognized.",
            })
            self.assertEqual(updated["status"], "saved")
            self.assertEqual(store.get(record["feedback_id"])["category"], "voice")
            self.assertTrue((Path(directory) / record["feedback_id"] / "feedback.json").is_file())

    def test_live_capture_route_serves_form_and_screenshot(self) -> None:
        image = b"\x89PNG\r\n\x1a\nlive-frame"
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"OPENRA_AI_FEEDBACK_DIR": directory}):
            companion = Companion()
            companion.latest_snapshot = GameSnapshot(tick=120, map_name="Heartland", mod_id="ra2")
            companion.set_frame_provider(lambda: VisionFrame(image, 120, 640, 360))
            server = create_server("127.0.0.1", 0, companion)
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                capture_request = urllib.request.Request(
                    base + "/v1/feedback/capture", data=b"{}", headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(capture_request, timeout=3) as response:
                    self.assertEqual(response.status, 201)
                    record = json.loads(response.read())
                feedback_id = record["feedback_id"]
                self.assertEqual(record["feedback_url"], f"/feedback/{feedback_id}")

                with urllib.request.urlopen(base + record["feedback_url"], timeout=3) as response:
                    page = response.read()
                self.assertIn(b"Report what happened", page)
                self.assertIn(feedback_id.encode(), page)

                with urllib.request.urlopen(base + record["screenshot_url"], timeout=3) as response:
                    self.assertEqual(response.headers["Content-Type"], "image/png")
                    self.assertEqual(response.read(), image)

                update_request = urllib.request.Request(
                    base + f"/v1/feedback/{feedback_id}",
                    data=json.dumps({
                        "category": "voice",
                        "title": "Voice input missed",
                        "description": "The second press was not recognized.",
                    }).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(update_request, timeout=3) as response:
                    updated = json.loads(response.read())
                self.assertEqual(updated["status"], "saved")
                self.assertEqual(updated["category"], "voice")
            finally:
                server.shutdown()
                server.server_close()
                worker.join()


if __name__ == "__main__":
    unittest.main()
