from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import GeoSelection

OVERPASS_URLS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
USER_AGENT = "OpenRA-AI/0.1 (+https://github.com/alibad/OpenRA-AI)"


@dataclass(frozen=True)
class GeoFeature:
    kind: str
    points: tuple[tuple[float, float], ...]
    closed: bool = False
    name: str = ""
    tags: tuple[tuple[str, str], ...] = ()


def _feature_kind(tags: dict[str, str]) -> str | None:
    if tags.get("natural") in {"water", "coastline", "bay"}:
        return "water"
    if "waterway" in tags:
        if tags.get("intermittent") in {"yes", "seasonal"}:
            return "dry-river"
        return "river"
    if tags.get("highway") in {"motorway", "trunk", "primary", "secondary"}:
        return "road"
    if tags.get("highway") in {"tertiary", "residential"}:
        return "local-road"
    if "railway" in tags:
        return "rail"
    if "building" in tags:
        return "building"
    if tags.get("landuse") in {"residential", "commercial", "industrial", "retail", "construction"}:
        return "urban"
    if tags.get("natural") in {"wood", "scrub", "grassland"} or tags.get("landuse") in {"forest", "meadow", "orchard"}:
        return "forest"
    if tags.get("leisure") in {"park", "garden", "nature_reserve"}:
        return "forest"
    if tags.get("natural") in {"bare_rock", "scree", "shingle", "cliff"} or tags.get("landuse") == "quarry":
        return "rough"
    if tags.get("natural") in {"sand", "beach", "dune"}:
        return "sand"
    return None


def parse_overpass(payload: dict[str, Any]) -> list[GeoFeature]:
    features: list[GeoFeature] = []
    for element in payload.get("elements", []):
        geometry = element.get("geometry") or []
        if len(geometry) < 2:
            continue
        tags = element.get("tags") or {}
        kind = _feature_kind(tags)
        if not kind:
            continue
        points = tuple((float(p["lat"]), float(p["lon"])) for p in geometry)
        closed = len(points) > 3 and points[0] == points[-1]
        features.append(GeoFeature(kind, points, closed, tags.get("name", ""), tuple(sorted(tags.items()))))
    return features


def load_fixture(path: Path) -> list[GeoFeature]:
    return parse_overpass(json.loads(path.read_text(encoding="utf-8")))


def fetch_features(selection: GeoSelection, timeout: float = 18.0) -> list[GeoFeature]:
    latitude_delta = selection.radius_m / 111_320.0
    longitude_delta = selection.radius_m / (111_320.0 * max(0.15, math.cos(math.radians(selection.latitude))))
    bbox = (
        selection.latitude - latitude_delta,
        selection.longitude - longitude_delta,
        selection.latitude + latitude_delta,
        selection.longitude + longitude_delta,
    )
    box = ",".join(f"{value:.7f}" for value in bbox)
    query = f"""[out:json][timeout:15];
(
  way({box})[natural~\"water|coastline|bay\"];
  way({box})[waterway];
  way({box})[highway~\"motorway|trunk|primary|secondary|tertiary|residential\"];
  way({box})[railway];
  way({box})[building];
  way({box})[landuse~\"residential|commercial|industrial|retail|construction|forest|meadow|orchard|quarry\"];
  way({box})[natural~\"wood|scrub|grassland|bare_rock|scree|shingle|cliff|sand|beach|dune\"];
  way({box})[leisure~\"park|garden|nature_reserve\"];
);
out tags geom;"""
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    failures: list[str] = []
    for endpoint in OVERPASS_URLS:
        request = urllib.request.Request(
            endpoint,
            data=body,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return parse_overpass(payload)
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            failures.append(f"{urllib.parse.urlparse(endpoint).netloc}: {exc}")
    raise RuntimeError(f"OpenStreetMap acquisition failed across public Overpass instances: {'; '.join(failures)}")


def project_point(
    lat: float,
    lon: float,
    selection: GeoSelection,
    playable_min: int,
    playable_max: int,
) -> tuple[int, int]:
    radius = selection.radius_m
    north_m = (lat - selection.latitude) * 111_320.0
    east_m = (lon - selection.longitude) * 111_320.0 * max(
        0.15, math.cos(math.radians(selection.latitude))
    )
    span = playable_max - playable_min
    x = playable_min + round((east_m / (2 * radius) + 0.5) * span)
    y = playable_min + round((0.5 - north_m / (2 * radius)) * span)
    return (
        max(playable_min, min(playable_max, x)),
        max(playable_min, min(playable_max, y)),
    )
