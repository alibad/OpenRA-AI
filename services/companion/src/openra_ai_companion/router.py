from __future__ import annotations

import io
import json
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from dataclasses import dataclass

from .settings import Settings


class RouterError(RuntimeError):
    pass


@dataclass(frozen=True)
class RouterResult:
    text: str
    latency_ms: int
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class AIRouter:
    """The only model-provider boundary used by the game companion."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self._usage_lock = threading.Lock()
        self._usage_started = time.monotonic()
        self._chat_calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._speech_characters = 0
        self._transcription_seconds = 0.0

    def configure(self, values: dict, *, persist: bool = True) -> dict[str, str | float | bool]:
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
            usage = response.get("usage") or {}
            input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RouterError("AI router returned an invalid chat completion") from exc
        if not text:
            raise RouterError("AI router returned an empty chat completion")
        if input_tokens <= 0:
            input_tokens = max(1, sum(len(str(message.get("content", ""))) for message in messages) // 4)
        if output_tokens <= 0:
            output_tokens = max(1, len(text) // 4)
        with self._usage_lock:
            self._chat_calls += 1
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens
        return RouterResult(text, latency, self.settings.text_model, input_tokens, output_tokens)

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
        duration = 0.0
        try:
            with wave.open(io.BytesIO(audio), "rb") as wav:
                duration = wav.getnframes() / max(1, wav.getframerate())
        except (wave.Error, EOFError):
            pass
        with self._usage_lock:
            self._transcription_seconds += duration
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
        if not payload.startswith(b"RIFF"):
            detail = payload[:300].decode("utf-8", errors="replace")
            raise RouterError(f"AI router returned invalid WAV speech: {detail}")
        with self._usage_lock:
            self._speech_characters += len(text)
        return payload, latency, "audio/wav"

    @staticmethod
    def _text_prices(model: str) -> tuple[float, float, str]:
        prices = {
            "gpt-5.5": (5.0, 30.0, "GPT-5.5 public token rates"),
        }
        return prices.get(model.lower(), (0.0, 0.0, f"No public price mapping for {model}"))

    def usage_summary(self) -> dict:
        with self._usage_lock:
            elapsed_seconds = max(1.0, time.monotonic() - self._usage_started)
            chat_calls = self._chat_calls
            input_tokens = self._input_tokens
            output_tokens = self._output_tokens
            speech_characters = self._speech_characters
            transcription_seconds = self._transcription_seconds

        input_rate, output_rate, text_assumption = self._text_prices(self.settings.text_model)
        text_cost = input_tokens / 1_000_000 * input_rate + output_tokens / 1_000_000 * output_rate

        speech_known = self.settings.speech_model.lower() in {"openai-tts", "tts-1"}
        speech_rate = 15.0 if speech_known else 0.0
        speech_cost = speech_characters / 1_000_000 * speech_rate

        transcription_known = self.settings.transcribe_model.lower() in {"openai-transcribe", "whisper-1"}
        transcription_rate = 0.006 if transcription_known else 0.0
        transcription_cost = transcription_seconds / 60 * transcription_rate

        total = text_cost + speech_cost + transcription_cost
        hourly = total / max(60.0, elapsed_seconds) * 3600
        return {
            "elapsed_seconds": round(elapsed_seconds, 1),
            "chat_calls": chat_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "speech_characters": speech_characters,
            "transcription_seconds": round(transcription_seconds, 2),
            "text_cost_usd": round(text_cost, 6),
            "speech_cost_usd": round(speech_cost, 6),
            "transcription_cost_usd": round(transcription_cost, 6),
            "session_cost_usd": round(total, 6),
            "hourly_cost_usd": round(hourly, 6),
            "pricing_known": input_rate > 0 and speech_known and transcription_known,
            "assumptions": [
                text_assumption,
                "openai-tts estimated at TTS-1: $15 / 1M characters" if speech_known else f"No public price mapping for {self.settings.speech_model}",
                "openai-transcribe estimated at Whisper: $0.006 / minute" if transcription_known else f"No public price mapping for {self.settings.transcribe_model}",
            ],
            "estimate_only": True,
        }

    def health(self) -> dict[str, str | bool]:
        request = urllib.request.Request(f"{self.settings.router_url}/health/liveliness", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return {"reachable": response.status < 500, "url": self.settings.router_url}
        except OSError:
            return {"reachable": False, "url": self.settings.router_url}
