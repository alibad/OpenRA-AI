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
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


LOCAL_CHAT_PORT = 4001
LOCAL_TRANSCRIBE_PORT = 4002
DEFAULT_PORT = 4000


def app_data_root() -> Path:
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

    @classmethod
    def load(cls, path: Path | None = None) -> "RuntimeConfig":
        path = path or provider_config_path()
        if not path.is_file():
            return cls()
        value = json.loads(path.read_text(encoding="utf-8"))
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value[key] for key in allowed if key in value}).validated()

    def validated(self) -> "RuntimeConfig":
        if self.mode not in {"local", "external"}:
            raise ValueError("AI mode must be local or external")
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


def _merge_companion_settings(config: RuntimeConfig) -> None:
    path = companion_settings_path()
    try:
        settings = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except json.JSONDecodeError:
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    local = config.mode == "local"
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

    def start(self) -> None:
        if self.config.mode != "local":
            return
        ai_root = self.install_root / "ai"
        executable_suffix = ".exe" if os.name == "nt" else ""
        llama = self.runtime_root / "llama" / f"llama-server{executable_suffix}"
        whisper = self.runtime_root / "whisper" / f"whisper-server{executable_suffix}"
        model = ai_root / self.profile.get("model", "models/llm/Qwen3VL-2B-Instruct-Q4_K_M.gguf")
        projector_path = self.profile.get("projector") if self.profile else "models/llm/mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"
        projector = ai_root / projector_path if projector_path else None
        whisper_model = ai_root / "models" / "stt" / "ggml-base.en.bin"
        missing = [path for path in (llama, whisper, model, projector, whisper_model) if path and not path.is_file()]
        if missing:
            raise FileNotFoundError("Local AI is selected but its payload is incomplete: " + ", ".join(str(p) for p in missing))

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.children.append(subprocess.Popen([
                str(llama), "--model", str(model),
                *(["--mmproj", str(projector)] if projector else []),
                "--host", "127.0.0.1", "--port", str(LOCAL_CHAT_PORT),
                "--ctx-size", str(self.profile.get("context_length", 8192)),
                "--threads", str(max(1, min(4, (os.cpu_count() or 4) // 2))),
                "--threads-batch", str(max(1, min(4, (os.cpu_count() or 4) // 2))),
                "--alias", "local-coder",
                "--parallel", "1",
                "--chat-template-kwargs", '{"enable_thinking":false}',
                "--jinja", "--no-webui",
            ], cwd=llama.parent, creationflags=creation_flags))
            self.children.append(subprocess.Popen([
                str(whisper), "--model", str(whisper_model), "--host", "127.0.0.1",
                "--port", str(LOCAL_TRANSCRIBE_PORT), "--language", "en",
                *(["--no-gpu"] if os.name == "nt" else []),
            ], cwd=whisper.parent, creationflags=creation_flags))
            self._wait_until_ready()
        except Exception:
            self.stop()
            raise

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

    def __init__(self, address: tuple[str, int], install_root: Path, config: RuntimeConfig, profile: dict | None = None):
        super().__init__(address, GatewayHandler)
        self.install_root = install_root
        self.config = config
        self.profile = profile or {}
        self._kokoro = None
        self._tts_lock = threading.Lock()

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

    def _write(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, value: dict | list) -> None:
        self._write(status, json.dumps(value).encode("utf-8"), "application/json")

    def do_GET(self) -> None:
        if self.path == "/health/liveliness":
            self._json(HTTPStatus.OK, {"status": "ok", "mode": self.server.config.mode})
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
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
            self._json(HTTPStatus.BAD_GATEWAY, {"error": "local_ai_runtime", "detail": str(exc)[:500]})

    def _external_url(self, path: str) -> str:
        base = self.server.config.endpoint.rstrip("/")
        if base.endswith("/v1") and path.startswith("/v1/"):
            return base + path[len("/v1"):]
        return base + path

    def _proxy(self, url: str, body: bytes, content_type: str) -> None:
        headers = {"Content-Type": content_type, "Accept": self.headers.get("Accept", "application/json")}
        if self.server.config.mode == "external" and self.server.config.api_key:
            headers["Authorization"] = "Bearer " + self.server.config.api_key
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
                self._write(response.status, payload, response.headers.get("Content-Type", "application/json"))
        except urllib.error.HTTPError as exc:
            self._write(exc.code, exc.read(), exc.headers.get("Content-Type", "application/json"))


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
    if mode not in {"local", "external"}:
        raise ValueError("Choose local or external AI mode")
    config = RuntimeConfig(
        mode=mode,
        endpoint=values.get("endpoint") or "https://api.openai.com/v1",
        protected_api_key=protect_secret(key),
        text_model=values.get("text_model") or "gpt-4.1-mini",
        vision_model=values.get("vision_model") or values.get("text_model") or "gpt-4.1-mini",
        transcribe_model=values.get("transcribe_model") or "whisper-1",
        speech_model=values.get("speech_model") or "gpt-4o-mini-tts",
        speech_voice=values.get("speech_voice") or "alloy",
    ).validated()
    config.save()
    _merge_companion_settings(config)
    print(f"Configured {config.mode} AI mode in {provider_config_path()}")
    return 0


def serve_runtime(args: argparse.Namespace) -> int:
    install_root = Path(args.root).resolve()
    config = RuntimeConfig(mode=args.mode) if args.mode else RuntimeConfig.load()
    runtime_root = Path(args.runtime_root).resolve() if args.runtime_root else None
    profile = json.loads(getattr(args, "model_profile", "{}"))
    processes = RuntimeProcesses(install_root, config, runtime_root, profile)
    processes.start()
    atexit.register(processes.stop)
    server = GatewayServer((args.host, args.port), install_root, config, profile)

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
    serve.add_argument("--mode", choices=("local", "external"))
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--parent-pid", type=int, default=0)
    serve.add_argument("--model-profile", default="{}")
    config = commands.add_parser("configure")
    config.add_argument("--mode", choices=("local", "external"))
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
