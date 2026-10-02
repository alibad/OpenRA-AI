from __future__ import annotations

import base64
import io
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from dataclasses import dataclass, replace

from .settings import HOSTED_MODEL, Settings

# The hosted proxy accepts two inline images per call (viewport + tactical overview).
MAX_IMAGES = 2


class RouterError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, state: str = "", route: str = ""):
        super().__init__(message)
        self.status = status
        # Hosted-gateway classification (ok, allowance, offline, paused, budget, ...).
        self.state = state
        self.route = route


@dataclass(frozen=True)
class RouterResult:
    text: str
    latency_ms: int
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    vision_used: bool = False


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
        self._service_lock = threading.Lock()
        self._service: dict[str, object] = {"route": "", "state": "", "detail": "", "remaining_usd": None, "updated_at": 0.0}

    def service_state(self) -> dict[str, object]:
        """Where the brain was served last time: hosted, local-fallback, or none (alerts only)."""
        with self._service_lock:
            return dict(self._service)

    def _record_service(self, route: str, state: str, detail: str = "", remaining: str | None = None) -> None:
        with self._service_lock:
            self._service.update({"route": route, "state": state, "detail": detail[:200], "updated_at": time.time()})
            if remaining:
                try:
                    self._service["remaining_usd"] = float(remaining)
                except ValueError:
                    pass

    def configure(self, values: dict, *, persist: bool = True) -> dict[str, str | float | bool]:
        self.settings = self.settings.with_updates(values)
        if persist:
            self.settings.save()
        return self.settings.as_dict()

    def _request(self, path: str, body: bytes, content_type: str) -> tuple[bytes, int, str]:
        started = time.perf_counter()
        local_audio = ((path == "/v1/audio/transcriptions" and self.settings.transcribe_model == "local-whisper") or
                       (path == "/v1/audio/speech" and self.settings.speech_model == "local-kokoro"))
        base_url = os.environ.get("OPENRA_AI_LOCAL_ROUTER_URL", "http://127.0.0.1:4000") if local_audio and self.settings.model_provider == "custom" else self.settings.router_url
        request = urllib.request.Request(
            f"{base_url}{path}",
            data=body,
            headers={"Content-Type": content_type, "Accept": "application/json, audio/wav"},
            method="POST",
        )
        brain = path == "/v1/chat/completions"
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                payload = response.read()
                response_type = response.headers.get("Content-Type", "")
                if brain:
                    self._record_service(
                        response.headers.get("X-RTSAI-AI-Route", "") or "direct",
                        response.headers.get("X-RTSAI-AI-State", "") or "ok",
                        remaining=response.headers.get("x-rtsai-remaining-usd"),
                    )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            state = (exc.headers.get("X-RTSAI-AI-State", "") if exc.headers else "") or "error"
            route = (exc.headers.get("X-RTSAI-AI-Route", "") if exc.headers else "") or "none"
            if brain:
                try:
                    message = str(json.loads(detail).get("error", {}).get("message", ""))
                except (ValueError, AttributeError):
                    message = ""
                self._record_service(route, state, message)
            raise RouterError(f"AI router returned HTTP {exc.code}: {detail}", status=exc.code, state=state, route=route) from exc
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            # urllib wraps connection failures (refused, or a connect timeout) in
            # URLError: the gateway is not running. A bare timeout while waiting
            # for the response means it is up but the model behind it is slow.
            state = "upstream" if isinstance(exc, TimeoutError) else "gateway_unreachable"
            if brain:
                self._record_service("none", state, str(exc))
            raise RouterError(f"AI router is unavailable at {self.settings.router_url}: {exc}",
                              state=state, route="none") from exc
        return payload, round((time.perf_counter() - started) * 1000), response_type

    def _get_json(self, path: str) -> dict:
        request = urllib.request.Request(
            f"{self.settings.router_url}{path}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=min(5, self.settings.timeout_seconds)) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RouterError(f"AI router returned HTTP {exc.code}: {detail}") from exc
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RouterError(f"AI router catalogue is unavailable at {self.settings.router_url}: {exc}") from exc

    @staticmethod
    def _fallback_models() -> list[dict]:
        return [
            {"id": "gpt-5.5", "label": "GPT-5.5", "provider": "openai", "mode": "chat", "local": False},
            {"id": "claude-opus", "label": "Claude Opus", "provider": "anthropic", "mode": "chat", "local": False},
            {"id": "claude-sonnet", "label": "Claude Sonnet", "provider": "anthropic", "mode": "chat", "local": False},
            {"id": "claude-haiku", "label": "Claude Haiku", "provider": "anthropic", "mode": "chat", "local": False},
            {"id": "gemini-pro", "label": "Gemini Pro", "provider": "gemini", "mode": "chat", "local": False},
            {"id": "gemini-flash", "label": "Gemini Flash", "provider": "gemini", "mode": "chat", "local": False},
            {"id": "local-coder", "label": "On-device assistant", "provider": "local", "mode": "chat", "local": True},
            {"id": "openai-transcribe", "label": "OpenAI Transcription", "provider": "openai", "mode": "audio_transcription", "local": False},
            {"id": "local-whisper", "label": "Local Whisper", "provider": "local", "mode": "audio_transcription", "local": True},
            {"id": "openai-tts", "label": "OpenAI Voice", "provider": "openai", "mode": "audio_speech", "local": False},
            {"id": "local-kokoro", "label": "Local Voice", "provider": "local", "mode": "audio_speech", "local": True},
        ]

    @staticmethod
    def _catalogue_model(raw: dict) -> dict | None:
        model_id = str(raw.get("model_name") or "").strip()
        if not model_id:
            return None
        params = raw.get("litellm_params") or {}
        info = raw.get("model_info") or {}
        api_base = str(params.get("api_base") or "")
        hostname = (urllib.parse.urlparse(api_base).hostname or "").lower()
        local = hostname in {"localhost", "127.0.0.1", "::1"}
        provider = "local" if local else str(info.get("litellm_provider") or "unknown").lower()
        provider = {"vertex_ai": "gemini"}.get(provider, provider)
        labels = {
            "gpt-5.5": "GPT-5.5",
            "claude-opus": "Claude Opus",
            "claude-sonnet": "Claude Sonnet",
            "claude-haiku": "Claude Haiku",
            "gemini-pro": "Gemini Pro",
            "gemini-flash": "Gemini Flash",
            "local-small": "Legacy local route",
            "local-coder": "On-device assistant",
            "openai-transcribe": "OpenAI Transcription",
            "local-whisper": "Local Whisper",
            "openai-tts": "OpenAI Voice",
            "local-kokoro": "Local Voice",
        }
        return {
            "id": model_id,
            "label": info.get("display_name") or labels.get(model_id, model_id.replace("-", " ").title()),
            "provider": provider,
            "mode": str(info.get("mode") or "chat"),
            "local": local,
            "supports_vision": info.get("supports_vision", False),
        }

    def catalogue(self) -> dict:
        router_available = True
        detail = "Models are managed by the AI layer; hosted providers do not need an endpoint URL."
        try:
            raw_models = self._get_json("/v1/model/info").get("data") or []
            models = [model for value in raw_models if (model := self._catalogue_model(value))]
            if not models:
                raise RouterError("AI router returned an empty model catalogue")
        except RouterError as exc:
            router_available = False
            detail = str(exc)
            models = self._fallback_models()

        provider_labels = {
            "openai": "OpenAI",
            "anthropic": "Anthropic / Claude",
            "gemini": "Google / Gemini",
            "local": "Local models",
            "custom": "Custom endpoint",
        }
        provider_order = ("openai", "anthropic", "gemini", "local", "custom")
        providers = [
            {
                "id": provider,
                "label": provider_labels[provider],
                "requires_endpoint": provider == "custom",
            }
            for provider in provider_order
            if provider == "custom" or any(model["provider"] == provider and model["mode"] == "chat" for model in models)
        ]
        return {
            "router_available": router_available,
            "detail": detail,
            "providers": providers,
            "models": models,
            "voices": [
                {"id": "alloy", "label": "Alloy"},
                {"id": "echo", "label": "Echo"},
                {"id": "fable", "label": "Fable"},
                {"id": "onyx", "label": "Onyx"},
                {"id": "nova", "label": "Nova"},
                {"id": "shimmer", "label": "Shimmer"},
            ],
        }

    def _chat(self, messages: list[dict[str, object]], model: str) -> RouterResult:
        body = json.dumps(
            {
                "model": model,
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
        return RouterResult(text, latency, model, input_tokens, output_tokens)

    def chat(self, messages: list[dict[str, object]], temperature: float | None = None) -> RouterResult:
        return self._chat(messages, self.settings.text_model)

    def _structured(
        self,
        messages: list[dict[str, object]],
        model: str,
        schema: dict,
        *,
        name: str,
        max_tokens: int,
    ) -> RouterResult:
        """Request schema-constrained JSON, degrading for providers without json_schema support.

        llama.cpp turns ``json_schema`` into a GBNF grammar, so the local model
        cannot emit malformed or out-of-schema output.  Hosted OpenAI-compatible
        services use the same standard field.  Endpoints that reject it are
        retried with ``json_object`` and finally with prompt-only JSON; callers
        still validate the result strictly.
        """
        formats: list[dict | None] = [
            {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
            {"type": "json_object"},
            None,
        ]
        last_error: RouterError | None = None
        for response_format in formats:
            body: dict[str, object] = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0,
            }
            if response_format is not None:
                body["response_format"] = response_format
            started = time.perf_counter()
            try:
                payload, _, _ = self._request("/v1/chat/completions", json.dumps(body).encode("utf-8"), "application/json")
            except RouterError as exc:
                detail = str(exc).lower()
                unsupported = "http 400" in detail or "http 422" in detail
                if response_format is not None and unsupported and any(
                    marker in detail for marker in ("response_format", "json_schema", "json_object", "schema", "grammar", "unsupported", "not supported")
                ):
                    last_error = exc
                    continue
                raise
            latency = round((time.perf_counter() - started) * 1000)
            try:
                response = json.loads(payload)
                content = response["choices"][0]["message"]["content"]
                if isinstance(content, list):
                    content = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
                text = str(content or "").strip()
                usage = response.get("usage") or {}
                input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise RouterError("AI router returned an invalid chat completion") from exc
            if not text:
                raise RouterError("AI router returned an empty chat completion")
            with self._usage_lock:
                self._chat_calls += 1
                self._input_tokens += input_tokens or max(1, sum(len(str(m.get("content", ""))) for m in messages) // 4)
                self._output_tokens += output_tokens or max(1, len(text) // 4)
            return RouterResult(text, latency, model, input_tokens, output_tokens)
        raise last_error or RouterError("AI router rejected every structured-output format")

    def chat_structured(
        self,
        messages: list[dict[str, object]],
        schema: dict,
        *,
        name: str = "structured_reply",
        max_tokens: int = 320,
    ) -> RouterResult:
        return self._structured(messages, self.settings.text_model, schema, name=name, max_tokens=max_tokens)

    def vision_structured(
        self,
        prompt: str,
        images: list[tuple[bytes, str]],
        schema: dict,
        *,
        name: str = "structured_reply",
        max_tokens: int = 320,
    ) -> RouterResult:
        """Schema-constrained multimodal request; text-only profiles use the structured state alone."""
        if self.settings.vision_model == "local-no-vision" or not images:
            return self.chat_structured([
                {"role": "system", "content": "Use only the structured game state below. No images are available; do not invent visual details."},
                {"role": "user", "content": prompt},
            ], schema, name=name, max_tokens=max_tokens)
        content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        for image, media_type in images[:MAX_IMAGES]:
            encoded = base64.b64encode(image).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}", "detail": "high"}})
        try:
            result = self._structured([{"role": "user", "content": content}], self.settings.vision_model, schema,
                                      name=name, max_tokens=max_tokens)
        except RouterError as exc:
            if "not a multimodal model" not in str(exc).lower():
                raise
            return self.chat_structured([{"role": "user", "content": prompt}], schema, name=name, max_tokens=max_tokens)
        return replace(result, vision_used=True)

    def vision(self, prompt: str, image: bytes, media_type: str = "image/png") -> RouterResult:
        if self.settings.vision_model == "local-no-vision":
            raise RouterError("The lightweight AI profile uses game state, not map images. Choose Balanced for image analysis.")
        return self._vision_many(prompt, [(image, media_type)])

    def vision_many(self, prompt: str, images: list[tuple[bytes, str]]) -> RouterResult:
        if self.settings.vision_model == "local-no-vision":
            return self.chat([
                {"role": "system", "content": "Use only the structured game state below. No images are available; do not invent visual details."},
                {"role": "user", "content": prompt},
            ])
        try:
            return self._vision_many(prompt, images)
        except RouterError as exc:
            # Local text models still receive the complete structured game
            # snapshot. If the selected route cannot consume pixels, preserve
            # useful local intelligence instead of degrading the whole answer.
            if "not a multimodal model" not in str(exc).lower():
                raise
            return self.chat([
                {
                    "role": "system",
                    "content": (
                        "Image input is unavailable for this local text model. "
                        "Use only the structured battlefield snapshot in the prompt, "
                        "and do not invent details from the omitted images."
                    ),
                },
                {"role": "user", "content": prompt},
            ])

    def _vision_many(self, prompt: str, images: list[tuple[bytes, str]]) -> RouterResult:
        if not images or any(not image for image, _ in images):
            raise ValueError("at least one non-empty image is required")
        content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        for image, media_type in images[:MAX_IMAGES]:
            encoded = base64.b64encode(image).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{encoded}",
                    "detail": "high",
                },
            })
        result = self._chat([
            {
                "role": "user",
                "content": content,
            }
        ], self.settings.vision_model)
        return replace(result, vision_used=True)

    def transcribe(self, audio: bytes, filename: str = "question.wav") -> RouterResult:
        boundary = f"----OpenRAAI{uuid.uuid4().hex}"
        chunks = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{self.settings.transcribe_model}\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\n{self.settings.transcribe_language}\r\n".encode(),
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
        if model.lower().startswith("local-"):
            return 0.0, 0.0, "Local router model: $0 provider cost"
        prices = {
            "gpt-5.5": (5.0, 30.0, "GPT-5.5 public token rates"),
            HOSTED_MODEL: (1.0, 5.0, "Claude Haiku 4.5 list price ($1 / $5 per 1M tokens) via the RTS AI proxy"),
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

        local_text = self.settings.text_model.lower().startswith("local-")
        local_speech = self.settings.speech_model.lower() == "local-kokoro"
        speech_known = local_speech or self.settings.speech_model.lower() in {"openai-tts", "tts-1"}
        speech_rate = 0.0 if local_speech else 15.0 if speech_known else 0.0
        speech_cost = speech_characters / 1_000_000 * speech_rate

        local_transcription = self.settings.transcribe_model.lower() == "local-whisper"
        transcription_known = local_transcription or self.settings.transcribe_model.lower() in {"openai-transcribe", "whisper-1"}
        transcription_rate = 0.0 if local_transcription else 0.006 if transcription_known else 0.0
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
            "pricing_known": (input_rate > 0 or local_text) and speech_known and transcription_known,
            "assumptions": [
                text_assumption,
                "Local Kokoro route: $0 provider cost" if local_speech else "openai-tts estimated at TTS-1: $15 / 1M characters" if speech_known else f"No public price mapping for {self.settings.speech_model}",
                "Local Whisper route: $0 provider cost" if local_transcription else "openai-transcribe estimated at Whisper: $0.006 / minute" if transcription_known else f"No public price mapping for {self.settings.transcribe_model}",
            ],
            "estimate_only": True,
        }

    def health(self) -> dict[str, str | bool]:
        endpoint = "/v1/models" if self.settings.model_provider == "custom" else "/health/liveliness"
        request = urllib.request.Request(f"{self.settings.router_url}{endpoint}", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return {"reachable": response.status < 500, "url": self.settings.router_url}
        except OSError:
            return {"reachable": False, "url": self.settings.router_url}
