from __future__ import annotations

import json
import math
import shutil
import tempfile
import threading
import time
import unicodedata
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from .ai import TerrainAnalyzer
from .generator import MissionGenerator
from .models import GeoSelection
from .terrain import fetch_terrain_view
from .webui import WORLD_STUDIO_HTML


def _uses_latin_script(value: str) -> bool:
    return bool(value.strip()) and all(
        not character.isalpha() or "LATIN" in unicodedata.name(character, "")
        for character in value
    )


def _readable_place_name(match: dict, query: str) -> str:
    native_name = str(match.get("display_name", "")).strip()
    english_name = str((match.get("namedetails") or {}).get("name:en", "")).strip()
    for candidate in (native_name, english_name, query):
        if _uses_latin_script(candidate):
            return candidate

    return "Selected Earth location"


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

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=604800")
        self.end_headers()
        self.wfile.write(body)

    def _generation_payload(self) -> dict:
        size = int(self.headers.get("Content-Length", "0"))
        if size > 64_000:
            raise ValueError("request too large")
        payload = json.loads(self.rfile.read(size) or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        return payload

    def _generate_mission(self, payload: dict, progress=None) -> dict:
        selection = GeoSelection(
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            title=str(payload.get("title", "Earth Skirmish")),
            location_name=str(payload.get("location_name", "Selected Earth location")),
            radius_m=int(payload.get("radius_m", 3500)),
            map_size=int(payload.get("map_size", 64)),
            seed=int(payload.get("seed", 1)),
            source=str(payload.get("source", "openstreetmap")),
            story_seed=str(payload.get("story_seed", "")),
            generation_mode=str(payload.get("generation_mode", "reality-first")),
        )
        analyzer = TerrainAnalyzer(self.server.companion_url) if self.server.companion_url else None  # type: ignore[attr-defined]
        result = MissionGenerator(allow_network=True, terrain_analyzer=analyzer).generate(
            selection,
            Path(self.server.output_directory),  # type: ignore[attr-defined]
            progress=progress,
        )
        install_directory = Path(self.server.install_directory)  # type: ignore[attr-defined]
        install_directory.mkdir(parents=True, exist_ok=True)
        installed_path = install_directory / result.package_path.name
        shutil.copy2(result.package_path, installed_path)
        response = result.as_dict()
        response["download_url"] = f"/v1/missions/{result.package_path.name}"
        response["filename"] = result.package_path.name
        response["installed_path"] = str(installed_path)
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        response["synthesis"] = {
            "analysis": manifest.get("analysis", {}),
            "feature_counts": manifest.get("design", {}).get("feature_counts", {}),
            "terrain_view": manifest.get("terrain_view", {}),
            "tileset": manifest.get("game", {}).get("tileset", "TEMPERAT"),
        }
        return response

    def _set_job(self, job_id: str, **values) -> None:
        with self.server.generation_jobs_lock:  # type: ignore[attr-defined]
            job = self.server.generation_jobs.get(job_id)  # type: ignore[attr-defined]
            if job is not None:
                job.update(values)

    def _run_generation_job(self, job_id: str, payload: dict) -> None:
        def progress(stage: int, message: str) -> None:
            self._set_job(job_id, state="running", stage=stage, message=message)

        try:
            result = self._generate_mission(payload, progress)
            self._set_job(
                job_id,
                state="succeeded",
                stage=6,
                message="Playable battlefield is ready",
                result=result,
            )
        except Exception as exc:  # The polling client receives a structured failure.
            self._set_job(job_id, state="failed", message=str(exc), error=type(exc).__name__)

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
                    "https://nominatim.openstreetmap.org/search?" + urlencode(
                        {
                            "q": query,
                            "format": "jsonv2",
                            "limit": 1,
                            "accept-language": "en",
                            "namedetails": 1,
                        }
                    ),
                    headers={
                        "User-Agent": "OpenRA-AI/0.1 local mission generator",
                        "Accept-Language": "en",
                    },
                )
                with urlopen(request, timeout=12) as response:
                    matches = json.loads(response.read())
                if not matches:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "location_not_found"})
                    return
                match = matches[0]
                self._json(HTTPStatus.OK, {
                    "name": _readable_place_name(match, query),
                    "native_name": match.get("display_name", query),
                    "latitude": float(match["lat"]),
                    "longitude": float(match["lon"]),
                })
            except (OSError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_GATEWAY, {"error": "geocoding_failed", "detail": str(exc)})
            return
        if path == "/v1/map-tile":
            query = parse_qs(urlparse(self.path).query)
            try:
                latitude = float(query.get("latitude", [""])[0])
                longitude = float(query.get("longitude", [""])[0])
                zoom = int(query.get("zoom", ["11"])[0])
                if not -85.051129 <= latitude <= 85.051129 or not -180 <= longitude <= 180:
                    raise ValueError("coordinates are outside Web Mercator bounds")
                if not 4 <= zoom <= 16:
                    raise ValueError("zoom must be between 4 and 16")

                scale = 1 << zoom
                tile_x = int((longitude + 180.0) / 360.0 * scale)
                latitude_radians = math.radians(latitude)
                tile_y = int((1.0 - math.asinh(math.tan(latitude_radians)) / math.pi) / 2.0 * scale)
                tile_x = max(0, min(scale - 1, tile_x))
                tile_y = max(0, min(scale - 1, tile_y))

                cache = Path(self.server.output_directory) / "tile-cache" / str(zoom) / str(tile_x)  # type: ignore[attr-defined]
                cache.mkdir(parents=True, exist_ok=True)
                tile_path = cache / f"{tile_y}.png"
                cache_age = time.time() - tile_path.stat().st_mtime if tile_path.exists() else float("inf")
                if cache_age >= 7 * 24 * 60 * 60:
                    tile_url = f"https://tile.openstreetmap.org/{zoom}/{tile_x}/{tile_y}.png"
                    request = Request(
                        tile_url,
                        headers={"User-Agent": "OpenRA-AI/0.1 (+https://github.com/alibad/OpenRA-AI)"},
                    )
                    with urlopen(request, timeout=12) as response:
                        body = response.read(1_000_001)
                    if len(body) > 1_000_000 or not body.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise ValueError("tile server returned an invalid image")
                    tile_path.write_bytes(body)

                self._bytes(HTTPStatus.OK, tile_path.read_bytes(), "image/png")
            except (OSError, TimeoutError, ValueError) as exc:
                self._json(HTTPStatus.BAD_GATEWAY, {"error": "map_tile_failed", "detail": str(exc)})
            return
        if path == "/v1/terrain-view":
            query = parse_qs(urlparse(self.path).query)
            try:
                selection = GeoSelection(
                    latitude=float(query.get("latitude", [""])[0]),
                    longitude=float(query.get("longitude", [""])[0]),
                    radius_m=int(query.get("radius_m", ["3500"])[0]),
                ).validated()
                view = fetch_terrain_view(selection, Path(self.server.output_directory))  # type: ignore[attr-defined]
                self._bytes(HTTPStatus.OK, view.image, "image/png")
            except (OSError, TimeoutError, ValueError) as exc:
                self._json(HTTPStatus.BAD_GATEWAY, {"error": "terrain_view_failed", "detail": str(exc)})
            return
        if path.startswith("/v1/jobs/"):
            job_id = Path(path).name
            with self.server.generation_jobs_lock:  # type: ignore[attr-defined]
                job = self.server.generation_jobs.get(job_id)  # type: ignore[attr-defined]
                snapshot = dict(job) if job is not None else None
            if snapshot is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
            else:
                self._json(HTTPStatus.OK, snapshot)
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
        path = urlparse(self.path).path
        if path not in {"/v1/missions/generate", "/v1/missions/generate-async"}:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            payload = self._generation_payload()
            if path == "/v1/missions/generate-async":
                job_id = uuid.uuid4().hex
                with self.server.generation_jobs_lock:  # type: ignore[attr-defined]
                    jobs = self.server.generation_jobs  # type: ignore[attr-defined]
                    while len(jobs) >= 32:
                        jobs.pop(next(iter(jobs)))
                    jobs[job_id] = {
                        "id": job_id,
                        "state": "queued",
                        "stage": 0,
                        "message": "Generation queued",
                    }
                threading.Thread(target=self._run_generation_job, args=(job_id, payload), daemon=True).start()
                self._json(HTTPStatus.ACCEPTED, {"job_id": job_id, "poll_url": f"/v1/jobs/{job_id}"})
            else:
                self._json(HTTPStatus.CREATED, self._generate_mission(payload))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_request", "detail": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"worldgen: {fmt % args}")


def create_server(
    host: str = "127.0.0.1",
    port: int = 8788,
    output_directory: Path | None = None,
    install_directory: Path | None = None,
    companion_url: str | None = None,
) -> ThreadingHTTPServer:
    directory = output_directory or Path(tempfile.gettempdir()) / "openra-ai-missions"
    directory.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), WorldgenHandler)
    server.output_directory = str(directory)  # type: ignore[attr-defined]
    server.install_directory = str(install_directory or directory)  # type: ignore[attr-defined]
    server.companion_url = companion_url  # type: ignore[attr-defined]
    server.generation_jobs = {}  # type: ignore[attr-defined]
    server.generation_jobs_lock = threading.Lock()  # type: ignore[attr-defined]
    return server


def serve(host: str = "127.0.0.1", port: int = 8788, output_directory: Path | None = None) -> None:
    server = create_server(host, port, output_directory)
    print(f"OpenRA AI worldgen listening on http://{host}:{port}")
    server.serve_forever()
