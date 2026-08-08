from __future__ import annotations

import threading
import time
import unittest
import urllib.request
import wave
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest import mock

from openra_ai_companion.cli import _speak
from openra_ai_companion.core import Companion
from openra_ai_companion.hotkeys import VoiceHotkeys
from openra_ai_companion.insights import InsightEngine
from openra_ai_companion.models import GameSnapshot
from openra_ai_companion.router import AIRouter, RouterError, RouterResult
from openra_ai_companion.server import create_server
from openra_ai_companion.settings import Settings
from openra_ai_companion.voice import _normalize_wav, _wav_bytes


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

    def transcribe(self, audio, filename="question.wav"):  # noqa: ANN001
        return RouterResult("Where is the threat?", 4, "fake-transcribe")

    def speech(self, text):  # noqa: ANN001
        return b"RIFFfake", 5, "audio/wav"


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

    def test_changed_situation_gets_a_periodic_update(self) -> None:
        companion = Companion(router=FakeRouter(), insights=InsightEngine(situation_interval_ticks=250))
        self.assertIsNone(companion.observe(snapshot(tick=1000)))
        response = companion.observe(snapshot(
            tick=1250,
            production=[{"item": "1tnk", "progress": 0.9, "remaining_ticks": 80}],
        ))
        self.assertIsNotNone(response)
        self.assertEqual(response.insight.key, "situation_update")
        self.assertIn("active production: 1tnk", response.insight.fact)

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
        self.assertEqual(current["visible_enemy_buildings"], ["tsla"])
        self.assertEqual(current["remembered_enemy_buildings"][0]["type"], "weap")

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

    def test_resolved_economy_warning_is_replaced_immediately(self) -> None:
        companion = Companion(router=FakeRouter())
        warning = companion.observe(snapshot(tick=1000, harvester_count=0))
        self.assertEqual(warning.insight.key, "no_harvester")
        recovered = companion.observe(snapshot(
            tick=1010,
            harvester_count=1,
            units=[{"actor_id": 12, "type": "harv"}],
            production=[],
        ))
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.insight.key, "economy_recovered")

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
                self.assertIn(b"Companion Console", response.read())
            request = urllib.request.Request(base + "/v1/test/full", data=b"{}", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = response.read()
            self.assertIn(b'"ok": true', payload)
            self.assertEqual(player.audio, b"RIFFfake")
            request = urllib.request.Request(
                base + "/v1/control",
                data=b'{"muted":true}',
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = response.read()
            self.assertIn(b'"muted": true', payload)
            self.assertEqual(player.audio, b"")
            self.assertEqual(statuses[-1], ("muted", "AI VOICE OFF  •  TEXT INSIGHTS STAY ON"))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
