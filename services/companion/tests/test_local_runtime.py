from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.request
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from openra_ai_companion.local_runtime import (
    GatewayServer,
    RuntimeConfig,
    RuntimeProcesses,
    configure,
    protect_secret,
    unprotect_secret,
)


class _ProviderHandler(BaseHTTPRequestHandler):
    authorization = ""
    requested_path = ""

    def log_message(self, *_args) -> None:
        pass

    def do_POST(self) -> None:
        type(self).authorization = self.headers.get("Authorization", "")
        type(self).requested_path = self.path
        body = json.dumps({"choices": [{"message": {"content": "ready"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LocalRuntimeTests(unittest.TestCase):
    def test_lightweight_runtime_skips_images_and_caps_cpu(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("ai/runtime/llama/llama-server", "ai/runtime/whisper/whisper-server",
                         "ai/models/text.gguf", "ai/models/stt/ggml-base.en.bin"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            runtime = RuntimeProcesses(root, RuntimeConfig(), profile={"model": "models/text.gguf", "projector": None, "context_length": 4096})
            with patch("subprocess.Popen") as process, patch.object(runtime, "_wait_until_ready"), patch("os.cpu_count", return_value=16):
                runtime.start()
                args = process.call_args_list[0].args[0]
            self.assertNotIn("--mmproj", args)
            self.assertEqual(args[args.index("--threads") + 1], "4")
            self.assertEqual(args[args.index("--parallel") + 1], "1")

    def test_secret_round_trip(self) -> None:
        protected = protect_secret("test-secret")
        self.assertNotIn("test-secret", protected)
        self.assertEqual(unprotect_secret(protected), "test-secret")

    def test_configure_writes_provider_and_companion_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APPDATA": directory}):
            key_file = Path(directory) / "key.txt"
            key_file.write_text("secret-value", encoding="utf-8")
            args = Namespace(
                mode="external",
                endpoint="https://example.invalid/v1/",
                key_file=str(key_file),
                text_model="text-model",
                vision_model="vision-model",
                transcribe_model="stt-model",
                speech_model="tts-model",
                speech_voice="nova",
            )
            self.assertEqual(configure(args), 0)
            provider = RuntimeConfig.load(Path(directory) / "OpenRA-AI" / "provider.json")
            self.assertEqual(provider.endpoint, "https://example.invalid/v1")
            self.assertEqual(provider.api_key, "secret-value")
            self.assertFalse(key_file.exists())
            companion = json.loads((Path(directory) / "OpenRA-AI" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(companion["model_provider"], "custom")
            self.assertEqual(companion["text_model"], "text-model")

    def test_installer_ini_is_consumed_without_leaving_plaintext_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APPDATA": directory}):
            input_ini = Path(directory) / "provider.ini"
            input_ini.write_text(
                "[provider]\n"
                "mode=external\n"
                "endpoint=http://127.0.0.1:1234/v1\n"
                "api_key=installer-secret\n"
                "text_model=local-model\n",
                encoding="utf-8",
            )
            args = Namespace(
                mode=None,
                input_ini=str(input_ini),
                endpoint="https://api.openai.com/v1",
                key_file=None,
                text_model="gpt-4.1-mini",
                vision_model="",
                transcribe_model="whisper-1",
                speech_model="gpt-4o-mini-tts",
                speech_voice="alloy",
            )
            self.assertEqual(configure(args), 0)
            self.assertFalse(input_ini.exists())
            stored = (Path(directory) / "OpenRA-AI" / "provider.json").read_text(encoding="utf-8")
            self.assertNotIn("installer-secret", stored)
            self.assertEqual(RuntimeConfig.load().api_key, "installer-secret")

    def test_external_gateway_forwards_provider_key(self) -> None:
        provider = ThreadingHTTPServer(("127.0.0.1", 0), _ProviderHandler)
        provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
        provider_thread.start()
        config = RuntimeConfig(
            mode="external",
            endpoint=f"http://127.0.0.1:{provider.server_port}/v1",
            protected_api_key=protect_secret("provider-key"),
        )
        with tempfile.TemporaryDirectory() as directory:
            gateway = GatewayServer(("127.0.0.1", 0), Path(directory), config)
            gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            gateway_thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{gateway.server_port}/v1/chat/completions",
                    data=b'{"model":"example","messages":[]}',
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(json.loads(response.read())["choices"][0]["message"]["content"], "ready")
                self.assertEqual(_ProviderHandler.authorization, "Bearer provider-key")
                self.assertEqual(_ProviderHandler.requested_path, "/v1/chat/completions")
            finally:
                gateway.shutdown()
                provider.shutdown()
                gateway.server_close()
                provider.server_close()

    def test_local_catalogue_advertises_all_three_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gateway = GatewayServer(("127.0.0.1", 0), Path(directory), RuntimeConfig())
            thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{gateway.server_port}/v1/model/info", timeout=5
                ) as response:
                    models = json.loads(response.read())["data"]
                self.assertEqual(
                    {model["model_info"]["mode"] for model in models},
                    {"chat", "audio_transcription", "audio_speech"},
                )
            finally:
                gateway.shutdown()
                gateway.server_close()


if __name__ == "__main__":
    unittest.main()
