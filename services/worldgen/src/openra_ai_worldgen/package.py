from __future__ import annotations

import hashlib
import json
import struct
import zlib
from datetime import UTC, datetime
from pathlib import Path
from random import Random
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .models import GeoSelection
from .raster import FOREST, LAND, ROAD, ROUGH, SAND, URBAN, WATER, TerrainPlan
from .terrain import TerrainView

GENERATOR_VERSION = "0.2.0"


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def render_preview(plan: TerrainPlan, scale: int = 4) -> bytes:
    colors = {
        LAND: (96, 111, 74),
        WATER: (35, 77, 100),
        ROAD: (165, 145, 105),
        URBAN: (151, 132, 112),
        FOREST: (53, 92, 58),
        ROUGH: (100, 91, 82),
        SAND: (194, 166, 103),
    }
    spawn_colors = {(x, y): (224, 198, 103) for x, y in plan.spawns}
    mine_colors = {(x, y): (179, 76, 50) for x, y in plan.mines}
    width, height = plan.width * scale, plan.height * scale
    raw = bytearray()
    for y in range(plan.height):
        for _ in range(scale):
            raw.append(0)
            for x in range(plan.width):
                color = spawn_colors.get((x, y)) or mine_colors.get((x, y)) or colors[plan.cells[y][x]]
                raw.extend(color * scale)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _png_chunk(b"IEND", b"")


def compile_map_binary(plan: TerrainPlan, seed: int) -> bytes:
    rng = Random(seed)
    width, height = plan.width, plan.height
    area = width * height
    tiles_offset = 17
    resources_offset = tiles_offset + 3 * area
    result = bytearray(struct.pack("<BHHIII", 2, width, height, tiles_offset, 0, resources_offset))

    # OpenRA map arrays are serialized column-major.
    for x in range(width):
        for y in range(height):
            cell = plan.cells[y][x]
            if cell == WATER:
                tile_id, tile_index = (256, 0) if plan.tileset == "DESERT" else (1, 0)
            elif cell == ROAD:
                tile_id, tile_index = ((164 if (x + y) % 2 else 165), 0) if plan.tileset == "DESERT" else ((227 if (x + y) % 2 else 228), 0)
            elif cell == ROUGH:
                tile_id, tile_index = ((2 + (x + y) % 5), 0) if plan.tileset == "DESERT" else (97, 0)
            else:
                tile_id, tile_index = 255, rng.randrange(16)
            result.extend(struct.pack("<HB", tile_id, tile_index))

    resource_cells: dict[tuple[int, int], tuple[int, int]] = {}
    for mine_x, mine_y in plan.mines:
        resource_rng = Random(seed ^ 0x5F3759DF)
        for dy in range(-5, 6):
            for dx in range(-5, 6):
                x, y = mine_x + dx, mine_y + dy
                if 0 <= x < width and 0 <= y < height and plan.cells[y][x] != WATER:
                    distance = abs(dx) + abs(dy)
                    if 2 <= distance <= 7 and resource_rng.random() < 0.62:
                        resource_cells[(x, y)] = (1, max(4, 12 - distance))

    for x in range(width):
        for y in range(height):
            resource_type, density = resource_cells.get((x, y), (0, 0))
            result.extend(struct.pack("<BB", resource_type, density))
    return bytes(result)


