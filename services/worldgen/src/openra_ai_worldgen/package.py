from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .models import GeoSelection
from .raster import TerrainPlan
from .terrain import TerrainView

GENERATOR_VERSION = "0.3.0"


def artifact_paths(selection: GeoSelection, output_directory: Path) -> tuple[Path, Path, Path]:
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    slug = "".join(c.lower() if c.isalnum() else "-" for c in selection.title).strip("-") or "earth-skirmish"
    slug = "-".join(filter(None, slug.split("-")))[:48]
    stem = f"{slug}-{selection.seed}"
    return (
        output_directory / f"{stem}.oramap",
        output_directory / f"{stem}.png",
        output_directory / f"{stem}.manifest.json",
    )


def _zip_info(name: str) -> ZipInfo:
    info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def finalize_native_package(
    selection: GeoSelection,
    plan: TerrainPlan,
    package_path: Path,
    output_directory: Path,
    source_status: str,
    native: dict,
    native_options: dict,
    validation: dict,
    terrain_view: TerrainView | None = None,
) -> tuple[Path, Path, Path]:
    """Add Earth provenance to a package already rendered by OpenRA itself."""
    expected_package, preview_path, manifest_path = artifact_paths(selection, output_directory)
    if package_path.resolve() != expected_package.resolve():
        raise ValueError("native generator wrote an unexpected package path")

    with ZipFile(package_path, "r") as archive:
        map_yaml = archive.read("map.yaml")
        map_binary = archive.read("map.bin")
        preview = archive.read("map.png")

    briefing = (
        f"# {selection.title}\n\n"
        f"A two-player skirmish inspired by terrain evidence around {selection.location_name} "
        f"({selection.latitude:.5f}, {selection.longitude:.5f}).\n\n"
        f"{selection.story_seed.strip() or 'Secure the approaches, protect your supply line, and control the center.'}\n\n"
        "OpenRA's native generator converts that terrain character into a mechanically playable battlefield. "
        "This is a stylized fictional scenario, not a factual simulation of people or events.\n"
    ).encode("utf-8")
    checksums = {
        "map.yaml": hashlib.sha256(map_yaml).hexdigest(),
        "map.bin": hashlib.sha256(map_binary).hexdigest(),
        "map.png": hashlib.sha256(preview).hexdigest(),
    }
    if terrain_view:
        checksums["earth-terrain.png"] = hashlib.sha256(terrain_view.image).hexdigest()

    manifest = {
        "schema": "openra-ai.mission-package/v1",
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "selection": selection.as_dict(),
        "projection": "Earth evidence to native OpenRA generator profile",
        "source": {
            "provider": "OpenStreetMap",
            "attribution": "© OpenStreetMap contributors",
            "status": source_status,
            "feature_count": plan.source_feature_count,
        },
        "terrain_view": terrain_view.metadata() if terrain_view else {"provider": "unavailable"},
        "analysis": plan.analysis.as_dict(),
        "game": {"mod": "ra", "map_format": 12, "tileset": native.get("tileset", plan.tileset)},
        "generator": {
            "engine": "OpenRA ClassicMapGenerator",
            "engine_generator": native.get("engine_generator", "classic"),
            "requested_seed": native.get("requested_seed", selection.seed),
            "actual_seed": native.get("actual_seed", selection.seed),
            "uid": native.get("uid", ""),
            "options": native_options,
            "passability": native.get("passability", {}),
        },
        "design": {
            "feature_counts": plan.feature_counts,
            "mode": selection.generation_mode,
            "terrain_profile": native_options.get("terrain", "Plots"),
            "roads": native_options.get("roads", True),
        },
        "checksums": checksums,
        "validation": validation,
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    with ZipFile(package_path, "a", compression=ZIP_DEFLATED) as archive:
        archive.writestr(_zip_info("briefing.md"), briefing)
        archive.writestr(_zip_info("openra-ai-manifest.json"), manifest_bytes)
        if terrain_view:
            archive.writestr(_zip_info("earth-terrain.png"), terrain_view.image)

    preview_path.write_bytes(preview)
    manifest_path.write_bytes(manifest_bytes)
    return package_path, preview_path, manifest_path
