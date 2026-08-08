from __future__ import annotations

import io
import math
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image

from .models import GeoSelection

USER_AGENT = "OpenRA-AI/0.2 (+https://github.com/alibad/OpenRA-AI)"
TERRAIN_TILE_URL = "https://tile.opentopomap.org/{zoom}/{x}/{y}.png"


@dataclass(frozen=True)
class TerrainView:
    image: bytes
    zoom: int
    provider: str = "OpenTopoMap"
    attribution: str = "Map data © OpenStreetMap contributors, SRTM | Map style © OpenTopoMap (CC-BY-SA)"

    def metadata(self) -> dict[str, str | int]:
        return {
            "provider": self.provider,
            "attribution": self.attribution,
            "zoom": self.zoom,
        }


def _world_pixel(latitude: float, longitude: float, zoom: int) -> tuple[float, float]:
    scale = 256 * (1 << zoom)
    latitude = max(-85.051129, min(85.051129, latitude))
    x = (longitude + 180.0) / 360.0 * scale
    y = (1.0 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2.0 * scale
    return x, y


def _zoom_for_radius(selection: GeoSelection, output_size: int) -> int:
    desired_mpp = (selection.radius_m * 2) / output_size
    zoom = round(math.log2(156543.03392 * max(0.15, math.cos(math.radians(selection.latitude))) / desired_mpp))
    return max(5, min(16, zoom))


def _tile(cache_root: Path, zoom: int, x: int, y: int) -> bytes:
    scale = 1 << zoom
    x %= scale
    y = max(0, min(scale - 1, y))
    path = cache_root / "terrain-tile-cache" / str(zoom) / str(x) / f"{y}.png"
    age = time.time() - path.stat().st_mtime if path.exists() else float("inf")
    if age < 7 * 24 * 60 * 60:
        return path.read_bytes()

    request = Request(
        TERRAIN_TILE_URL.format(zoom=zoom, x=x, y=y),
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=15) as response:
        body = response.read(1_500_001)
    if len(body) > 1_500_000 or not body.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("terrain tile service returned an invalid image")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def fetch_terrain_view(selection: GeoSelection, cache_root: Path, output_size: int = 512) -> TerrainView:
    zoom = _zoom_for_radius(selection, output_size)
    center_x, center_y = _world_pixel(selection.latitude, selection.longitude, zoom)
    meters_per_pixel = 156543.03392 * max(0.15, math.cos(math.radians(selection.latitude))) / (1 << zoom)
    source_span = max(256, min(744, round(selection.radius_m * 2 / meters_per_pixel)))
    half = source_span / 2
    min_tile_x = math.floor((center_x - half) / 256)
    max_tile_x = math.floor((center_x + half) / 256)
    min_tile_y = math.floor((center_y - half) / 256)
    max_tile_y = math.floor((center_y + half) / 256)

    canvas = Image.new("RGB", ((max_tile_x - min_tile_x + 1) * 256, (max_tile_y - min_tile_y + 1) * 256))
    for tile_y in range(min_tile_y, max_tile_y + 1):
        for tile_x in range(min_tile_x, max_tile_x + 1):
            with Image.open(io.BytesIO(_tile(cache_root, zoom, tile_x, tile_y))) as tile:
                canvas.paste(tile.convert("RGB"), ((tile_x - min_tile_x) * 256, (tile_y - min_tile_y) * 256))

    local_x = center_x - min_tile_x * 256
    local_y = center_y - min_tile_y * 256
    crop = canvas.crop((round(local_x - half), round(local_y - half), round(local_x + half), round(local_y + half)))
    crop = crop.resize((output_size, output_size), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    crop.save(output, format="PNG", optimize=True)
    return TerrainView(output.getvalue(), zoom)

