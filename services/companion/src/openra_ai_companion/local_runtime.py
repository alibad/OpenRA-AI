from __future__ import annotations

import argparse
import atexit
import base64
import configparser
import ctypes
import io
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from ctypes import wintypes
from dataclasses import asdict, dataclass, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .hosted_gateway import (
    DEFAULT_HOSTED_ENDPOINT,
    FALLBACK_STATES,
    HOSTED_MODEL,
    HostedClient,
    hosted_endpoint,
    prepare_hosted_body,
    prepare_local_body,
)


LOCAL_CHAT_PORT = int(os.environ.get("OPENRA_AI_LOCAL_CHAT_PORT", "4001"))
LOCAL_TRANSCRIBE_PORT = int(os.environ.get("OPENRA_AI_LOCAL_TRANSCRIBE_PORT", "4002"))
DEFAULT_PORT = 4000


def app_data_root() -> Path:
    configured = os.environ.get("OPENRA_AI_DATA_DIR", "").strip()
    if configured:
        # The RTS AI mod keeps provider.json (and the hosted install token) in its support directory.
        return Path(configured).expanduser()
    return Path(os.environ.get("APPDATA") or Path.home()) / "OpenRA-AI"


def provider_config_path() -> Path:
    return app_data_root() / "provider.json"


def companion_settings_path() -> Path:
    return app_data_root() / "settings.json"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def protect_secret(value: str) -> str:
    if not value:
        return ""
    if os.name != "nt":
        return "portable:" + base64.b64encode(value.encode("utf-8")).decode("ascii")
    source, source_buffer = _blob(value.encode("utf-8"))
    destination = _DataBlob()
    description = "OpenRA AI provider key"
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), description, None, None, None, 0, ctypes.byref(destination)
    ):
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(destination.pbData, destination.cbData)
        return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)
        del source_buffer


def unprotect_secret(value: str) -> str:
    if not value:
        return ""
    prefix, _, payload = value.partition(":")
    encrypted = base64.b64decode(payload)
    if prefix == "portable":
        return encrypted.decode("utf-8")
    if prefix != "dpapi" or os.name != "nt":
        raise ValueError("Provider key is not readable for this Windows user")
    source, source_buffer = _blob(encrypted)
    destination = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(destination)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(destination.pbData, destination.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)
        del source_buffer


AI_MODES = ("local", "external", "hosted")


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str = "local"
    endpoint: str = "https://api.openai.com/v1"
    protected_api_key: str = ""
    text_model: str = "gpt-4.1-mini"
    vision_model: str = "gpt-4.1-mini"
    transcribe_model: str = "whisper-1"
    speech_model: str = "gpt-4o-mini-tts"
    speech_voice: str = "alloy"
    # Hosted mode: the rtsai.net proxy and its DPAPI-protected install token.
    hosted_endpoint: str = DEFAULT_HOSTED_ENDPOINT
    protected_install_token: str = ""

    @classmethod
    def load(cls, path: Path | None = None) -> "RuntimeConfig":
        path = path or provider_config_path()
        if not path.is_file():
            return cls()
        value = json.loads(path.read_text(encoding="utf-8"))
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value[key] for key in allowed if key in value}).validated()

    @classmethod
    def exists(cls, path: Path | None = None) -> bool:
        return (path or provider_config_path()).is_file()

    def validated(self) -> "RuntimeConfig":
        if self.mode not in AI_MODES:
            raise ValueError("AI mode must be local, external, or hosted")
        endpoint = self.endpoint.rstrip("/")
        if self.mode == "external" and not endpoint.startswith(("http://", "https://")):
            raise ValueError("External AI endpoint must be an absolute HTTP(S) URL")
        for value in (self.text_model, self.vision_model, self.transcribe_model, self.speech_model):
            if not value.strip() or len(value) > 160:
                raise ValueError("AI model names must contain 1 to 160 characters")
        return RuntimeConfig(**{**asdict(self), "endpoint": endpoint})

    def save(self, path: Path | None = None) -> Path:
        path = path or provider_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self.validated()), indent=2) + "\n", encoding="utf-8")
        return path

    @property
    def api_key(self) -> str:
        return unprotect_secret(self.protected_api_key)

    @property
    def install_token(self) -> str:
        try:
            return unprotect_secret(self.protected_install_token)
        except (ValueError, OSError):
            # A token encrypted for another Windows user is useless here; re-register.
            return ""


