from __future__ import annotations

import threading
import time
import unittest
import wave
from io import BytesIO

from openra_ai_companion.core import Companion
from openra_ai_companion.models import GameSnapshot
from openra_ai_companion.router import RouterResult
from openra_ai_companion.voice import _wav_bytes


class FakeRouter:
    def __init__(self, delay: float = 0):
        self.delay = delay
        self.calls = 0

    def chat(self, messages, temperature=0.2):  # noqa: ANN001
        self.calls += 1
        time.sleep(self.delay)
        return RouterResult("Enemy armor is entering from the east.", round(self.delay * 1000), "fake")

    def health(self):
        return {"reachable": True, "url": "fake://router"}

    def transcribe(self, audio, filename="question.wav"):  # noqa: ANN001
        return RouterResult("Where is the threat?", 4, "fake-transcribe")

    def speech(self, text):  # noqa: ANN001
        return b"RIFFfake", 5, "audio/wav"


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


class CompanionTests(unittest.TestCase):
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
        response = companion.observe(snapshot(power_provided=50, power_drained=125))
        self.assertEqual(response.insight.key, "low_power")
        companion.configure(muted=True)
        audio, metadata = companion.speech("test")
        self.assertEqual(audio, b"")
        self.assertTrue(metadata["disabled"])

    def test_voice_routes_share_same_router(self) -> None:
        companion = Companion(router=FakeRouter())
        self.assertEqual(companion.transcribe(b"audio").text, "Where is the threat?")
        audio, metadata = companion.speech("Hold the center")
        self.assertEqual(audio, b"RIFFfake")
        self.assertFalse(metadata["interrupted"])

    def test_push_to_talk_frames_are_packaged_as_mono_wav(self) -> None:
        audio = _wav_bytes([b"\x00\x00" * 160], 16_000)
        self.assertTrue(audio.startswith(b"RIFF"))
        with wave.open(BytesIO(audio), "rb") as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getframerate(), 16_000)
            self.assertEqual(wav.getnframes(), 160)


if __name__ == "__main__":
    unittest.main()
