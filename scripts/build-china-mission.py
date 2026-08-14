"""Package the deterministic Haitan Network scenario for OpenRA."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "missions" / "china-faction" / "haitan-network"
OUTPUT = ROOT / "generated" / "missions" / "haitan-network-2026.oramap"
INSTALL = ROOT / "engine" / "openra" / "mods" / "ra" / "maps" / "haitan-network-2026.oramap"
FIXED_TIME = (2026, 8, 12, 0, 0, 0)


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()
    files = {
        path.name: path.read_bytes()
        for path in sorted(SOURCE.iterdir())
        if path.is_file() and path.name not in {"README.md", "briefing.md"}
    }
    manifest = {
        "schema": "openra-ai.scripted-mission/v1",
        "id": "haitan-network-2026",
        "scenario_date": "2026-08-12",
        "fictional": True,
        "real_persons": False,
        "terrain": {
            "generator": "OpenRA Classic Generator",
            "tileset": "DESERT",
            "profile": "LargeIslands",
            "requested_seed": 8122026,
            "accepted_seed": 8122027,
            "tracked_reachable_spawns": "2/2",
            "tracked_reachable_cells": 2165,
        },
        "features": [
            "deployable sensor and jammer specialist",
            "water-gated amphibious landing",
            "coordinated land, air, missile, drone, and naval combat",
            "difficulty-scaled ground, air, and naval attacks",
            "Mandarin and English generic synthetic radio",
        ],
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    files["china-mission-manifest.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w") as archive:
        for name, data in sorted(files.items()):
            archive.writestr(zip_info(name), data)

    if not args.skip_install:
        INSTALL.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OUTPUT, INSTALL)
    print(f"Mission: {OUTPUT}")
    if not args.skip_install:
        print(f"Installed: {INSTALL}")
    print(f"SHA256: {hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
