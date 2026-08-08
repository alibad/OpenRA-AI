from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from collections import Counter

from .models import GeoSelection, TerrainAnalysis
from .osm import GeoFeature
from .terrain import TerrainView


class TerrainAnalyzer:
    def __init__(self, companion_url: str, timeout: float = 35.0):
        self.companion_url = companion_url.rstrip("/")
        self.timeout = timeout

    def analyze(self, selection: GeoSelection, features: list[GeoFeature], view: TerrainView) -> TerrainAnalysis:
        kinds = Counter(feature.kind for feature in features)
        context = {
            "location": selection.location_name,
            "coordinates": [selection.latitude, selection.longitude],
            "radius_m": selection.radius_m,
            "generation_mode": selection.generation_mode,
            "terrain_view": view.metadata(),
            "osm_feature_counts": dict(kinds),
        }
        body = json.dumps({
            "context": context,
            "image_base64": base64.b64encode(view.image).decode("ascii"),
        }).encode("utf-8")
        request = urllib.request.Request(
            self.companion_url + "/v1/design/terrain",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"terrain vision route unavailable: {exc}") from exc
        return TerrainAnalysis.from_dict(payload)

