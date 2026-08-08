from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import time
from typing import Callable

from .ai import TerrainAnalyzer
from .models import GeoSelection, MissionResult, TerrainAnalysis, ValidationReport
from .native import NativeMapGenerator
from .osm import GeoFeature, fetch_features, load_fixture
from .package import artifact_paths, finalize_native_package
from .raster import build_terrain
from .terrain import TerrainView, fetch_terrain_view
from .validator import validate_package


class MissionGenerator:
    def __init__(
        self,
        fixture: Path | None = None,
        allow_network: bool = True,
        terrain_analyzer: TerrainAnalyzer | None = None,
        native_map_generator: NativeMapGenerator | None = None,
    ):
        self.fixture = fixture
        self.allow_network = allow_network
        self.terrain_analyzer = terrain_analyzer
        self.native_map_generator = native_map_generator or NativeMapGenerator()

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
        forest_ratio = counts["forest"] / total
        water_ratio = (counts["water"] + counts["river"]) / total
        arid_belt = 15 <= abs(selection.latitude) <= 35 and forest_ratio < 0.05 and water_ratio < 0.02
        biome = "snow" if abs(selection.latitude) >= 62 else "desert" if counts["sand"] > 0 or arid_belt else "temperate"
        water_confidence = min(1.0, water_ratio * 40)
        if counts["river"]:
            water_confidence = max(0.35, water_confidence)
        elif counts["water"]:
            water_confidence = max(0.25, water_confidence)
        notes = ("Vision unavailable; used OpenStreetMap geometry and conservative climate fallback.",)
        if reason:
            notes += (reason[:120],)
        return TerrainAnalysis(
            biome=biome,
            relief="flat",
            vegetation_density=min(1.0, counts["forest"] / total * 4),
            urban_density=min(1.0, (counts["urban"] + counts["building"]) / total * 2),
            water_confidence=water_confidence,
            fidelity_notes=notes,
            summary="Geographic evidence summarized into a native OpenRA terrain profile without vision.",
            confidence=0.45,
        )

    def generate(
        self,
        selection: GeoSelection,
        output_directory: Path,
        progress: Callable[[int, str], None] | None = None,
    ) -> MissionResult:
        report = progress or (lambda _stage, _message: None)
        selection.validated()
        report(1, "Reading roads, waterways, buildings, and land use")
        features, source_status = self._features(selection, output_directory)
        terrain_view: TerrainView | None = None
        analysis = self._fallback_analysis(selection, features)
        if self.allow_network and not self.fixture:
            try:
                report(2, "Capturing the terrain view used by the AI")
                terrain_view = fetch_terrain_view(selection, output_directory)
                source_status += "+terrain-view"
            except (OSError, TimeoutError, ValueError) as exc:
                source_status += "+terrain-view-unavailable"
                analysis = self._fallback_analysis(selection, features, str(exc))
        if terrain_view and self.terrain_analyzer:
            try:
                report(3, "AI is interpreting terrain character and visual context")
                analysis = self.terrain_analyzer.analyze(selection, features, terrain_view)
                source_status += "+ai-vision"
            except RuntimeError as exc:
                source_status += "+vision-fallback"
                analysis = self._fallback_analysis(selection, features, str(exc))

        report(4, "Translating geography into playable OpenRA terrain")
        plan = build_terrain(selection, features, analysis, terrain_view)
        package_path, _, _ = artifact_paths(selection, output_directory)
        native = self.native_map_generator.generate(selection, analysis, package_path)
        report(5, "OpenRA is validating tracked-unit paths, spawn zones, resources, and package integrity")
        structural = validate_package(package_path)
        passability = native.metadata.get("passability", {})
        checks = {
            **structural.checks,
            "native_openra_generator": native.metadata.get("engine_generator") == "classic",
            "tracked_unit_passability": bool(passability.get("valid")),
        }
        validation = ValidationReport(
            valid=all(checks.values()),
            checks=checks,
            metrics={
                **structural.metrics,
                "passability_unit": str(passability.get("unit", "")),
                "passability_locomotor": str(passability.get("locomotor", "")),
                "reachable_spawns": int(passability.get("reachable_spawns", 0)),
                "reachable_cells": int(passability.get("reachable_cells", 0)),
                "minimum_spawn_zone_cells": int(passability.get("minimum_spawn_zone_cells", 0)),
                "actual_seed": int(native.metadata.get("actual_seed", selection.seed)),
            },
            warnings=[warning for warning in structural.warnings if warning != "generation manifest is missing"],
        )
        if not validation.valid:
            package_path.unlink(missing_ok=True)
            raise ValueError(f"generated package failed validation: {validation.checks}")

        package_path, preview_path, manifest_path = finalize_native_package(
            selection,
            plan,
            package_path,
            output_directory,
            source_status,
            native.metadata,
            native.options,
            validation.as_dict(),
            terrain_view,
        )
        final_validation = validate_package(package_path)
        if not final_validation.valid:
            package_path.unlink(missing_ok=True)
            raise ValueError(f"final mission package failed validation: {final_validation.checks}")
        return MissionResult(package_path, preview_path, manifest_path, validation, source_status)
