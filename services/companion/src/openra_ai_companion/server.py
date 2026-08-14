from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import Companion
from .learning import LearningStore, learning_dashboard
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

    def _binary(self, value: bytes, content_type: str, *, cache_control: str = "no-store") -> None:
        self._headers(HTTPStatus.OK, content_type, len(value), Cache_Control=cache_control)
        self.wfile.write(value)

    def _publish_action_response(self, response: object) -> None:
        metadata = getattr(response, "metadata", {})
        action = metadata.get("action", {}) if isinstance(metadata, dict) else {}
        action_state = action.get("state") if isinstance(action, dict) else None
        state = {
            "pending": "action-pending",
            "executed": "action-executed",
            "cancelled": "action-cancelled",
            "rejected": "action-rejected",
            "failed": "action-rejected",
            "unavailable": "action-rejected",
            "expired": "action-rejected",
            "missing": "action-rejected",
        }.get(action_state)
        publisher = getattr(self.server, "status_publisher", None)
        if state and publisher:
            try:
                publisher(state, f"AI  •  {getattr(response, 'text', '')}")
            except Exception:
                pass

    def _state_payload(self) -> dict:
        return {
            "enabled": self.companion.enabled,
            "voice_enabled": not self.companion.muted,
            "auto_act_enabled": self.companion.auto_act_enabled,
            "pending_action": self.companion.pending_action(),
            "brain": self.companion.brain_state(),
            "snapshot": self.companion.latest_snapshot.compact() if self.companion.latest_snapshot else None,
            "threat": self.companion.threat_status(),
            "config": self.companion.router.settings.as_dict(),
            "usage": self.companion.router.usage_summary(),
            "router": self.companion.router.health(),
        }

    def _war_room_payload(self) -> dict:
        store = LearningStore()
        dashboard = store.dashboard()
        state = self._state_payload()
        return {
            "contract_version": 1,
            "live": {
                "active": state["snapshot"] is not None,
                "enabled": state["enabled"],
                "voice_enabled": state["voice_enabled"],
                "auto_act_enabled": state["auto_act_enabled"],
                "pending_action": state["pending_action"],
                "snapshot": state["snapshot"],
                "threat": state["threat"],
                "brain": state["brain"],
                "strategy": self.companion.status()["strategy"],
                "router": state["router"],
            },
            "debrief": store.latest(),
            "learning": dashboard,
            "settings": state["config"],
        }

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
        elif path == "/v1/catalog":
            self._json(HTTPStatus.OK, self.companion.router.catalogue())
        elif path == "/v1/learning":
            self._json(HTTPStatus.OK, learning_dashboard())
        elif path == "/v1/learning/latest":
            self._json(HTTPStatus.OK, LearningStore().latest())
        elif path == "/v1/war-room":
            self._json(HTTPStatus.OK, self._war_room_payload())
        elif path.startswith("/v1/learning/matches/"):
            parts = path.strip("/").split("/")
            attempt = parts[3] if len(parts) >= 4 else ""
            try:
                record = LearningStore().match(attempt)
            except ValueError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            if len(parts) == 4:
                self._json(HTTPStatus.OK if record else HTTPStatus.NOT_FOUND, record or {"error": "not_found"})
            elif len(parts) == 6 and parts[4] == "frames" and record:
                filename = parts[5]
                evidence_dir = Path(str(record.get("evidence_dir", ""))).resolve()
                frames_dir = (evidence_dir / "frames").resolve()
                frame = (frames_dir / filename).resolve()
                visual_evidence = record.get("visual_evidence", {})
                recent_frames = visual_evidence.get("recent_frames", []) if isinstance(visual_evidence, dict) else []
                known_frames = {
                    Path(str(item.get("file", ""))).name
                    for item in recent_frames
                    if isinstance(item, dict)
                }
                if (
                    filename in known_frames
                    and frame.parent == frames_dir
                    and frame.suffix.lower() == ".png"
                    and frame.is_file()
                ):
                    self._binary(frame.read_bytes(), "image/png", cache_control="private, max-age=300")
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "frame_not_found"})
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        elif path in {"/v1/state", "/v1/usage"}:
            state = self._state_payload()
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
                    "router_url", "model_provider", "text_model", "vision_model", "transcribe_model", "transcribe_language",
                    "speech_model", "speech_voice",
                    "notification_pace", "voice_priority", "companion_enabled", "voice_enabled", "auto_act_enabled", "native_strategy",
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
                    "auto_act_enabled": self.companion.auto_act_enabled,
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
                self.companion.begin_user_turn()
                try:
                    response = self.companion.handle_player_input(str(payload.get("question", "")))
                finally:
                    self.companion.end_user_turn()
                self._publish_action_response(response)
                self._json(HTTPStatus.OK, response.as_dict())
            elif path == "/v1/actions/propose":
                payload = json.loads(self._payload() or b"{}")
                self.companion.begin_user_turn()
                try:
                    response = self.companion.handle_player_input(str(payload.get("instruction", "")))
                finally:
                    self.companion.end_user_turn()
                self._publish_action_response(response)
                self._json(HTTPStatus.OK, response.as_dict())
            elif path == "/v1/actions/confirm":
                payload = json.loads(self._payload() or b"{}")
                response = self.companion.confirm_action(str(payload.get("proposal_id", "")))
                self._publish_action_response(response)
                self._json(HTTPStatus.OK, response.as_dict())
            elif path == "/v1/actions/cancel":
                payload = json.loads(self._payload() or b"{}")
                response = self.companion.cancel_action(str(payload.get("proposal_id", "")))
                self._publish_action_response(response)
                self._json(HTTPStatus.OK, response.as_dict())
            elif path == "/v1/design/mission":
                payload = json.loads(self._payload() or b"{}")
                self._json(HTTPStatus.OK, self.companion.draft_mission(payload).as_dict())
            elif path == "/v1/design/terrain":
                import base64

                payload = json.loads(self._payload(3_000_000) or b"{}")
                image = base64.b64decode(str(payload.get("image_base64", "")), validate=True)
                if not image.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("terrain image must be a PNG")
                self._json(HTTPStatus.OK, self.companion.analyze_terrain(dict(payload.get("context") or {}), image))
            elif path == "/v1/interrupt":
                self._payload()
                self._json(HTTPStatus.OK, {"interrupted": True, "generation": self.companion.interrupt()})
            elif path == "/v1/control":
                payload = json.loads(self._payload() or b"{}")
                state = self.companion.configure(
                    enabled=payload.get("enabled"),
                    muted=payload.get("muted"),
                    auto_act=payload.get("auto_act"),
                    native_strategy=payload.get("native_strategy"),
                    persist=True,
                )
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
            elif path in {"/v1/voice/start", "/v1/voice/stop"}:
                self._payload()
                controller = getattr(self.server, "voice_controller", None)
                if controller is None:
                    self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "voice_controller_unavailable"})
                else:
                    active = controller.start_question() if path.endswith("/start") else controller.stop_question()
                    self._json(HTTPStatus.OK, {"ok": True, "active": active})
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
    server.voice_controller = None  # type: ignore[attr-defined]
    return server


def serve(host: str = "127.0.0.1", port: int = 8787, companion: Companion | None = None) -> None:
    server = create_server(host, port, companion)
    print(f"OpenRA AI companion listening on http://{host}:{port}")
    server.serve_forever()
