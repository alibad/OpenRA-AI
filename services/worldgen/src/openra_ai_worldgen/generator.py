from __future__ import annotations

from pathlib import Path

from .models import GeoSelection, MissionResult
from .osm import GeoFeature, fetch_features, load_fixture
from .package import create_package
from .raster import build_terrain
from .validator import validate_package


class MissionGenerator:
    def __init__(self, fixture: Path | None = None, allow_network: bool = True):
        self.fixture = fixture
        self.allow_network = allow_network

    def _features(self, selection: GeoSelection) -> tuple[list[GeoFeature], str]:
        if self.fixture:
            return load_fixture(self.fixture), "fixture"
        if self.allow_network and selection.source == "openstreetmap":
            try:
                features = fetch_features(selection)
                if features:
                    return features, "live"
                return [], "live-empty-synthetic-water"
            except RuntimeError:
                return [], "offline-synthetic-water"
        return [], "offline-synthetic-water"

    def generate(self, selection: GeoSelection, output_directory: Path) -> MissionResult:
        selection.validated()
        features, source_status = self._features(selection)
        plan = build_terrain(selection, features)
        package_path, preview_path, manifest_path = create_package(
            selection, plan, output_directory, source_status
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
        )
        final_validation = validate_package(package_path)
        if not final_validation.valid:
            package_path.unlink(missing_ok=True)
            raise ValueError(f"repacked mission failed validation: {final_validation.checks}")
        return MissionResult(package_path, preview_path, manifest_path, final_validation, source_status)
