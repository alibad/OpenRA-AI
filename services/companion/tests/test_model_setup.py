from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from openra_ai_companion.core import Companion
from openra_ai_companion.model_setup import LocalAIManager
from openra_ai_companion.server import create_server


class _Download(BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class _TestManager(LocalAIManager):
    def _start_runtime(self) -> None:
        self._configure_local_route()
        with self._lock:
            self._state = "running"
            self._detail = "Local AI is installed and ready. Voice stays on this Mac."


class LocalAIManagerTests(unittest.TestCase):
    def test_setup_downloads_verifies_and_activates_the_local_pack(self) -> None:
        payload = b"pinned-model-payload"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / "ai-pack.lock.json"
            lock.write_text(json.dumps({
                "schema_version": 1,
                "pack_version": "test.1",
                "name": "Test Local AI Pack",
                "components": [{
                    "id": "test-model",
                    "url": "https://example.invalid/test-model.bin",
                    "sha256": digest,
                    "bytes": len(payload),
                    "destination": "models/test/model.bin",
                }],
            }), encoding="utf-8")
            runtime = root / "openra-ai-runtime"
            runtime.write_text("runtime", encoding="utf-8")
            runtime_root = root / "runtime"
            (runtime_root / "llama").mkdir(parents=True)
            (runtime_root / "whisper").mkdir()
            (runtime_root / "llama" / "llama-server").write_text("llama", encoding="utf-8")
            (runtime_root / "whisper" / "whisper-server").write_text("whisper", encoding="utf-8")
            companion = Companion()
            manager = _TestManager(
                companion,
                lock_path=lock,
                install_root=root / "data",
                runtime_executable=runtime,
                runtime_root=runtime_root,
                auto_start=False,
            )

            with patch("urllib.request.urlopen", return_value=_Download(payload)), \
                    patch("openra_ai_companion.model_setup._reachable", return_value=True):
                self.assertEqual(manager.install()["state"], "installing")
                deadline = time.monotonic() + 5
                while manager.status()["state"] in {"installing", "ready", "starting"} and time.monotonic() < deadline:
                    time.sleep(0.01)
                status = manager.status()
            self.assertEqual(status["state"], "running")
            self.assertEqual(status["progress_percent"], 100)
            self.assertTrue(status["installed"])
            self.assertEqual(
                (root / "data" / "ai" / "models" / "test" / "model.bin").read_bytes(),
                payload,
            )
            self.assertEqual(companion.router.settings.model_provider, "local")
            self.assertEqual(companion.router.settings.router_url, "http://127.0.0.1:4000")

    def test_setup_is_truthfully_unsupported_without_bundled_runtime(self) -> None:
        companion = Companion()
        with patch.dict("os.environ", {}, clear=True):
            manager = LocalAIManager(companion, auto_start=False)
        status = manager.status()
        self.assertFalse(status["supported"])
        self.assertEqual(status["state"], "unsupported")

    def test_companion_exposes_setup_status_and_install_action(self) -> None:
        class Manager:
            def __init__(self):
                self.started = False

            def status(self):
                return {"supported": True, "installed": False, "state": "not_installed"}

            def install(self):
                self.started = True
                return {"supported": True, "installed": False, "state": "installing"}

            retry = install

        manager = Manager()
        server = create_server("127.0.0.1", 0, Companion())
        server.local_ai_manager = manager
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(base + "/v1/local-ai", timeout=3) as response:
                self.assertEqual(json.loads(response.read())["state"], "not_installed")
            request = urllib.request.Request(base + "/v1/local-ai/install", data=b"{}")
            with urllib.request.urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 202)
                self.assertEqual(json.loads(response.read())["state"], "installing")
            self.assertTrue(manager.started)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
