"""Package the authored Red Sea missions over deterministic terrain."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance


ROOT = Path(__file__).resolve().parents[1]
KEY_ART = ROOT / "assets" / "red-sea-2026" / "red-sea-key-art.png"
DEFAULT_TERRAIN = ROOT / "generated" / "missions" / "jizan-corridor-20260811.oramap"
FIXED_TIME = (2026, 8, 11, 0, 0, 0)

MISSION_SPECS = {
    "jizan-corridor-2026": {
        "source": ROOT / "missions" / "red-sea-2026" / "jizan-corridor",
        "output": ROOT / "generated" / "missions" / "jizan-corridor-2026.oramap",
        "install": ROOT / "engine" / "openra" / "mods" / "ra" / "maps" / "jizan-corridor-2026.oramap",
        "preview": ROOT / "assets" / "red-sea-2026" / "jizan-mission-preview.png",
        "crop_offset": -190,
        "route": [(8, 84), (26, 71), (44, 58), (61, 43), (76, 28), (87, 13)],
        "features": [
            "playable Saudi construction and harvesting economy",
            "scripted radar-capture phase",
            "layered drone and ground attacks",
            "mobile-launcher hunt",
            "three-vehicle relief convoy",
            "bilingual Arabic and English radio",
            "difficulty-scaled waves",
        ],
    },
    "hodeidah-lifeline-2026": {
        "source": ROOT / "missions" / "red-sea-2026" / "hodeidah-lifeline",
        "output": ROOT / "generated" / "missions" / "hodeidah-lifeline-2026.oramap",
        "install": ROOT / "engine" / "openra" / "mods" / "ra" / "maps" / "hodeidah-lifeline-2026.oramap",
        "preview": ROOT / "assets" / "red-sea-2026" / "hodeidah-mission-preview.png",
        "crop_offset": 170,
        "route": [(87, 13), (76, 28), (61, 43), (44, 58), (26, 71), (8, 84)],
        "features": [
            "playable Yemen construction, harvesting, and air economy",
            "two-stage relief and evacuation convoy flow",
            "timed surveillance-dispersal mechanic",
            "scripted Saudi combined-arms pressure",
            "starter Yemen infantry roster with drone-guided launchers",
            "player-buildable technicals, mobile launchers, and Samad drones",
            "bilingual Arabic and English radio",
            "difficulty-scaled sweep tolerance and attack waves",
        ],
    },
    "bab-al-mandab-passage-2026": {
        "source": ROOT / "missions" / "red-sea-2026" / "bab-al-mandab-passage",
        "output": ROOT / "generated" / "missions" / "bab-al-mandab-passage-2026.oramap",
        "install": ROOT / "engine" / "openra" / "mods" / "ra" / "maps" / "bab-al-mandab-passage-2026.oramap",
        "preview": ROOT / "assets" / "red-sea-2026" / "mandab-mission-preview.png",
        "crop_offset": 0,
        "route": [(48, 92), (42, 73), (38, 57), (37, 38), (42, 20), (48, 3)],
        "source_terrain": True,
        "features": [
            "playable Saudi construction, harvesting, production, and Tech Center progression",
            "three-sector coastal reconnaissance",
            "mobile-launcher hunt",
            "four-vessel civilian maritime escort around stylized Mayyun",
            "deadlock-resistant split-lane convoy recovery",
            "final difficulty-scaled combined-arms hold",
            "original bilingual Arabic and English synthetic radio",
        ],
    },
}


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def source_files(source: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(source.iterdir()):
        if path.is_file() and path.name not in {"README.md", "map.bin", "map.png"}:
            files[path.name] = path.read_bytes()
    return files


def build_mission_preview(spec: dict[str, object]) -> bytes:
    with Image.open(KEY_ART) as original:
        art = original.convert("RGB")
    side = min(art.height, art.width)
    centered = (art.width - side) // 2
    left = max(0, min(art.width - side, centered + int(spec["crop_offset"])))
    crop = art.crop((left, 0, left + side, side))
    crop = ImageEnhance.Contrast(crop).enhance(1.12)
    crop = ImageEnhance.Color(crop).enhance(0.90).resize((94, 94), Image.Resampling.LANCZOS)
    preview = crop.convert("RGBA")
    overlay = Image.new("RGBA", preview.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    route = list(spec["route"])
    draw.line(route, fill=(15, 12, 8, 210), width=4)
    draw.line(route, fill=(238, 181, 73, 245), width=2)
    for x, y in route:
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(250, 215, 116, 255), outline=(26, 20, 12, 255))
    radar_x, radar_y = route[0]
    for radius, alpha in ((15, 70), (10, 100), (5, 140)):
        draw.arc(
            (radar_x - radius, radar_y - radius, radar_x + radius, radar_y + radius),
            205,
            335,
            fill=(115, 220, 210, alpha),
            width=1,
        )
    draw.rectangle((0, 0, 93, 93), outline=(19, 17, 15, 255), width=2)
    preview.alpha_composite(overlay)
    preview_path = Path(spec["preview"])
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview.save(preview_path)
    return preview_path.read_bytes()


def build_mission(
    mission_id: str,
    spec: dict[str, object],
    terrain_package: Path | None,
    output: Path,
    install: Path,
) -> None:
    source = Path(spec["source"])
    files = source_files(source)
    if terrain_package is not None and terrain_package.is_file():
        with zipfile.ZipFile(terrain_package) as terrain:
            files["map.bin"] = terrain.read("map.bin")
            if "earth-terrain.png" in terrain.namelist():
                files["earth-terrain.png"] = terrain.read("earth-terrain.png")
    else:
        files["map.bin"] = (source / "map.bin").read_bytes()
    files["map.png"] = build_mission_preview(spec)

    contract = {
        "schema": "openra-ai.scripted-mission/v1",
        "id": mission_id,
        "factual_cutoff": "2026-08-11",
        "scenario": (
            "Source-dated Red Sea strategy fiction; force composition, routes, timing, "
            "positions, and outcomes are gameplay abstractions."
        ),
        "features": list(spec["features"]),
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    files["red-sea-mission-manifest.json"] = json.dumps(
        contract,
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in sorted(files.items()):
            archive.writestr(zip_info(name), data)

    if install != output:
        install.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output, install)
    print(f"Mission: {output}")
    if install != output:
        print(f"Installed: {install}")
    print(f"SHA256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mission", choices=("all", *MISSION_SPECS), default="all")
    parser.add_argument("--terrain-package", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--install", type=Path)
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()
    selected = list(MISSION_SPECS) if args.mission == "all" else [args.mission]
    if len(selected) > 1 and (args.output or args.install):
        parser.error("--output and --install require one explicit --mission")

    for mission_id in selected:
        spec = MISSION_SPECS[mission_id]
        if args.terrain_package:
            terrain = args.terrain_package.resolve()
        elif spec.get("source_terrain"):
            terrain = None
        else:
            terrain = DEFAULT_TERRAIN.resolve()
        output = (args.output or Path(spec["output"])).resolve()
        install = (args.install or Path(spec["install"])).resolve()
        if args.skip_install:
            install = output
        build_mission(mission_id, spec, terrain, output, install)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
