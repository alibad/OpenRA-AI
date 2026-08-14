from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from openra_ai_companion.cli import main
from openra_ai_companion.voice import microphone_status


class VoiceReadinessTests(unittest.TestCase):
    def test_dependency_only_check_does_not_require_audio_hardware(self) -> None:
        with mock.patch.dict(sys.modules, {"sounddevice": SimpleNamespace()}):
            status = microphone_status(check_device=False)

        self.assertTrue(status["available"])
        self.assertTrue(status["dependency_available"])
        self.assertFalse(status["device_available"])

    def test_missing_capture_dependency_is_reported_precisely(self) -> None:
        with mock.patch.dict(sys.modules, {"sounddevice": None}):
            status = microphone_status(check_device=False)

        self.assertFalse(status["available"])
        self.assertFalse(status["dependency_available"])
        self.assertIn("dependency is missing", str(status["reason"]))

    def test_voice_check_command_is_machine_readable(self) -> None:
        expected = {
            "available": True,
            "dependency_available": True,
            "device_available": False,
            "device_name": "",
            "reason": "",
        }
        output = io.StringIO()
        with (
            mock.patch("openra_ai_companion.cli.microphone_status", return_value=expected) as status,
            contextlib.redirect_stdout(output),
        ):
            result = main(["voice-check", "--dependencies-only"])

        self.assertEqual(result, 0)
        status.assert_called_once_with(check_device=False)
        self.assertEqual(json.loads(output.getvalue()), expected)


if __name__ == "__main__":
    unittest.main()
