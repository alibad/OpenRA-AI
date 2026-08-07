from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .core import Companion
from .models import GameSnapshot
from .router import RouterError


class CompanionHandler(BaseHTTPRequestHandler):
    server_version = "OpenRAAICompanion/0.1"

    @property
    def companion(self) -> Companion:
        return self.server.companion  # type: ignore[attr-defined]

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
        if urlparse(self.path).path == "/health":
            self._json(HTTPStatus.OK, self.companion.status())
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/v1/observe":
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
                self._json(HTTPStatus.OK, self.companion.configure(enabled=payload.get("enabled"), muted=payload.get("muted")))
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
            self._json(HTTPStatus.BAD_GATEWAY, {"error": "betenshi_error", "detail": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"companion: {fmt % args}")


def serve(host: str = "127.0.0.1", port: int = 8787, companion: Companion | None = None) -> None:
    server = ThreadingHTTPServer((host, port), CompanionHandler)
    server.companion = companion or Companion()  # type: ignore[attr-defined]
    print(f"OpenRA AI companion listening on http://{host}:{port}")
    server.serve_forever()
