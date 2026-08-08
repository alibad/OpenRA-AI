from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .core import Companion
from .models import GameSnapshot
from .router import RouterError
from .voice import AudioPlayer, record_question
from .webui import AI_CONSOLE_HTML


class CompanionHandler(BaseHTTPRequestHandler):
    server_version = "OpenRAAICompanion/0.1"

    @property
    def companion(self) -> Companion:
        return self.server.companion  # type: ignore[attr-defined]

    @property
    def player(self) -> AudioPlayer:
        return self.server.player  # type: ignore[attr-defined]

    def _headers(self, status: int, content_type: str, length: int, **extra: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Access-Control-Allow-Origin", "http://localhost:3000")
        for key, value in extra.items():
            self.send_header(key.replace("_", "-"), value)
        self.end_headers()

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._headers(status, "application/json", len(body))
        self.wfile.write(body)

    def _html(self, value: str) -> None:
        body = value.encode("utf-8")
        self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body))
        self.wfile.write(body)

    def _payload(self, limit: int = 256_000) -> bytes:
        size = int(self.headers.get("Content-Length", "0"))
        if size > limit:
            raise ValueError("request too large")
        return self.rfile.read(size)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "http://localhost:3000")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            self._html(AI_CONSOLE_HTML)
        elif path == "/health":
            self._json(HTTPStatus.OK, self.companion.status())
        elif path == "/v1/config":
            self._json(HTTPStatus.OK, self.companion.router.settings.as_dict())
        elif path in {"/v1/state", "/v1/usage"}:
            state = {
                "enabled": self.companion.enabled,
                "voice_enabled": not self.companion.muted,
                "config": self.companion.router.settings.as_dict(),
                "usage": self.companion.router.usage_summary(),
                "router": self.companion.router.health(),
            }
            self._json(HTTPStatus.OK, state if path == "/v1/state" else state["usage"])
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/v1/config":
                payload = json.loads(self._payload() or b"{}")
                config = self.companion.router.configure(payload)
                self.companion.apply_settings()
                self._json(HTTPStatus.OK, config)
            elif path == "/v1/state":
                payload = json.loads(self._payload() or b"{}")
                config_values = dict(payload.get("config") or {})
                for key in (
                    "router_url", "text_model", "transcribe_model", "speech_model", "speech_voice",
                    "notification_pace", "voice_priority", "companion_enabled", "voice_enabled",
                ):
                    if key in payload:
                        config_values[key] = payload[key]
                self.companion.router.configure(config_values)
                self.companion.apply_settings()
                if self.companion.muted:
                    self.player.stop()
                publisher = getattr(self.server, "status_publisher", None)
                if publisher:
                    try:
                        publisher(*self.companion.idle_status())
                    except Exception:
                        pass
                self._json(HTTPStatus.OK, {
                    "enabled": self.companion.enabled,
                    "voice_enabled": not self.companion.muted,
                    "config": self.companion.router.settings.as_dict(),
                    "usage": self.companion.router.usage_summary(),
                    "router": self.companion.router.health(),
                })
            elif path == "/v1/test/connection":
                self._payload()
                health = self.companion.router.health()
                self._json(HTTPStatus.OK if health["reachable"] else HTTPStatus.BAD_GATEWAY, health)
            elif path == "/v1/test/chat":
                self._payload()
                result = self.companion.router.chat([
                    {"role": "system", "content": "Reply with one short sentence confirming the OpenRA AI companion is operational."},
                    {"role": "user", "content": "Run the companion diagnostic."},
                ])
                self._json(HTTPStatus.OK, {"ok": True, "model": result.model, "latency_ms": result.latency_ms, "text": result.text})
            elif path == "/v1/test/microphone":
                self._payload()
                result = self.companion.transcribe(record_question(3.0))
                self._json(HTTPStatus.OK, {"ok": True, "model": result.metadata.get("model"), "latency_ms": result.latency_ms, "transcript": result.text})
            elif path == "/v1/test/speech":
                self._payload()
                audio, metadata = self.companion.speech("OpenRA AI speech route is operational.")
                self.player.play(audio)
                self._json(HTTPStatus.OK, {"ok": bool(audio), **metadata})
            elif path == "/v1/test/full":
                self._payload()
                health = self.companion.router.health()
                if not health["reachable"]:
                    raise RouterError(f"AI layer is unavailable at {health['url']}")
                result = self.companion.router.chat([
                    {"role": "system", "content": "Reply with one short sentence confirming the OpenRA AI companion is operational."},
                    {"role": "user", "content": "Run the full companion diagnostic."},
                ])
                audio, speech = self.companion.speech(result.text)
                self.player.play(audio)
                self._json(HTTPStatus.OK, {
                    "ok": bool(audio),
                    "connection": health,
                    "text": {"model": result.model, "latency_ms": result.latency_ms, "response": result.text},
                    "speech": speech,
                    "microphone": "Run the separate microphone test to verify live input.",
                })
            elif path == "/v1/observe":
                response = self.companion.observe(GameSnapshot.from_dict(json.loads(self._payload() or b"{}")))
                self._json(HTTPStatus.OK, {"speak": response is not None, "response": response.as_dict() if response else None})
            elif path == "/v1/ask":
                payload = json.loads(self._payload() or b"{}")
                self._json(HTTPStatus.OK, self.companion.ask(str(payload.get("question", ""))).as_dict())
            elif path == "/v1/interrupt":
                self._payload()
                self._json(HTTPStatus.OK, {"interrupted": True, "generation": self.companion.interrupt()})
            elif path == "/v1/control":
                payload = json.loads(self._payload() or b"{}")
                state = self.companion.configure(enabled=payload.get("enabled"), muted=payload.get("muted"), persist=True)
                if state["muted"]:
                    self.player.stop()
                publisher = getattr(self.server, "status_publisher", None)
                if publisher:
                    try:
                        publisher(*self.companion.idle_status())
                    except Exception:
                        pass
                self._json(HTTPStatus.OK, state)
            elif path == "/v1/transcribe":
                query = parse_qs(urlparse(self.path).query)
                filename = query.get("filename", ["question.wav"])[0]
                self._json(HTTPStatus.OK, self.companion.transcribe(self._payload(20_000_000), filename).as_dict())
            elif path == "/v1/speak":
                payload = json.loads(self._payload() or b"{}")
                audio, metadata = self.companion.speech(str(payload.get("text", "")))
                if metadata.get("interrupted"):
                    self._json(HTTPStatus.CONFLICT, metadata)
                else:
                    self._headers(HTTPStatus.OK, str(metadata.get("content_type", "audio/wav")), len(audio), X_OpenRA_AI_Utterance=str(metadata["utterance_id"]))
                    self.wfile.write(audio)
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request", "detail": str(exc)})
        except RouterError as exc:
            self._json(HTTPStatus.BAD_GATEWAY, {"error": "ai_router_error", "detail": str(exc)})
        except Exception as exc:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "diagnostic_failed", "detail": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"companion: {fmt % args}")


def create_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    companion: Companion | None = None,
    player: AudioPlayer | None = None,
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), CompanionHandler)
    server.companion = companion or Companion()  # type: ignore[attr-defined]
    server.player = player or AudioPlayer()  # type: ignore[attr-defined]
    server.status_publisher = None  # type: ignore[attr-defined]
    return server


def serve(host: str = "127.0.0.1", port: int = 8787, companion: Companion | None = None) -> None:
    server = create_server(host, port, companion)
    print(f"OpenRA AI companion listening on http://{host}:{port}")
    server.serve_forever()