def _merge_companion_settings(config: RuntimeConfig) -> None:
    path = companion_settings_path()
    try:
        settings = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except json.JSONDecodeError:
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    local = config.mode == "local"
    if config.mode == "hosted":
        settings.update({
            "router_url": f"http://127.0.0.1:{DEFAULT_PORT}",
            "model_provider": "hosted",
            "text_model": HOSTED_MODEL,
            "vision_model": HOSTED_MODEL,
            "transcribe_model": "local-whisper",
            "speech_model": "local-kokoro",
            "speech_voice": "alloy",
        })
    else:
        settings.update({
            "router_url": f"http://127.0.0.1:{DEFAULT_PORT}",
            "model_provider": "local" if local else "custom",
            "text_model": "local-coder" if local else config.text_model,
            "vision_model": "local-coder" if local else config.vision_model,
            "transcribe_model": "local-whisper" if local else config.transcribe_model,
            "speech_model": "local-kokoro" if local else config.speech_model,
            "speech_voice": "alloy" if local else config.speech_voice,
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


class RuntimeProcesses:
    def __init__(self, install_root: Path, config: RuntimeConfig, runtime_root: Path | None = None, profile: dict | None = None):
        self.install_root = install_root
        self.config = config
        self.runtime_root = runtime_root or install_root / "ai" / "runtime"
        self.children: list[subprocess.Popen] = []
        self.profile = profile or {}
        self._chat_process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def _paths(self) -> dict[str, Path | None]:
        ai_root = self.install_root / "ai"
        executable_suffix = ".exe" if os.name == "nt" else ""
        model = self.profile.get("model", "models/llm/Qwen3VL-2B-Instruct-Q4_K_M.gguf") if self.profile else "models/llm/Qwen3VL-2B-Instruct-Q4_K_M.gguf"
        projector_path = self.profile.get("projector") if self.profile else "models/llm/mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"
        return {
            "llama": self.runtime_root / "llama" / f"llama-server{executable_suffix}",
            "whisper": self.runtime_root / "whisper" / f"whisper-server{executable_suffix}",
            "model": ai_root / model if model else None,
            "projector": ai_root / projector_path if projector_path else None,
            "whisper_model": ai_root / "models" / "stt" / "ggml-base.en.bin",
        }

    @property
    def local_chat_installed(self) -> bool:
        paths = self._paths()
        return all(path is not None and path.is_file() for path in (paths["llama"], paths["model"])) and (
            paths["projector"] is None or paths["projector"].is_file()
        )

    @property
    def local_vision(self) -> bool:
        return self._paths()["projector"] is not None

    @property
    def voice_installed(self) -> bool:
        paths = self._paths()
        return bool(paths["whisper"] and paths["whisper"].is_file() and paths["whisper_model"] and paths["whisper_model"].is_file())

    def _chat_command(self) -> tuple[list[str], Path]:
        paths = self._paths()
        llama, model, projector = paths["llama"], paths["model"], paths["projector"]
        assert llama is not None and model is not None
        return [
            str(llama), "--model", str(model),
            *(["--mmproj", str(projector)] if projector else []),
            "--host", "127.0.0.1", "--port", str(LOCAL_CHAT_PORT),
            "--ctx-size", str(self.profile.get("context_length") or 8192),
            "--threads", str(max(1, min(4, (os.cpu_count() or 4) // 2))),
            "--threads-batch", str(max(1, min(4, (os.cpu_count() or 4) // 2))),
            "--alias", "local-coder",
            "--parallel", "1",
            "--chat-template-kwargs", '{"enable_thinking":false}',
            "--jinja", "--no-webui",
        ], llama.parent

    def _whisper_command(self) -> tuple[list[str], Path]:
        paths = self._paths()
        whisper, whisper_model = paths["whisper"], paths["whisper_model"]
        assert whisper is not None and whisper_model is not None
        return [
            str(whisper), "--model", str(whisper_model), "--host", "127.0.0.1",
            "--port", str(LOCAL_TRANSCRIBE_PORT), "--language", "en",
            *(["--no-gpu"] if os.name == "nt" else []),
        ], whisper.parent

    def start(self) -> None:
        if self.config.mode == "hosted":
            # Hosted thinking needs no local model in memory. Speech recognition
            # starts when the voice pack is installed; the local chat model only
            # starts on demand as a fallback (start_local_chat).
            if self.voice_installed:
                command, cwd = self._whisper_command()
                self.children.append(subprocess.Popen(command, cwd=cwd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
            return
        if self.config.mode != "local":
            return
        paths = self._paths()
        missing = [path for path in (paths["llama"], paths["whisper"], paths["model"], paths["projector"], paths["whisper_model"])
                   if path and not path.is_file()]
        if missing:
            raise FileNotFoundError("Local AI is selected but its payload is incomplete: " + ", ".join(str(p) for p in missing))

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            command, cwd = self._chat_command()
            self._chat_process = subprocess.Popen(command, cwd=cwd, creationflags=creation_flags)
            self.children.append(self._chat_process)
            command, cwd = self._whisper_command()
            self.children.append(subprocess.Popen(command, cwd=cwd, creationflags=creation_flags))
            self._wait_until_ready()
        except Exception:
            self.stop()
            raise

    def start_local_chat(self) -> bool:
        """Start the installed local model as the hosted fallback. Returns False when it is not installed."""
        with self._lock:
            if self._chat_process is not None and self._chat_process.poll() is None:
                return True
            if not self.local_chat_installed:
                return False
            command, cwd = self._chat_command()
            self._chat_process = subprocess.Popen(command, cwd=cwd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.children.append(self._chat_process)
            return True

    def _wait_until_ready(self) -> None:
        urls = (
            f"http://127.0.0.1:{LOCAL_CHAT_PORT}/health",
            f"http://127.0.0.1:{LOCAL_TRANSCRIBE_PORT}/health",
        )
        pending = set(urls)
        deadline = time.monotonic() + 180
        while pending and time.monotonic() < deadline:
            for child in self.children:
                if child.poll() is not None:
                    self.stop()
                    raise RuntimeError(f"Local AI model process exited with code {child.returncode}")
            for url in tuple(pending):
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status < 500:
                            pending.remove(url)
                except (OSError, TimeoutError, urllib.error.URLError):
                    pass
            if pending:
                time.sleep(0.5)
        if pending:
            self.stop()
            raise TimeoutError("Local AI models did not finish loading within three minutes")

    def stop(self) -> None:
        for child in reversed(self.children):
            if child.poll() is None:
                child.terminate()
        for child in reversed(self.children):
            if child.poll() is None:
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        install_root: Path,
        config: RuntimeConfig,
        profile: dict | None = None,
        processes: RuntimeProcesses | None = None,
        config_path: Path | None = None,
    ):
        super().__init__(address, GatewayHandler)
        self.install_root = install_root
        self.config = config
        self.profile = profile or {}
        self.processes = processes or RuntimeProcesses(install_root, config, profile=self.profile)
        self.config_path = config_path or provider_config_path()
        self._kokoro = None
        self._tts_lock = threading.Lock()
        self._chat_health = (0.0, False)
        self.hosted = (
            HostedClient(hosted_endpoint(config.hosted_endpoint), self._load_install_token, self._save_install_token)
            if config.mode == "hosted" else None
        )

    def _load_install_token(self) -> str:
        if RuntimeConfig.exists(self.config_path):
            return RuntimeConfig.load(self.config_path).install_token
        return self.config.install_token

    def _save_install_token(self, token: str) -> None:
        """Persist the install token under DPAPI without touching the rest of provider.json."""
        if RuntimeConfig.exists(self.config_path):
            current = RuntimeConfig.load(self.config_path)
        else:
            current = replace(self.config, mode="hosted")
        replace(current, protected_install_token=protect_secret(token)).save(self.config_path)

    def local_chat_ready(self) -> bool:
        checked_at, ready = self._chat_health
        if time.monotonic() - checked_at < 2.0:
            return ready
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{LOCAL_CHAT_PORT}/health", timeout=0.5) as response:
                ready = response.status < 500
        except (OSError, TimeoutError, urllib.error.URLError):
            ready = False
        self._chat_health = (time.monotonic(), ready)
        return ready

    def local_fallback(self) -> bool:
        """True when the installed local model can answer now; starts it on first need."""
        if not self.processes.start_local_chat():
            return False
        return self.local_chat_ready()

    def speech(self, text: str, voice: str) -> bytes:
        ai_root = self.install_root / "ai"
        model = ai_root / "models" / "tts" / "kokoro-v1.0.int8.onnx"
        voices = ai_root / "models" / "tts" / "voices-v1.0.bin"
        if not model.is_file() or not voices.is_file():
            raise FileNotFoundError("Kokoro model files are not installed")
        with self._tts_lock:
            if self._kokoro is None:
                from kokoro_onnx import Kokoro
                self._kokoro = Kokoro(str(model), str(voices))
            mapped_voice = {
                "alloy": "af_sarah", "echo": "am_adam", "fable": "bf_emma",
                "onyx": "am_michael", "nova": "af_nicole", "shimmer": "af_sky",
            }.get(voice, "af_sarah")
            samples, sample_rate = self._kokoro.create(text, voice=mapped_voice, speed=1.0, lang="en-us")
        import numpy as np
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(int(sample_rate))
            wav.writeframes(pcm)
        return output.getvalue()


class GatewayHandler(BaseHTTPRequestHandler):
    server: GatewayServer

    def log_message(self, format: str, *args) -> None:
        print("local-ai: " + format % args, flush=True)

    def _write(self, status: int, payload: bytes, content_type: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, value: dict | list) -> None:
        self._write(status, json.dumps(value).encode("utf-8"), "application/json")

    def do_GET(self) -> None:
        if self.path == "/health/liveliness":
            health = {"status": "ok", "mode": self.server.config.mode}
            if self.server.hosted:
                health["hosted"] = self.server.hosted.state()
            self._json(HTTPStatus.OK, health)
            return
        if self.path == "/v1/hosted/status" and self.server.hosted:
            status = self.server.hosted.refresh_status()
            status["voice_installed"] = self.server.processes.voice_installed
            status["local_fallback_installed"] = self.server.processes.local_chat_installed
            self._json(HTTPStatus.OK, status)
            return
        if self.path == "/v1/model/info" and self.server.hosted:
            local_api = f"http://127.0.0.1:{LOCAL_TRANSCRIBE_PORT}"
            self._json(HTTPStatus.OK, {"data": [
                {
                    "model_name": HOSTED_MODEL,
                    "litellm_params": {"model": HOSTED_MODEL, "api_base": self.server.hosted.endpoint},
                    "model_info": {"mode": "chat", "litellm_provider": "anthropic",
                                   "display_name": "Claude Haiku 4.5 (RTS AI hosted)", "supports_vision": True},
                },
                {
                    "model_name": "local-whisper",
                    "litellm_params": {"model": "local-whisper", "api_base": local_api},
                    "model_info": {"mode": "audio_transcription", "litellm_provider": "local", "supports_vision": False},
                },
                {
                    "model_name": "local-kokoro",
                    "litellm_params": {"model": "local-kokoro", "api_base": local_api},
                    "model_info": {"mode": "audio_speech", "litellm_provider": "local", "supports_vision": False},
                },
            ]})
            return
        if self.path == "/v1/model/info":
            local = self.server.config.mode == "local"
            provider = "local" if local else "openai"
            endpoint = f"http://127.0.0.1:{LOCAL_CHAT_PORT}/v1" if local else self.server.config.endpoint
            models = [
                ("local-coder" if local else self.server.config.text_model, "chat"),
                ("local-whisper" if local else self.server.config.transcribe_model, "audio_transcription"),
                ("local-kokoro" if local else self.server.config.speech_model, "audio_speech"),
            ]
            self._json(HTTPStatus.OK, {"data": [{
                "model_name": model,
                "litellm_params": {"model": model, "api_base": endpoint},
                "model_info": {
                    "mode": mode, "litellm_provider": provider,
                    "display_name": self.server.profile.get("model_name") if mode == "chat" else None,
                    "supports_vision": bool(self.server.profile.get("projector")) if self.server.profile else True,
                },
            } for model, mode in models]})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            if self.server.config.mode == "external":
                self._proxy(self._external_url(self.path), body, self.headers.get("Content-Type", "application/json"))
            elif self.path == "/v1/chat/completions" and self.server.hosted:
                self._hosted_chat(body)
            elif (self.path in {"/v1/audio/transcriptions", "/v1/audio/speech"} and self.server.hosted
                  and not self.server.processes.voice_installed):
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {
                    "error": "voice_pack_missing",
                    "detail": "Install the voice pack (about 270 MB) to talk to the co-commander.",
                })
            elif self.path == "/v1/chat/completions":
                request = json.loads(body)
                has_images = any(isinstance(message.get("content"), list) and
                                 any(part.get("type") == "image_url" for part in message["content"] if isinstance(part, dict))
                                 for message in request.get("messages", []))
                if has_images and self.server.profile and not self.server.profile.get("projector"):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "This lightweight profile does not support map images."})
                    return
                self._proxy(f"http://127.0.0.1:{LOCAL_CHAT_PORT}{self.path}", body, "application/json")
            elif self.path == "/v1/audio/transcriptions":
                self._proxy(
                    f"http://127.0.0.1:{LOCAL_TRANSCRIBE_PORT}/inference",
                    body,
                    self.headers.get("Content-Type", "multipart/form-data"),
                )
            elif self.path == "/v1/audio/speech":
                request = json.loads(body)
                audio = self.server.speech(str(request.get("input", ""))[:1200], str(request.get("voice", "alloy")))
                self._write(HTTPStatus.OK, audio, "audio/wav")
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except FileNotFoundError as exc:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "voice_pack_missing", "detail": str(exc)[:500]})
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
            self._json(HTTPStatus.BAD_GATEWAY, {"error": "local_ai_runtime", "detail": str(exc)[:500]})

    def _hosted_chat(self, body: bytes) -> None:
        """Hosted brain with graceful degradation: the local model if installed, else a clear error.

        The companion turns an error into deterministic alert lines and reads
        X-RTSAI-AI-State / X-RTSAI-AI-Route to tell the player what happened.
        """
        hosted = self.server.hosted
        assert hosted is not None
        try:
            hosted_body = prepare_hosted_body(body)
        except (ValueError, AttributeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": {"code": "invalid_json", "message": "Request body is not JSON"}})
            return
        reply = hosted.chat(hosted_body)
        if reply.state in FALLBACK_STATES:
            if self.server.local_fallback():
                hosted.set_route("local-fallback")
                try:
                    self._proxy(
                        f"http://127.0.0.1:{LOCAL_CHAT_PORT}/v1/chat/completions",
                        prepare_local_body(body, vision=self.server.processes.local_vision),
                        "application/json",
                        {"X-RTSAI-AI-Route": "local-fallback", "X-RTSAI-AI-State": reply.state},
                    )
                    return
                except (OSError, urllib.error.URLError):
                    pass
            hosted.set_route("none")
            self._write(reply.status, reply.payload, reply.content_type,
                        {"X-RTSAI-AI-Route": "none", "X-RTSAI-AI-State": reply.state, **reply.headers})
            return
        hosted.set_route("hosted")
        self._write(reply.status, reply.payload, reply.content_type,
                    {"X-RTSAI-AI-Route": "hosted", "X-RTSAI-AI-State": reply.state, **reply.headers})

    def _external_url(self, path: str) -> str:
        base = self.server.config.endpoint.rstrip("/")
        if base.endswith("/v1") and path.startswith("/v1/"):
            return base + path[len("/v1"):]
        return base + path

    def _proxy(self, url: str, body: bytes, content_type: str, extra_headers: dict[str, str] | None = None) -> None:
        headers = {"Content-Type": content_type, "Accept": self.headers.get("Accept", "application/json")}
        if self.server.config.mode == "external" and self.server.config.api_key:
            headers["Authorization"] = "Bearer " + self.server.config.api_key
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
                self._write(response.status, payload, response.headers.get("Content-Type", "application/json"), extra_headers)
        except urllib.error.HTTPError as exc:
            self._write(exc.code, exc.read(), exc.headers.get("Content-Type", "application/json"), extra_headers)


def configure(args: argparse.Namespace) -> int:
    values = vars(args).copy()
    input_ini = getattr(args, "input_ini", None)
    if input_ini:
        input_path = Path(input_ini)
        parser = configparser.ConfigParser()
        parser.read(input_path, encoding="utf-8")
        values.update(dict(parser["provider"]))
        input_path.unlink(missing_ok=True)
    key = values.get("api_key") or ""
    key_file = values.get("key_file")
    if key_file:
        key_path = Path(key_file)
        key = key_path.read_text(encoding="utf-8").strip()
        key_path.unlink(missing_ok=True)
    mode = values.get("mode")
    if mode not in AI_MODES:
        raise ValueError("Choose local, external, or hosted AI mode")
    previous = RuntimeConfig.load() if RuntimeConfig.exists() else RuntimeConfig()
    config = RuntimeConfig(
        mode=mode,
        endpoint=values.get("endpoint") or "https://api.openai.com/v1",
        protected_api_key=protect_secret(key),
        text_model=values.get("text_model") or "gpt-4.1-mini",
        vision_model=values.get("vision_model") or values.get("text_model") or "gpt-4.1-mini",
        transcribe_model=values.get("transcribe_model") or "whisper-1",
        speech_model=values.get("speech_model") or "gpt-4o-mini-tts",
        speech_voice=values.get("speech_voice") or "alloy",
        hosted_endpoint=values.get("hosted_endpoint") or previous.hosted_endpoint,
        # Re-running setup keeps this install's identity and allowance.
        protected_install_token=previous.protected_install_token,
    ).validated()
    config.save()
    _merge_companion_settings(config)
    print(f"Configured {config.mode} AI mode in {provider_config_path()}")
    return 0


def runtime_config_for(mode: str | None, path: Path | None = None) -> RuntimeConfig:
    """The saved provider configuration with --mode applied.

    Earlier builds replaced the whole configuration with RuntimeConfig(mode=...),
    which dropped the External endpoint and key the installer had saved.
    """
    config = RuntimeConfig.load(path)
    return replace(config, mode=mode).validated() if mode else config


def serve_runtime(args: argparse.Namespace) -> int:
    install_root = Path(args.root).resolve()
    config = runtime_config_for(args.mode)
    runtime_root = Path(args.runtime_root).resolve() if args.runtime_root else None
    profile = json.loads(getattr(args, "model_profile", "{}"))
    processes = RuntimeProcesses(install_root, config, runtime_root, profile)
    processes.start()
    atexit.register(processes.stop)
    server = GatewayServer((args.host, args.port), install_root, config, profile, processes)
    if server.hosted:
        # Register (zero-click) and read the allowance in the background so the
        # first question does not wait for the install round trip.
        threading.Thread(target=server.hosted.refresh_status, name="rtsai-hosted-register", daemon=True).start()

    if args.parent_pid:
        def watch_parent() -> None:
            while _pid_alive(args.parent_pid):
                time.sleep(1)
            server.shutdown()
        threading.Thread(target=watch_parent, daemon=True).start()

    def stop_server(*_args) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGINT, stop_server)
    signal.signal(signal.SIGTERM, stop_server)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        processes.stop()
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="openra-ai-runtime")
    commands = root.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--root", required=True)
    serve.add_argument("--runtime-root")
    serve.add_argument("--mode", choices=AI_MODES)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--parent-pid", type=int, default=0)
    serve.add_argument("--model-profile", default="{}")
    config = commands.add_parser("configure")
    config.add_argument("--mode", choices=AI_MODES)
    config.add_argument("--hosted-endpoint", default="")
    config.add_argument("--input-ini")
    config.add_argument("--endpoint", default="https://api.openai.com/v1")
    config.add_argument("--key-file")
    config.add_argument("--text-model", default="gpt-4.1-mini")
    config.add_argument("--vision-model", default="")
    config.add_argument("--transcribe-model", default="whisper-1")
    config.add_argument("--speech-model", default="gpt-4o-mini-tts")
    config.add_argument("--speech-voice", default="alloy")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return configure(args) if args.command == "configure" else serve_runtime(args)


if __name__ == "__main__":
    raise SystemExit(main())
