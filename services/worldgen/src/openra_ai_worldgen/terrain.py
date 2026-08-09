from __future__ import annotations

import io
import math
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image, ImageOps

from .models import GeoSelection

USER_AGENT = "OpenRA-AI/0.2 (+https://github.com/alibad/OpenRA-AI)"
TERRAIN_TILE_URL = "https://tile.opentopomap.org/{zoom}/{x}/{y}.png"
SATELLITE_TILE_URL = (
    "https://a.tiles.maps.eox.at/wmts/1.0.0/"
    "s2cloudless-2025_3857/default/g/{zoom}/{y}/{x}.jpg"
)


@dataclass(frozen=True)
class TerrainView:
    image: bytes
    zoom: int
    provider: str = "OpenTopoMap"
    style: str = "terrain"
    attribution: str = "Map data © OpenStreetMap contributors, SRTM | Map style © OpenTopoMap (CC-BY-SA)"

    def metadata(self) -> dict[str, str | int]:
        return {
            "provider": self.provider,
            "attribution": self.attribution,
            "zoom": self.zoom,
            "style": self.style,
        }


def _world_pixel(latitude: float, longitude: float, zoom: int) -> tuple[float, float]:
    scale = 256 * (1 << zoom)
    latitude = max(-85.051129, min(85.051129, latitude))
    x = (longitude + 180.0) / 360.0 * scale
    y = (1.0 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2.0 * scale
    return x, y


def _zoom_for_radius(selection: GeoSelection, output_size: int, maximum_zoom: int = 16) -> int:
    desired_mpp = (selection.radius_m * 2) / output_size
    zoom = round(math.log2(156543.03392 * max(0.15, math.cos(math.radians(selection.latitude))) / desired_mpp))
    return max(5, min(maximum_zoom, zoom))


def _tile(cache_root: Path, zoom: int, x: int, y: int, style: str) -> bytes:
    scale = 1 << zoom
    x %= scale
    y = max(0, min(scale - 1, y))
    satellite = style == "satellite"
    extension = "jpg" if satellite else "png"
    path = cache_root / "earth-imagery-cache" / style / str(zoom) / str(x) / f"{y}.{extension}"
    age = time.time() - path.stat().st_mtime if path.exists() else float("inf")
    if age < 7 * 24 * 60 * 60:
        return path.read_bytes()

    request = Request(
        (SATELLITE_TILE_URL if satellite else TERRAIN_TILE_URL).format(zoom=zoom, x=x, y=y),
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=15) as response:
        body = response.read(1_500_001)
    valid_header = body.startswith(b"\xff\xd8\xff") if satellite else body.startswith(b"\x89PNG\r\n\x1a\n")
    if len(body) > 1_500_000 or not valid_header:
        raise ValueError(f"{style} tile service returned an invalid image")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def _render_source(
    selection: GeoSelection,
    cache_root: Path,
    output_size: int,
    style: str,
) -> tuple[Image.Image, int]:
    # The EOX WMTS advertises the Google-compatible matrix through zoom 21.
    # Sentinel-2 itself is still a ~10 m source, but requesting zoom 16 keeps
    # the crop faithful to a tactical 500 m radius instead of forcing a broad
    # district view. The UI reports the source-detail limit honestly.
    zoom = _zoom_for_radius(selection, output_size, maximum_zoom=16 if style == "satellite" else 17)
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
            with Image.open(io.BytesIO(_tile(cache_root, zoom, tile_x, tile_y, style))) as tile:
                canvas.paste(tile.convert("RGB"), ((tile_x - min_tile_x) * 256, (tile_y - min_tile_y) * 256))

    local_x = center_x - min_tile_x * 256
    local_y = center_y - min_tile_y * 256
    crop = canvas.crop((round(local_x - half), round(local_y - half), round(local_x + half), round(local_y + half)))
    crop = crop.resize((output_size, output_size), Image.Resampling.LANCZOS)
    return crop, zoom


def fetch_terrain_view(
    selection: GeoSelection,
    cache_root: Path,
    output_size: int = 512,
    style: str | None = None,
) -> TerrainView:
    requested_style = style or selection.imagery_style
    if requested_style not in {"auto", "hybrid", "satellite", "terrain"}:
        raise ValueError("imagery style must be auto, hybrid, satellite, or terrain")

    # Sentinel-2 is useful regional evidence, but its native ~10 m pixels do
    # not contain enough information for a 1-2 km tactical crop. Auto detail
    # therefore uses the legible street/building map at those ranges, then
    # returns to unmodified satellite imagery once the source has enough real
    # pixels. Hybrid remains available as an explicit visual option.
    resolved_style = requested_style
    if requested_style == "auto":
        resolved_style = "terrain" if selection.radius_m <= 1000 else "satellite"

    if resolved_style == "hybrid":
        satellite, satellite_zoom = _render_source(selection, cache_root, output_size, "satellite")
        mapped, map_zoom = _render_source(selection, cache_root, output_size, "terrain")
        # Use the map's distance from white as an alpha mask. This preserves
        # the satellite texture instead of washing the whole image with a
        # second raster, while drawing dark street edges, labels, and building
        # footprints strongly enough to remain useful at tactical scale.
        detail_mask = ImageOps.invert(ImageOps.grayscale(mapped)).point(lambda value: min(205, int(value * 0.9)))
        rendered = Image.composite(mapped, satellite, detail_mask)
        zoom = max(satellite_zoom, map_zoom)
    else:
        rendered, zoom = _render_source(selection, cache_root, output_size, resolved_style)

    output = io.BytesIO()
    rendered.save(output, format="PNG", optimize=True)
    if resolved_style == "hybrid":
        return TerrainView(
            output.getvalue(),
            zoom,
            provider="EOX Sentinel-2 + OpenTopoMap",
            attribution=(
                "EOxCloudless © EOX IT Services GmbH | modified Copernicus Sentinel data 2025 | "
                "OpenStreetMap contributors, SRTM | OpenTopoMap CC-BY-SA"
            ),
            style=resolved_style,
        )
    if resolved_style == "satellite":
        return TerrainView(
            output.getvalue(),
            zoom,
            provider="EOX Sentinel-2 Cloudless 2025",
            attribution="EOxCloudless © EOX IT Services GmbH | Contains modified Copernicus Sentinel data 2025",
            style=resolved_style,
        )
    return TerrainView(output.getvalue(), zoom, style=resolved_style)
