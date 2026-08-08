from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import time

from .ai import TerrainAnalyzer
from .models import GeoSelection, MissionResult, TerrainAnalysis
from .osm import GeoFeature, fetch_features, load_fixture
from .package import create_package
from .raster import build_terrain
from .terrain import TerrainView, fetch_terrain_view
from .validator import validate_package


class MissionGenerator:
    def __init__(
        self,
        fixture: Path | None = None,
        allow_network: bool = True,
        terrain_analyzer: TerrainAnalyzer | None = None,
    ):
        self.fixture = fixture
        self.allow_network = allow_network
        self.terrain_analyzer = terrain_analyzer

    def _features(self, selection: GeoSelection, output_directory: Path) -> tuple[list[GeoFeature], str]:
        if self.fixture:
            return load_fixture(self.fixture), "fixture"
        if self.allow_network and selection.source == "openstreetmap":
            cache = output_directory / "osm-cache" / (
                f"v3-{selection.latitude:.5f}-{selection.longitude:.5f}-{selection.radius_m}.json"
            )
            if cache.is_file() and time.time() - cache.stat().st_mtime < 7 * 24 * 60 * 60:
                try:
                    values = json.loads(cache.read_text(encoding="utf-8"))
                    return [
                        GeoFeature(
                            str(value["kind"]),
                            tuple((float(lat), float(lon)) for lat, lon in value["points"]),
                            bool(value.get("closed", False)),
                            str(value.get("name", "")),
                            tuple((str(key), str(item)) for key, item in value.get("tags", [])),
                        )
                        for value in values
                    ], "cache"
                except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                    pass
            try:
                features = fetch_features(selection)
                if features:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_text(json.dumps([
                        {
                            "kind": feature.kind,
                            "points": feature.points,
                            "closed": feature.closed,
                            "name": feature.name,
                            "tags": feature.tags,
                        }
                        for feature in features
                    ], separators=(",", ":")), encoding="utf-8")
                    return features, "live"
                return [], "live-empty"
            except RuntimeError:
                return [], "offline"
        return [], "offline"

    @staticmethod
    def _fallback_analysis(selection: GeoSelection, features: list[GeoFeature], reason: str = "") -> TerrainAnalysis:
        counts = Counter(feature.kind for feature in features)
        total = max(1, sum(counts.values()))
        arid_belt = 15 <= abs(selection.latitude) <= 35 and counts["forest"] == 0 and counts["water"] + counts["river"] == 0
        biome = "snow" if abs(selection.latitude) >= 62 else "desert" if counts["sand"] > 0 or arid_belt else "temperate"
        notes = ("Vision unavailable; used OpenStreetMap geometry and conservative climate fallback.",)
        if reason:
            notes += (reason[:120],)
        return TerrainAnalysis(
            biome=biome,
            relief="flat",
            vegetation_density=min(1.0, counts["forest"] / total * 4),
            urban_density=min(1.0, (counts["urban"] + counts["building"]) / total * 2),
            water_confidence=1.0 if counts["water"] + counts["river"] else 0.0,
            fidelity_notes=notes,
            summary="Geographic geometry preserved; terrain style inferred without vision.",
            confidence=0.45,
        )

    def generate(self, selection: GeoSelection, output_directory: Path) -> MissionResult:
        selection.validated()
        features, source_status = self._features(selection, output_directory)
        terrain_view: TerrainView | None = None
        analysis = self._fallback_analysis(selection, features)
        if self.allow_network and not self.fixture:
            try:
                terrain_view = fetch_terrain_view(selection, output_directory)
                source_status += "+terrain-view"
            except (OSError, TimeoutError, ValueError) as exc:
                source_status += "+terrain-view-unavailable"
                analysis = self._fallback_analysis(selection, features, str(exc))
        if terrain_view and self.terrain_analyzer:
            try:
                analysis = self.terrain_analyzer.analyze(selection, features, terrain_view)
                source_status += "+ai-vision"
            except RuntimeError as exc:
                source_status += "+vision-fallback"
                analysis = self._fallback_analysis(selection, features, str(exc))

        plan = build_terrain(selection, features, analysis, terrain_view)
        package_path, preview_path, manifest_path = create_package(
            selection, plan, output_directory, source_status, terrain_view=terrain_view
        )
        validation = validate_package(package_path)
        if not validation.valid:
            package_path.unlink(missing_ok=True)
            raise ValueError(f"generated package failed validation: {validation.checks}")
        # Repack once so the self-contained archive carries the validation
        # report that was computed from its map binary and metadata.
        package_path, preview_path, manifest_path = create_package(
            selection,
            plan,
            output_directory,
            source_status,
            validation.as_dict(),
            terrain_view,
        )
        final_validation = validate_package(package_path)
        if not final_validation.valid:
            package_path.unlink(missing_ok=True)
            raise ValueError(f"repacked mission failed validation: {final_validation.checks}")
        return MissionResult(package_path, preview_path, manifest_path, final_validation, source_status)
