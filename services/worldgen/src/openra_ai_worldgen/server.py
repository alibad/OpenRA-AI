from __future__ import annotations

import json
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .generator import MissionGenerator
from .models import GeoSelection


class WorldgenHandler(BaseHTTPRequestHandler):
    server_version = "OpenRAAIWorldgen/0.1"

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._json(HTTPStatus.OK, {"ok": True, "service": "worldgen", "version": "0.1.0"})
            return
        if path.startswith("/v1/missions/"):
            name = Path(path).name
            candidate = Path(self.server.output_directory) / name  # type: ignore[attr-defined]
            if candidate.is_file() and candidate.suffix == ".oramap":
                body = candidate.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="{candidate.name}"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/v1/missions/generate":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 64_000:
                raise ValueError("request too large")
            payload = json.loads(self.rfile.read(size) or b"{}")
            selection = GeoSelection(
                latitude=float(payload["latitude"]),
                longitude=float(payload["longitude"]),
                title=str(payload.get("title", "Earth Skirmish")),
                radius_m=int(payload.get("radius_m", 3500)),
                map_size=int(payload.get("map_size", 64)),
                seed=int(payload.get("seed", 1)),
                source=str(payload.get("source", "openstreetmap")),
                story_seed=str(payload.get("story_seed", "")),
            )
            result = MissionGenerator(allow_network=True).generate(
                selection, Path(self.server.output_directory)  # type: ignore[attr-defined]
            )
            response = result.as_dict()
            response["download_url"] = f"/v1/missions/{result.package_path.name}"
            self._json(HTTPStatus.CREATED, response)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request", "detail": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"worldgen: {fmt % args}")


def serve(host: str = "127.0.0.1", port: int = 8788, output_directory: Path | None = None) -> None:
    directory = output_directory or Path(tempfile.gettempdir()) / "openra-ai-missions"
    directory.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), WorldgenHandler)
    server.output_directory = str(directory)  # type: ignore[attr-defined]
    print(f"OpenRA AI worldgen listening on http://{host}:{port}")
    server.serve_forever()
