from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

from openra_ai_companion import local_runtime, model_setup
from openra_ai_companion.agent_models import create_agent_model
from openra_ai_companion.core import HOSTED_SPOKEN, Companion
from openra_ai_companion.interactive_agent import InteractiveMCPPlanner
from openra_ai_companion.local_runtime import GatewayServer, RuntimeConfig, configure, protect_secret, runtime_config_for
from openra_ai_companion.model_setup import LocalAIManager
from openra_ai_companion.models import GameSnapshot
from openra_ai_companion.router import AIRouter, RouterError
from openra_ai_companion.settings import HOSTED_MODEL, Settings
from openra_ai_companion.vision_budget import fit_images

ROOT = Path(__file__).resolve().parents[3]
LOCK = ROOT / "packaging" / "ai-pack.lock.json"


def _serve(handler: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _proxy_handler(behaviour: dict) -> type[BaseHTTPRequestHandler]:
    """A stand-in for rtsai.net/api/ai/v1 that records what the gateway sends."""

    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            pass

        def _send(self, status: int, value: dict, headers: dict[str, str] | None = None) -> None:
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for name, header in (headers or {}).items():
                self.send_header(name, header)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            behaviour["calls"].append(("GET", self.path, self.headers.get("Authorization", ""), None))
            self._send(200, {"state": "ok", "remaining_usd": 0.2}, {"x-rtsai-ai-state": "ok"})

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            behaviour["calls"].append(("POST", self.path, self.headers.get("Authorization", ""), body))
            if self.path.endswith("/install"):
                behaviour["installs"] += 1
                self._send(201, {"token": f"install-token-{behaviour['installs']}"})
                return
            status, state = behaviour["chat"].pop(0) if behaviour["chat"] else (200, "ok")
            if status == 200:
                self._send(200, {
                    "choices": [{"message": {"role": "assistant", "content": "Hosted Haiku answer."}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1200, "completion_tokens": 30},
                }, {"x-rtsai-ai-state": "ok", "x-rtsai-remaining-usd": "0.198000"})
            else:
                self._send(status, {"error": {"code": state, "message": f"proxy said {state}", "rtsai_state": state}},
                           {"x-rtsai-ai-state": state, "Retry-After": "120"})

    return Proxy


class _LocalModel(BaseHTTPRequestHandler):
    models: list[str] = []

    def log_message(self, *_args) -> None:
        pass

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        type(self).models.append(body["model"])
        payload = json.dumps({"choices": [{"message": {"content": "Local fallback answer."}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class HostedGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {"APPDATA": str(self.root)})
        self.environment.start()
        os.environ.pop("OPENRA_AI_HOSTED_ENDPOINT", None)
        self.behaviour = {"calls": [], "installs": 0, "chat": []}
        self.proxy, proxy_url = _serve(_proxy_handler(self.behaviour))
        self.config_path = self.root / "OpenRA-AI" / "provider.json"
        self.gateway = GatewayServer(
            ("127.0.0.1", 0),
            self.root,
            RuntimeConfig(mode="hosted", hosted_endpoint=proxy_url),
            config_path=self.config_path,
        )
        threading.Thread(target=self.gateway.serve_forever, daemon=True).start()
        self.gateway_url = f"http://127.0.0.1:{self.gateway.server_port}"

    def tearDown(self) -> None:
        for server in (self.gateway, self.proxy):
            if server is not None:
                server.shutdown()
                server.server_close()
        self.environment.stop()
        self.directory.cleanup()

    def _router(self) -> AIRouter:
        return AIRouter(Settings(router_url=self.gateway_url, model_provider="hosted",
                                 text_model=HOSTED_MODEL, vision_model=HOSTED_MODEL))

    def test_first_call_registers_once_and_keeps_the_token_out_of_the_game(self) -> None:
        router = self._router()
        result = router.chat([{"role": "user", "content": "status?"}])
        self.assertEqual(result.text, "Hosted Haiku answer.")
        self.assertEqual(result.input_tokens, 1200)
        self.assertEqual(router.service_state()["route"], "hosted")
        self.assertAlmostEqual(router.service_state()["remaining_usd"], 0.198)

        installs = [call for call in self.behaviour["calls"] if call[1].endswith("/install")]
        chats = [call for call in self.behaviour["calls"] if call[1].endswith("/chat/completions")]
        self.assertEqual(len(installs), 1)
        self.assertEqual(chats[0][2], "Bearer install-token-1")
        self.assertEqual(chats[0][3]["model"], HOSTED_MODEL)
        stored = self.config_path.read_text(encoding="utf-8")
        self.assertNotIn("install-token-1", stored, "the install token is stored encrypted")
        self.assertEqual(RuntimeConfig.load(self.config_path).install_token, "install-token-1")

        router.chat([{"role": "user", "content": "again"}])
        self.assertEqual(self.behaviour["installs"], 1, "the stored token is reused")

    def test_a_rejected_token_is_replaced_once(self) -> None:
        self.behaviour["chat"] = [(401, "unauthorized")]
        self._router().chat([{"role": "user", "content": "status?"}])
        self.assertEqual(self.behaviour["installs"], 2)
        self.assertEqual(RuntimeConfig.load(self.config_path).install_token, "install-token-2")

    def test_exhausted_allowance_falls_back_to_alert_lines_and_backs_off(self) -> None:
        self.behaviour["chat"] = [(429, "allowance")]
        router = self._router()
        with self.assertRaises(RouterError) as caught:
            router.chat([{"role": "user", "content": "status?"}])
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(caught.exception.state, "allowance")
        self.assertEqual(router.service_state()["route"], "none")

        companion = Companion(router=router)
        state, line = companion.idle_status()
        self.assertTrue(state.startswith("ready:"), "AUTO semantics in OpenRA are unchanged")
        self.assertEqual(line, "AI ALERTS ONLY  •  DAILY HOSTED ALLOWANCE USED, RESETS 00:00 UTC")
        companion.latest_snapshot = GameSnapshot.from_dict({"tick": 10, "map_info": {"width": 32, "height": 32}})
        answer = companion.ask("what now?")
        self.assertEqual(answer.text, HOSTED_SPOKEN["allowance"])
        self.assertEqual(answer.source, "deterministic-fallback")

        chats_before = sum(call[1].endswith("/chat/completions") for call in self.behaviour["calls"])
        with self.assertRaises(RouterError):
            router.chat([{"role": "user", "content": "and now?"}])
        chats_after = sum(call[1].endswith("/chat/completions") for call in self.behaviour["calls"])
        self.assertEqual(chats_before, chats_after, "the gateway backs off instead of retrying the proxy")

    def test_local_model_stands_in_when_installed(self) -> None:
        self.behaviour["chat"] = [(503, "paused")]
        _LocalModel.models = []
        local, local_url = _serve(_LocalModel)
        try:
            with patch.object(local_runtime, "LOCAL_CHAT_PORT", local.server_port), \
                    patch.object(GatewayServer, "local_fallback", return_value=True):
                router = self._router()
                result = router.chat([{"role": "user", "content": "status?"}])
            self.assertEqual(result.text, "Local fallback answer.")
            self.assertEqual(_LocalModel.models, ["local-coder"])
            self.assertEqual(router.service_state()["route"], "local-fallback")
            self.assertEqual(router.service_state()["state"], "paused")
            line = Companion(router=router).idle_status()[1]
            self.assertEqual(line, "AI READY  •  LOCAL MODEL STANDING IN: HOSTED AI PAUSED")
        finally:
            local.shutdown()
            local.server_close()

    def test_offline_proxy_is_reported_as_offline(self) -> None:
        self.proxy.shutdown()
        self.proxy.server_close()
        self.proxy = None
        with self.assertRaises(RouterError) as caught:
            self._router().chat([{"role": "user", "content": "status?"}])
        self.assertEqual(caught.exception.state, "offline")

    def test_voice_routes_stay_local_and_report_a_missing_voice_pack(self) -> None:
        request = urllib.request.Request(f"{self.gateway_url}/v1/audio/speech", data=b'{"input":"hi"}',
                                         headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 503)
        self.assertEqual(json.loads(caught.exception.read())["error"], "voice_pack_missing")
        self.assertFalse(any(call[1].endswith("/audio/speech") for call in self.behaviour["calls"]))

    def test_catalogue_names_the_hosted_brain_and_local_voice(self) -> None:
        with urllib.request.urlopen(f"{self.gateway_url}/v1/model/info", timeout=5) as response:
            models = {item["model_name"]: item["model_info"] for item in json.loads(response.read())["data"]}
        self.assertEqual(models[HOSTED_MODEL]["litellm_provider"], "anthropic")
        self.assertEqual(models["local-whisper"]["litellm_provider"], "local")
        self.assertEqual(models["local-kokoro"]["mode"], "audio_speech")


class HostedSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {"APPDATA": str(self.root)})
        self.environment.start()
        for name in ("OPENRA_AI_MODEL_PROVIDER", "OPENRA_AI_TEXT_MODEL", "OPENRA_AI_ROUTER_URL"):
            os.environ.pop(name, None)
        self.runtime = self.root / "bin" / "openra-ai-runtime.exe"
        self.runtime.parent.mkdir(parents=True)
        self.runtime.write_text("runtime", encoding="utf-8")
        self.runtime_root = self.root / "runtime"
        suffix = ".exe" if os.name == "nt" else ""
        for name in ("llama/llama-server", "whisper/whisper-server"):
            path = self.runtime_root / (name + suffix)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("binary", encoding="utf-8")

    def tearDown(self) -> None:
        self.environment.stop()
        self.directory.cleanup()

    def _manager(self, settings: Settings) -> LocalAIManager:
        return LocalAIManager(
            Companion(router=AIRouter(settings)),
            lock_path=LOCK,
            install_root=self.root / "install",
            runtime_executable=self.runtime,
            runtime_root=self.runtime_root,
            auto_start=False,
        )

    def test_first_launch_defaults_to_hosted_thinking_and_local_voice(self) -> None:
        with patch("openra_ai_companion.settings._load_project_env", return_value={}):
            settings = Settings.from_env()
            self.assertEqual((settings.model_provider, settings.text_model, settings.transcribe_model, settings.speech_model),
                             ("hosted", HOSTED_MODEL, "local-whisper", "local-kokoro"))
            Settings(model_provider="local").save()
            self.assertEqual(Settings.from_env().model_provider, "local", "an explicit choice is never overridden")

    def test_hosted_mode_downloads_only_the_voice_pack(self) -> None:
        manager = self._manager(Settings(model_provider="hosted", text_model=HOSTED_MODEL, vision_model=HOSTED_MODEL))
        status = manager.status()
        self.assertEqual(manager.mode, "hosted")
        self.assertEqual(status["mode"], "hosted")
        self.assertEqual(status["selection"]["profile"], "voice-only")
        self.assertEqual(status["total_bytes"], 268_539_880)
        self.assertEqual(status["state"], "not_installed")
        self.assertEqual(status["capabilities"]["assistant"], "stopped")

    def test_gateway_starts_in_hosted_mode_without_a_model_pack(self) -> None:
        manager = self._manager(Settings(model_provider="hosted", text_model=HOSTED_MODEL, vision_model=HOSTED_MODEL))
        process = MagicMock()
        process.poll.return_value = None
        with patch.object(model_setup, "LOCAL_ROUTER_URL", "http://127.0.0.1:4010"), \
                patch("openra_ai_companion.model_setup._reachable", side_effect=[False, True]), \
                patch("subprocess.Popen", return_value=process) as popen:
            manager._start_runtime()
        arguments = popen.call_args.args[0]
        self.assertEqual(arguments[arguments.index("--mode") + 1], "hosted")
        self.assertEqual(arguments[arguments.index("--port") + 1], "4010")
        settings = manager.companion.router.settings
        self.assertEqual((settings.router_url, settings.model_provider, settings.text_model),
                         ("http://127.0.0.1:4010", "hosted", HOSTED_MODEL))
        manager.stop()

    def test_external_mode_starts_its_gateway_in_installed_builds(self) -> None:
        manager = self._manager(Settings(model_provider="custom", router_url="http://127.0.0.1:4000", text_model="their-model"))
        self.assertEqual(manager.mode, "external")
        self.assertFalse(manager.installed, "External installs never download the model pack")
        process = MagicMock()
        process.poll.return_value = None
        with patch.object(model_setup, "LOCAL_ROUTER_URL", "http://127.0.0.1:4010"), \
                patch("openra_ai_companion.model_setup._reachable", side_effect=[False, True]), \
                patch("subprocess.Popen", return_value=process) as popen:
            manager._start_runtime()
        arguments = popen.call_args.args[0]
        self.assertEqual(arguments[arguments.index("--mode") + 1], "external")
        settings = manager.companion.router.settings
        self.assertEqual(settings.router_url, "http://127.0.0.1:4010", "the companion follows the launcher's gateway port")
        self.assertEqual(settings.text_model, "their-model")
        manager.stop()

    def test_serving_a_mode_keeps_the_saved_endpoint_and_key(self) -> None:
        path = self.root / "provider.json"
        RuntimeConfig(mode="external", endpoint="https://example.invalid/v1",
                      protected_api_key=protect_secret("external-key")).save(path)
        config = runtime_config_for("external", path)
        self.assertEqual(config.endpoint, "https://example.invalid/v1")
        self.assertEqual(config.api_key, "external-key")
        self.assertEqual(runtime_config_for("hosted", path).mode, "hosted")

    def test_configure_hosted_mode_for_the_installer(self) -> None:
        args = Namespace(mode="hosted", input_ini=None, endpoint="", key_file=None, text_model="", vision_model="",
                         transcribe_model="", speech_model="", speech_voice="", hosted_endpoint="")
        self.assertEqual(configure(args), 0)
        provider = RuntimeConfig.load()
        self.assertEqual(provider.mode, "hosted")
        self.assertEqual(provider.hosted_endpoint, "https://rtsai.net/api/ai/v1")
        settings = json.loads((self.root / "OpenRA-AI" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual((settings["model_provider"], settings["text_model"], settings["speech_model"]),
                         ("hosted", HOSTED_MODEL, "local-kokoro"))


class _HostedRouterStub:
    def __init__(self, provider: str = "hosted"):
        self.settings = Settings(router_url="http://127.0.0.1:4010", model_provider=provider,
                                 text_model=HOSTED_MODEL if provider == "hosted" else "local-coder")
        self.calls = 0

    def chat(self, *_args, **_kwargs):
        self.calls += 1
        raise RouterError("unused")

    def health(self):
        return {"reachable": True, "url": self.settings.router_url}

    def usage_summary(self):
        return {}


class HostedCostGuardrailTests(unittest.TestCase):
    def test_auto_mission_planner_never_runs_on_the_hosted_model(self) -> None:
        companion = Companion(router=_HostedRouterStub("hosted"))
        companion.latest_snapshot = GameSnapshot.from_dict({
            "tick": 100,
            "map_info": {"map_name": "Action Test", "width": 64, "height": 64},
            "units": [{"actor_id": 1, "type": "1tnk", "cell_x": 20, "cell_y": 20, "can_attack": True}],
            "buildings": [{"actor_id": 10, "type": "weap", "cell_x": 10, "cell_y": 10, "hp_percent": 0.5}],
            "available_production": ["1tnk"],
        })
        planned = []
        companion.set_action_planner(lambda instruction: planned.append(instruction) or {"message": "", "commands": []})
        companion.configure(auto_act=True)
        self.assertFalse(companion.llm_auto_planner_allowed)
        self.assertIsNone(companion.auto_act_once({"type": "enemy_spotted", "tick": 100, "battlefield": {}}))
        self.assertEqual(planned, [], "AUTO's MCP planner is blocked in hosted mode")
        self.assertTrue(Companion(router=_HostedRouterStub("local")).llm_auto_planner_allowed)

    def test_interactive_mcp_planner_goes_through_the_gateway_without_openai_key(self) -> None:
        planner = InteractiveMCPPlanner("127.0.0.1:9998", provider="openai", model="gpt-5.5",
                                        router=_HostedRouterStub("hosted"))
        planner._sync_route()
        self.assertEqual((planner.provider, planner.model, planner.router_url),
                         ("hosted", HOSTED_MODEL, "http://127.0.0.1:4010"))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "must-not-be-used"}):
            runtime = create_agent_model(provider="hosted", model=HOSTED_MODEL, router_url=planner.router_url)
        self.assertIsNotNone(runtime.client)
        self.assertEqual(str(runtime.client.base_url).rstrip("/"), "http://127.0.0.1:4010/v1")
        self.assertNotEqual(runtime.client.api_key, "must-not-be-used")
        self.assertTrue(runtime.gateway)

    def test_screenshots_are_downscaled_to_two_images_within_300_kb(self) -> None:
        from PIL import Image

        viewport = io.BytesIO()
        Image.effect_noise((1920, 1080), 80).convert("RGB").save(viewport, format="PNG")
        overview = io.BytesIO()
        Image.new("RGB", (96, 96), (70, 90, 60)).save(overview, format="PNG")
        extra = overview.getvalue()
        self.assertGreater(len(viewport.getvalue()), 1_000_000)

        images, views = fit_images(
            [(viewport.getvalue(), "image/png"), (overview.getvalue(), "image/png"), (extra, "image/png")],
            [{"order": 1, "scope": "viewport"}, {"order": 2, "scope": "overview"}, {"order": 3, "scope": "extra"}],
        )
        self.assertEqual(len(images), 2)
        self.assertLessEqual(sum(len(data) for data, _ in images), 300_000)
        self.assertEqual(images[0][1], "image/jpeg")
        self.assertLessEqual(max(views[0]["sent_width"], views[0]["sent_height"]), 1024)
        self.assertEqual(images[1][1], "image/png", "the small tactical overview stays lossless")
        self.assertEqual([view["scope"] for view in views], ["viewport", "overview"])


if __name__ == "__main__":
    unittest.main()
