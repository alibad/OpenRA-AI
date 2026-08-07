from __future__ import annotations

import re
import struct
from collections import deque
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from .models import ValidationReport


def _connected(tiles: list[list[int]], a: tuple[int, int], b: tuple[int, int]) -> bool:
    queue = deque([a])
    seen = {a}
    while queue:
        x, y = queue.popleft()
        if (x, y) == b:
            return True
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= ny < len(tiles) and 0 <= nx < len(tiles[0]) and tiles[ny][nx] != 1 and (nx, ny) not in seen:
                seen.add((nx, ny))
                queue.append((nx, ny))
    return False


def validate_package(path: Path) -> ValidationReport:
    checks = {
        "zip_readable": False,
        "required_files": False,
        "map_format": False,
        "binary_layout": False,
        "spawn_count": False,
        "spawns_in_bounds": False,
        "spawns_on_land": False,
        "spawn_connectivity": False,
        "resource_symmetry": False,
    }
    warnings: list[str] = []
    metrics: dict[str, int | float | str] = {"package": str(path)}
    try:
        with ZipFile(path) as archive:
            checks["zip_readable"] = True
            names = set(archive.namelist())
            checks["required_files"] = {"map.yaml", "map.bin", "map.png"} <= names
            if not checks["required_files"]:
                return ValidationReport(False, checks, metrics, ["map package is missing required files"])
            yaml_text = archive.read("map.yaml").decode("utf-8")
            binary = archive.read("map.bin")
    except (OSError, BadZipFile, KeyError, UnicodeDecodeError) as exc:
        return ValidationReport(False, checks, metrics, [str(exc)])

    checks["map_format"] = bool(re.search(r"^MapFormat:\s*12\s*$", yaml_text, re.MULTILINE))
    map_size_match = re.search(r"^MapSize:\s*(\d+),(\d+)\s*$", yaml_text, re.MULTILINE)
    if not map_size_match or len(binary) < 17:
        return ValidationReport(False, checks, metrics, ["invalid map size or binary header"])
    yaml_width, yaml_height = map(int, map_size_match.groups())
    tile_format, width, height, tiles_offset, heights_offset, resources_offset = struct.unpack("<BHHIII", binary[:17])
    expected_length = 17 + width * height * 5
    checks["binary_layout"] = (
        tile_format == 2
        and (width, height) == (yaml_width, yaml_height)
        and tiles_offset == 17
        and heights_offset == 0
        and resources_offset == 17 + width * height * 3
        and len(binary) == expected_length
    )
    metrics.update({"width": width, "height": height, "binary_bytes": len(binary)})
    if not checks["binary_layout"]:
        return ValidationReport(False, checks, metrics, ["map.bin offsets or length are invalid"])

    tiles = [[0 for _ in range(width)] for _ in range(height)]
    offset = tiles_offset
    for x in range(width):
        for y in range(height):
            tile_type, _ = struct.unpack("<HB", binary[offset : offset + 3])
            tiles[y][x] = tile_type
            offset += 3

    spawn_matches = re.findall(r"Actor\d+:\s+mpspawn\s+Owner:\s+Neutral\s+Location:\s+(\d+),(\d+)", yaml_text, re.MULTILINE)
    spawns = [(int(x), int(y)) for x, y in spawn_matches]
    checks["spawn_count"] = len(spawns) == 2
    checks["spawns_in_bounds"] = len(spawns) == 2 and all(0 <= x < width and 0 <= y < height for x, y in spawns)
    checks["spawns_on_land"] = checks["spawns_in_bounds"] and all(tiles[y][x] != 1 for x, y in spawns)
    checks["spawn_connectivity"] = checks["spawns_on_land"] and _connected(tiles, spawns[0], spawns[1])

    resource_counts: list[int] = []
    for spawn_x, spawn_y in spawns:
        count = 0
        for x in range(width):
            for y in range(height):
                resource_type, density = struct.unpack(
                    "<BB", binary[resources_offset + 2 * (x * height + y) : resources_offset + 2 * (x * height + y) + 2]
                )
                if resource_type and density and (x - spawn_x) ** 2 + (y - spawn_y) ** 2 <= 15 ** 2:
                    count += density
        resource_counts.append(count)
    metrics["spawn_resources"] = ",".join(map(str, resource_counts))
    checks["resource_symmetry"] = len(resource_counts) == 2 and min(resource_counts) > 0 and max(resource_counts) / min(resource_counts) <= 1.35
    if checks["required_files"] and "openra-ai-manifest.json" not in names:
        warnings.append("generation manifest is missing")
    return ValidationReport(all(checks.values()), checks, metrics, warnings)
