"""Validate the shared editorial catalog against game sources; stage unchanged bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

PRODUCT = Path(__file__).resolve().parents[1]
CATALOG = PRODUCT / "catalog" / "factions.json"


def validate(catalog: dict, engine: Path, product: Path = PRODUCT) -> None:
    if catalog.get("schemaVersion") != 1:
        raise ValueError("Unsupported catalog schema")

    def indexed(key):
        rows = catalog[key]
        result = {row["id"]: row for row in rows}
        if len(rows) != len(result) or any(not re.fullmatch(r"[a-z0-9-]+", key) for key in result):
            raise ValueError(f"Invalid or duplicate {key} ID")
        return result

    modes, profiles, factions, units = (indexed(key) for key in ("modes", "profiles", "factions", "units"))
    if set(modes) != {"ra", "ra2"}:
        raise ValueError("Catalog must distinguish ra and ra2")
    for profile in profiles.values():
        if profile["mode"] not in modes or not set(profile["factionIds"]) <= factions.keys():
            raise ValueError("Invalid profile membership")
    for faction in factions.values():
        if len(faction["unitIds"]) != len(set(faction["unitIds"])):
            raise ValueError("Duplicate roster entry")
        for unit_id in faction["unitIds"]:
            if unit_id not in units or units[unit_id]["factionId"] != faction["id"]:
                raise ValueError(f"Unresolved roster entry: {unit_id}")
        if set(faction["variants"]) != set(modes):
            raise ValueError("Missing faction mode")
        for mode, variant in faction["variants"].items():
            if variant["status"] not in {"implemented", "unavailable"}:
                raise ValueError("Invalid implementation status")
            profile = profiles.get(variant["profileId"])
            if variant["status"] == "implemented" and (not profile or profile["mode"] != mode or faction["id"] not in profile["factionIds"]):
                raise ValueError("Invalid faction profile")
            if variant["status"] == "unavailable" and profile is not None:
                raise ValueError("Unavailable faction cannot belong to a profile")
    for unit in units.values():
        faction = factions.get(unit["factionId"])
        if not faction or unit["id"] not in faction["unitIds"] or not unit["variants"]:
            raise ValueError("Orphaned unit")
        for mode, variant in unit["variants"].items():
            if mode not in modes or faction["variants"][mode]["status"] != "implemented":
                raise ValueError("Unit advertises an unavailable faction mode")
            roots = {"engine": engine, "product": product}
            root = roots[variant["repository"]].resolve()
            path = (root / variant["rulesPath"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Rules path escapes repository")
            source = path.read_text(encoding="utf-8")
            if not re.search(r"^" + re.escape(variant["actorId"]) + r":\s*$", source, re.MULTILINE):
                raise ValueError(f"Unresolved actor: {mode}/{variant['actorId']} in {path}")
    for theatre in indexed("theatres").values():
        if theatre["mode"] not in modes or not set(theatre["factionIds"]) <= factions.keys():
            raise ValueError("Invalid theatre membership")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=PRODUCT / "engine" / "openra")
    parser.add_argument("--stage", type=Path, help="Package root; copies catalog to catalog/factions.json")
    args = parser.parse_args()
    validate(json.loads(CATALOG.read_text(encoding="utf-8")), args.engine)
    if args.stage:
        destination = args.stage / "catalog" / "factions.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CATALOG, destination)
    print(json.dumps({"catalog": "catalog/factions.json", "sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(), "valid": True}))


if __name__ == "__main__":
    main()