def compile_map_yaml(selection: GeoSelection, plan: TerrainPlan) -> str:
    safe_title = selection.title.replace("\n", " ").replace("\r", " ").replace(":", " -").strip()[:80] or "Earth Skirmish"
    actor_lines: list[str] = []
    actor_id = 0
    for x, y in plan.spawns:
        actor_lines.extend([
            f"\tActor{actor_id}: mpspawn",
            "\t\tOwner: Neutral",
            f"\t\tLocation: {x},{y}",
        ])
        actor_id += 1
    for x, y in plan.mines:
        actor_lines.extend([
            f"\tActor{actor_id}: mine",
            "\t\tOwner: Neutral",
            f"\t\tLocation: {x},{y}",
        ])
        actor_id += 1
    for actor, x, y in plan.scenery:
        actor_lines.extend([
            f"\tActor{actor_id}: {actor}",
            "\t\tOwner: Neutral",
            f"\t\tLocation: {x},{y}",
        ])
        actor_id += 1
    margin = max(4, plan.width // 16)
    bounds_size = plan.width - 2 * margin
    return f"""MapFormat: 12

RequiresMod: ra

Title: {safe_title}

Author: OpenRA AI

Tileset: {plan.tileset}

MapSize: {plan.width},{plan.height}

Bounds: {margin},{margin},{bounds_size},{bounds_size}

Visibility: Lobby

Categories: Conquest

Players:
\tPlayerReference@Neutral:
\t\tName: Neutral
\t\tOwnsWorld: True
\t\tNonCombatant: True
\t\tFaction: allies
\tPlayerReference@Creeps:
\t\tName: Creeps
\t\tNonCombatant: True
\t\tFaction: allies
\t\tEnemies: Multi0, Multi1
\tPlayerReference@Multi0:
\t\tName: Multi0
\t\tPlayable: True
\t\tFaction: Random
\t\tEnemies: Creeps
\tPlayerReference@Multi1:
\t\tName: Multi1
\t\tPlayable: True
\t\tFaction: Random
\t\tEnemies: Creeps

Actors:
{chr(10).join(actor_lines)}
"""


def _zip_info(name: str) -> ZipInfo:
    info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def create_package(
    selection: GeoSelection,
    plan: TerrainPlan,
    output_directory: Path,
    source_status: str,
    validation: dict | None = None,
    terrain_view: TerrainView | None = None,
) -> tuple[Path, Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    slug = "".join(c.lower() if c.isalnum() else "-" for c in selection.title).strip("-") or "earth-skirmish"
    slug = "-".join(filter(None, slug.split("-")))[:48]
    stem = f"{slug}-{selection.seed}"
    package_path = output_directory / f"{stem}.oramap"
    preview_path = output_directory / f"{stem}.png"
    manifest_path = output_directory / f"{stem}.manifest.json"

    map_yaml = compile_map_yaml(selection, plan).encode("utf-8")
    map_binary = compile_map_binary(plan, selection.seed)
    preview = render_preview(plan)
    briefing = (
        f"# {selection.title}\n\n"
        f"A two-player skirmish translated from the terrain around {selection.location_name} "
        f"({selection.latitude:.5f}, {selection.longitude:.5f}).\n\n"
        f"{selection.story_seed.strip() or 'Secure the approaches, protect your supply line, and control the center.'}\n\n"
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
        "projection": "local equirectangular",
        "source": {
            "provider": "OpenStreetMap",
            "attribution": "© OpenStreetMap contributors",
            "status": source_status,
            "feature_count": plan.source_feature_count,
        },
        "terrain_view": terrain_view.metadata() if terrain_view else {"provider": "unavailable"},
        "analysis": plan.analysis.as_dict(),
        "game": {"mod": "ra", "map_format": 12, "tileset": plan.tileset},
        "design": {
            "spawns": plan.spawns,
            "mines": plan.mines,
            "scenery_count": len(plan.scenery),
            "feature_counts": plan.feature_counts,
            "mode": selection.generation_mode,
        },
        "checksums": checksums,
        "validation": validation or {},
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    with ZipFile(package_path, "w") as archive:
        for name, content in (
            ("map.yaml", map_yaml),
            ("map.bin", map_binary),
            ("map.png", preview),
            ("briefing.md", briefing),
            ("openra-ai-manifest.json", manifest_bytes),
        ):
            archive.writestr(_zip_info(name), content)
        if terrain_view:
            archive.writestr(_zip_info("earth-terrain.png"), terrain_view.image)

    preview_path.write_bytes(preview)
    manifest_path.write_bytes(manifest_bytes)
    return package_path, preview_path, manifest_path
