"""The RTS AI mod's sidecar contract: data/log locations, the single-executable gateway and AI pack installs."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from openra_ai_companion import pack_cli


def _lock(root: Path, files: dict[str, bytes]) -> Path:
    components = []
    for index, (name, payload) in enumerate(files.items()):
        components.append({
            "id": name,
            "url": f"https://example.invalid/{name}.bin",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "destination": f"models/{name}.bin",
        })
    ids = list(files)
    lock = root / "ai-pack.lock.json"
    lock.write_text(json.dumps({
        "schema_version": 1,
        "pack_version": "test.2",
        "name": "Test pack",
        "model_profiles": [
            {"id": "voice-only", "label": "Voice", "brain": "hosted", "validated": True, "priority": 0,
             "memory_bytes": 1, "prefers_acceleration": False, "context_length": None, "model": None,
             "projector": None, "components": ids[1:]},
            {"id": "recommended", "label": "Full", "validated": True, "priority": 20, "memory_bytes": 1,
             "prefers_acceleration": False, "context_length": 8192, "model": f"models/{ids[0]}.bin",
             "projector": None, "components": ids},
        ],
        "components": components,
    }), encoding="utf-8")
    return lock


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class DataDirectoryTests(unittest.TestCase):
    def test_mod_data_dir_holds_settings_provider_and_feedback(self) -> None:
        from openra_ai_companion import brain, feedback, learning, local_runtime, settings

        with tempfile.TemporaryDirectory() as directory, patch.dict(
                os.environ, {"OPENRA_AI_DATA_DIR": directory, "APPDATA": str(Path(directory) / "appdata")}):
            os.environ.pop("OPENRA_AI_BRAIN_STATE", None)
            os.environ.pop("OPENRA_AI_LEARNING_DIR", None)
            self.assertEqual(brain.default_blackboard_path(), Path(directory).resolve() / "runtime" / "brain-blackboard.jsonl")
            self.assertEqual(learning.default_learning_dir(), Path(directory).resolve() / "learning")
            self.assertEqual(settings.user_settings_path(), Path(directory) / "settings.json")
            self.assertEqual(local_runtime.provider_config_path(), Path(directory) / "provider.json")
            self.assertEqual(feedback.default_feedback_dir(), Path(directory).resolve() / "Feedback")
            local_runtime.RuntimeConfig(mode="hosted").save()
            self.assertTrue((Path(directory) / "provider.json").is_file())
            self.assertFalse((Path(directory) / "appdata").exists())

    def test_appdata_location_is_unchanged_without_override(self) -> None:
        from openra_ai_companion import settings

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APPDATA": directory}):
            os.environ.pop("OPENRA_AI_DATA_DIR", None)
            self.assertEqual(settings.user_settings_path(), Path(directory) / "OpenRA-AI" / "settings.json")


class GatewayCommandTests(unittest.TestCase):
    def test_gateway_runs_from_the_companion_executable_and_logs_to_the_support_dir(self) -> None:
        from openra_ai_companion.core import Companion
        from openra_ai_companion.model_setup import LocalAIManager
        from openra_ai_companion.router import AIRouter
        from openra_ai_companion.settings import Settings

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "rtsai-companion.exe"
            executable.write_text("stub", encoding="utf-8")
            logs = root / "Logs"
            companion = Companion(router=AIRouter(Settings(model_provider="hosted", text_model="claude-haiku-4-5",
                                                           vision_model="claude-haiku-4-5")))
            manager = LocalAIManager(companion, install_root=root, runtime_executable=executable, auto_start=False)
            started: dict = {}

            class _Process:
                def poll(self):
                    return None

                def terminate(self):
                    pass

                def wait(self, timeout=None):
                    return 0

            def popen(command, **kwargs):
                started["command"] = command
                started["stdout"] = kwargs["stdout"].name
                return _Process()

            reachable = iter([False, True, True, True])
            with patch.dict(os.environ, {"OPENRA_AI_RUNTIME_SUBCOMMAND": "runtime", "OPENRA_AI_LOG_DIR": str(logs)}), \
                    patch("openra_ai_companion.model_setup.subprocess.Popen", side_effect=popen), \
                    patch("openra_ai_companion.model_setup._reachable", side_effect=lambda *_a, **_k: next(reachable)):
                manager._start_runtime()
            manager.stop()
            self.assertEqual(started["command"][:3], [str(executable), "runtime", "serve"])
            self.assertIn("--mode", started["command"])
            self.assertEqual(started["command"][started["command"].index("--mode") + 1], "hosted")
            self.assertEqual(Path(started["stdout"]), logs / "ai-runtime.out.log")

    def test_hosted_first_launch_fetches_a_missing_voice_pack_when_asked(self) -> None:
        from openra_ai_companion.core import Companion
        from openra_ai_companion.model_setup import LocalAIManager
        from openra_ai_companion.router import AIRouter
        from openra_ai_companion.settings import Settings

        calls: list[str] = []
        companion = Companion(router=AIRouter(Settings(model_provider="hosted")))
        with patch.object(LocalAIManager, "supported", new=True), \
                patch.object(LocalAIManager, "installed", new=False), \
                patch.object(LocalAIManager, "gateway_supported", new=True), \
                patch.object(LocalAIManager, "_start_runtime_safely", lambda self: calls.append("gateway")), \
                patch.object(LocalAIManager, "install", lambda self: calls.append("install") or {}), \
                patch.dict(os.environ, {"OPENRA_AI_AUTO_INSTALL_VOICE": "1"}):
            manager = LocalAIManager(companion, auto_start=True)
            deadline = 50
            while "install" not in calls and deadline:
                import time
                time.sleep(0.02)
                deadline -= 1
        manager.stop()
        self.assertEqual(calls, ["gateway", "install"])


class PackInstallTests(unittest.TestCase):
    def test_install_downloads_verifies_and_writes_a_receipt_the_companion_accepts(self) -> None:
        files = {"brain": b"brain-model", "stt": b"whisper-model", "tts": b"kokoro-model"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = _lock(root, files)
            output = io.StringIO()
            responses = iter([_Response(files["stt"]), _Response(files["tts"])])
            with patch("urllib.request.urlopen", side_effect=lambda *_a, **_k: next(responses)):
                receipt = pack_cli.install(root / "companion", lock, "voice-only", stream=output)
            self.assertEqual(receipt["pack_version"], "test.2")
            self.assertEqual(sorted(entry["id"] for entry in receipt["components"]), ["stt", "tts"])
            self.assertEqual((root / "companion/ai/models/stt.bin").read_bytes(), files["stt"])
            self.assertFalse((root / "companion/ai/models/brain.bin").exists())
            self.assertIn("100%", output.getvalue())
            status = pack_cli.status(root / "companion", lock, "voice-only")
            self.assertTrue(status["installed"])
            self.assertFalse(pack_cli.status(root / "companion", lock, "recommended")["installed"])

    def test_a_tampered_download_is_rejected_and_never_installed(self) -> None:
        files = {"brain": b"brain-model", "stt": b"whisper-model", "tts": b"kokoro-model"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = _lock(root, files)
            with patch("urllib.request.urlopen", return_value=_Response(b"whisper-mode!")), \
                    self.assertRaises(pack_cli.PackInstallError):
                pack_cli.install(root / "companion", lock, "voice-only", stream=io.StringIO())
            self.assertFalse((root / "companion/ai/models/stt.bin").exists())
            self.assertFalse((root / "companion/ai/pack.json").exists())

    def test_offline_archive_and_local_copies_are_verified_before_use(self) -> None:
        files = {"brain": b"brain-model", "stt": b"whisper-model", "tts": b"kokoro-model"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = _lock(root, files)
            archive = root / "voice.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("models/stt.bin", files["stt"])
                bundle.writestr("models/tts.bin", b"tampered")
            local = root / "local-ai"
            (local / "models").mkdir(parents=True)
            (local / "models/tts.bin").write_bytes(files["tts"])
            with patch("urllib.request.urlopen", side_effect=AssertionError("no download expected")):
                pack_cli.install(root / "companion", lock, "voice-only", archive=archive, from_dir=local,
                                 stream=io.StringIO())
            self.assertEqual((root / "companion/ai/models/tts.bin").read_bytes(), files["tts"])
            self.assertEqual((root / "companion/ai/models/stt.bin").read_bytes(), files["stt"])

    def test_the_command_line_reports_failure_with_a_nonzero_exit(self) -> None:
        files = {"brain": b"brain-model", "stt": b"whisper-model", "tts": b"kokoro-model"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = _lock(root, files)
            with patch("urllib.request.urlopen", side_effect=OSError("offline")), \
                    patch("sys.stdout", new=io.StringIO()), patch("sys.stderr", new=io.StringIO()):
                code = pack_cli.main(["install", "--profile", "voice", "--root", str(root / "c"), "--lock", str(lock)])
            self.assertEqual(code, 2)

    def test_the_real_lock_resolves_the_installer_profiles(self) -> None:
        lock = Path(__file__).resolve().parents[3] / "packaging" / "ai-pack.lock.json"
        manifest = pack_cli.load_manifest(lock)
        voice = pack_cli.resolve_profile(manifest, "voice-only")
        full = pack_cli.resolve_profile(manifest, "full")
        from openra_ai_companion.model_selection import selected_components
        voice_bytes = sum(c["bytes"] for c in selected_components(manifest, voice))
        full_bytes = sum(c["bytes"] for c in selected_components(manifest, full))
        self.assertEqual(voice_bytes, 268_539_880)
        self.assertGreater(full_bytes, 1_700_000_000)


if __name__ == "__main__":
    unittest.main()
