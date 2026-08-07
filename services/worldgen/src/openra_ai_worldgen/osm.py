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


def _feature_kind(tags: dict[str, str]) -> str | None:
    if tags.get("natural") in {"water", "coastline", "bay"}:
        return "water"
    if "waterway" in tags:
        return "river"
    if tags.get("highway") in {
        "motorway", "trunk", "primary", "secondary", "tertiary", "residential"
    }:
        return "road"
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
        features.append(GeoFeature(kind, points, closed, tags.get("name", "")))
    return features


def load_fixture(path: Path) -> list[GeoFeature]:
    return parse_overpass(json.loads(path.read_text(encoding="utf-8")))


def fetch_features(selection: GeoSelection, timeout: float = 18.0) -> list[GeoFeature]:
    query = f"""[out:json][timeout:15];
(
  way(around:{selection.radius_m},{selection.latitude},{selection.longitude})[natural~\"water|coastline|bay\"];
  way(around:{selection.radius_m},{selection.latitude},{selection.longitude})[waterway];
  way(around:{selection.radius_m},{selection.latitude},{selection.longitude})[highway~\"motorway|trunk|primary|secondary|tertiary|residential\"];
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
