from __future__ import annotations

import json
import shutil
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from .generator import MissionGenerator
from .models import GeoSelection
from .webui import WORLD_STUDIO_HTML


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

    def _html(self, value: str) -> None:
        body = value.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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
        if path == "/":
            self._html(WORLD_STUDIO_HTML)
            return
        if path == "/health":
            self._json(HTTPStatus.OK, {"ok": True, "service": "worldgen", "version": "0.1.0"})
            return
        if path == "/v1/geocode":
            query = parse_qs(urlparse(self.path).query).get("query", [""])[0].strip()
            if not query:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "query_required"})
                return
            try:
                request = Request(
                    "https://nominatim.openstreetmap.org/search?" + urlencode({"q": query, "format": "jsonv2", "limit": 1}),
                    headers={"User-Agent": "OpenRA-AI/0.1 local mission generator"},
                )
                with urlopen(request, timeout=12) as response:
                    matches = json.loads(response.read())
                if not matches:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "location_not_found"})
                    return
                match = matches[0]
                self._json(HTTPStatus.OK, {
                    "name": match.get("display_name", query),
                    "latitude": float(match["lat"]),
                    "longitude": float(match["lon"]),
                })
            except (OSError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_GATEWAY, {"error": "geocoding_failed", "detail": str(exc)})
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
            install_directory = Path(self.server.install_directory)  # type: ignore[attr-defined]
            install_directory.mkdir(parents=True, exist_ok=True)
            installed_path = install_directory / result.package_path.name
            shutil.copy2(result.package_path, installed_path)
            response = result.as_dict()
            response["download_url"] = f"/v1/missions/{result.package_path.name}"
            response["filename"] = result.package_path.name
            response["installed_path"] = str(installed_path)
            self._json(HTTPStatus.CREATED, response)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request", "detail": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"worldgen: {fmt % args}")


def create_server(
    host: str = "127.0.0.1",
    port: int = 8788,
    output_directory: Path | None = None,
    install_directory: Path | None = None,
) -> ThreadingHTTPServer:
    directory = output_directory or Path(tempfile.gettempdir()) / "openra-ai-missions"
    directory.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), WorldgenHandler)
    server.output_directory = str(directory)  # type: ignore[attr-defined]
    server.install_directory = str(install_directory or directory)  # type: ignore[attr-defined]
    return server


def serve(host: str = "127.0.0.1", port: int = 8788, output_directory: Path | None = None) -> None:
    server = create_server(host, port, output_directory)
    print(f"OpenRA AI worldgen listening on http://{host}:{port}")
    server.serve_forever()
