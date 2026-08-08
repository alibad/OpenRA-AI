from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from .settings import Settings


class RouterError(RuntimeError):
    pass


@dataclass(frozen=True)
class RouterResult:
    text: str
    latency_ms: int
    model: str


class AIRouter:
    """The only model-provider boundary used by the game companion."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()

    def configure(self, values: dict, *, persist: bool = True) -> dict[str, str | float]:
        self.settings = self.settings.with_updates(values)
        if persist:
            self.settings.save()
        return self.settings.as_dict()

    def _request(self, path: str, body: bytes, content_type: str) -> tuple[bytes, int, str]:
        started = time.perf_counter()
        request = urllib.request.Request(
            f"{self.settings.router_url}{path}",
            data=body,
            headers={"Content-Type": content_type, "Accept": "application/json, audio/wav"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                payload = response.read()
                response_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RouterError(f"AI router returned HTTP {exc.code}: {detail}") from exc
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise RouterError(f"AI router is unavailable at {self.settings.router_url}: {exc}") from exc
        return payload, round((time.perf_counter() - started) * 1000), response_type

    def chat(self, messages: list[dict[str, str]], temperature: float | None = None) -> RouterResult:
        body = json.dumps(
            {
                "model": self.settings.text_model,
                "messages": messages,
                "max_tokens": 800,
                "reasoning_effort": "low",
            }
        ).encode("utf-8")
        payload, latency, _ = self._request("/v1/chat/completions", body, "application/json")
        try:
            response = json.loads(payload)
            content = response["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
            text = str(content).strip()
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RouterError("AI router returned an invalid chat completion") from exc
        if not text:
            raise RouterError("AI router returned an empty chat completion")
        return RouterResult(text, latency, self.settings.text_model)

    def transcribe(self, audio: bytes, filename: str = "question.wav") -> RouterResult:
        boundary = f"----OpenRAAI{uuid.uuid4().hex}"
        chunks = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{self.settings.transcribe_model}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: audio/wav\r\n\r\n".encode(),
            audio,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        payload, latency, _ = self._request(
            "/v1/audio/transcriptions", b"".join(chunks), f"multipart/form-data; boundary={boundary}"
        )
        try:
            text = str(json.loads(payload)["text"]).strip()
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RouterError("AI router returned an invalid transcription") from exc
        return RouterResult(text, latency, self.settings.transcribe_model)

    def speech(self, text: str) -> tuple[bytes, int, str]:
        body = json.dumps(
            {
                "model": self.settings.speech_model,
                "voice": self.settings.speech_voice,
                "input": text[:1200],
                "response_format": "wav",
            }
        ).encode("utf-8")
        payload, latency, content_type = self._request("/v1/audio/speech", body, "application/json")
        if payload.startswith(b"RIFF"):
            content_type = "audio/wav"
        return payload, latency, content_type or "audio/wav"

    def health(self) -> dict[str, str | bool]:
        request = urllib.request.Request(f"{self.settings.router_url}/health/liveliness", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return {"reachable": response.status < 500, "url": self.settings.router_url}
        except OSError:
            return {"reachable": False, "url": self.settings.router_url}
