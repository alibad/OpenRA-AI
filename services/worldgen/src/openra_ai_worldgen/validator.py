from __future__ import annotations

import re
import struct
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from .models import ValidationReport


def validate_package(path: Path) -> ValidationReport:
    checks = {
        "zip_readable": False,
        "required_files": False,
        "map_format": False,
        "binary_layout": False,
        "spawn_count": False,
        "spawns_in_bounds": False,
        "resource_data_present": False,
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

    spawn_matches = re.findall(r"Actor\d+:\s+mpspawn\s+Owner:\s+Neutral\s+Location:\s+(\d+),(\d+)", yaml_text, re.MULTILINE)
    spawns = [(int(x), int(y)) for x, y in spawn_matches]
    checks["spawn_count"] = len(spawns) == 2
    checks["spawns_in_bounds"] = len(spawns) == 2 and all(0 <= x < width and 0 <= y < height for x, y in spawns)

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
    checks["resource_data_present"] = len(resource_counts) == 2 and min(resource_counts) > 0
    mission_files = {"rules.yaml", "earth-mission.lua", "map.ftl"}
    if mission_files & names:
        checks["mission_runtime_files"] = mission_files <= names
        rules = re.search(r"^Rules:\s*(.*)$", yaml_text, re.MULTILINE)
        fluent = re.search(r"^FluentMessages:\s*(.*)$", yaml_text, re.MULTILINE)
        rule_sources = {value.strip() for value in rules.group(1).split(",")} if rules else set()
        fluent_sources = {value.strip() for value in fluent.group(1).split(",")} if fluent else set()
        checks["mission_rules_referenced"] = {
            "ra|rules/campaign-rules.yaml",
            "rules.yaml",
        } <= rule_sources
        checks["mission_fluent_referenced"] = {
            "ra|fluent/lua.ftl",
            "ra|fluent/campaign.ftl",
            "map.ftl",
        } <= fluent_sources
        if not checks["mission_runtime_files"]:
            warnings.append("mission runtime files are incomplete")
        if not checks["mission_rules_referenced"]:
            warnings.append("map.yaml does not activate the generated mission rules")
        if not checks["mission_fluent_referenced"]:
            warnings.append("map.yaml does not activate the generated mission text")
    if checks["required_files"] and "openra-ai-manifest.json" not in names:
        warnings.append("generation manifest is missing")
    return ValidationReport(all(checks.values()), checks, metrics, warnings)
