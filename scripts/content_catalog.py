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
# Where each mode's faction rules and player-facing Fluent strings live. RA2 is the
# product mode, so its in-game names are canonical; Classic is recorded as shipped.
MODE_SOURCES = {
    "ra": {"repository": "engine", "rules": ("mods/ra/rules", "mods/ra/experiences"), "fluent": ("mods/ra/fluent",)},
    "ra2": {"repository": "product", "rules": ("apps/installer/ra2/modern-factions",), "fluent": ("apps/installer/ra2/modern-factions",)},
}
PRIMARY_MODES = ("ra2", "ra")


def fluent_messages(directories: list[Path]) -> dict[str, str]:
    """Single-line Fluent messages and attributes, keyed as `id` and `id.attribute`."""
    messages: dict[str, str] = {}
    for directory in directories:
        for path in sorted(directory.glob("*.ftl")):
            current = None
            for row in path.read_text(encoding="utf-8").splitlines():
                message = re.fullmatch(r"([A-Za-z][\w-]*)\s*=\s*(.*?)\s*", row)
                attribute = re.fullmatch(r"\s+\.([\w-]+)\s*=\s*(.*?)\s*", row)
                if message:
                    current = message.group(1)
                    if message.group(2):
                        messages[current] = message.group(2)
                elif attribute and current:
                    messages[f"{current}.{attribute.group(1)}"] = attribute.group(2)
                elif row.strip() and not row[0].isspace():
                    current = None
    return messages


def yaml_block(source: str, header: str) -> list[str]:
    """Child rows of the first `header:` line, at any indentation."""
    rows = source.splitlines()
    for index, row in enumerate(rows):
        if re.fullmatch(r"(\s*)" + re.escape(header) + r":\s*", row):
            indent = len(row) - len(row.lstrip())
            block = []
            for child in rows[index + 1:]:
                if child.strip() and len(child) - len(child.lstrip()) <= indent:
                    break
                block.append(child)
            return block
    return []


def tooltip_name_key(actor_rows: list[str]) -> str | None:
    for index, row in enumerate(actor_rows):
        if re.fullmatch(r"\s+Tooltip:\s*", row):
            return next((m.group(1) for child in yaml_block("\n".join(actor_rows[index:]), "Tooltip")
                         if (m := re.fullmatch(r"\s+Name:\s*(\S.*?)\s*", child))), None)
    return None


def faction_name_key(rules_dirs: list[Path], internal_name: str) -> str | None:
    for directory in rules_dirs:
        for path in sorted(directory.rglob("*.yaml")):
            source = path.read_text(encoding="utf-8")
            for header in re.findall(r"^\s+(Faction@\S+):\s*$", source, re.MULTILINE):
                rows = yaml_block(source, header)
                fields = dict(m.groups() for row in rows if (m := re.fullmatch(r"\s+(\w+):\s*(\S.*?)\s*", row)))
                if fields.get("InternalName") == internal_name:
                    return fields.get("Name")
    return None


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
    roots = {"engine": engine.resolve(), "product": product.resolve()}

    def mode_dirs(mode: str, kind: str) -> list[Path]:
        source = MODE_SOURCES[mode]
        return [roots[source["repository"]] / relative for relative in source[kind]]

    strings = {mode: fluent_messages(mode_dirs(mode, "fluent")) for mode in modes}

    def displayed(mode: str, key: str | None, subject: str) -> str:
        if not key or key not in strings[mode]:
            raise ValueError(f"Unresolved in-game name for {subject} ({mode}: {key})")
        return strings[mode][key]

    def require_name(subject: str, mode: str, expected: str, key: str | None) -> None:
        actual = displayed(mode, key, subject)
        if actual != expected:
            raise ValueError(f"Name drift for {subject} ({mode}): catalog '{expected}' but game shows '{actual}'")

    def primary_name(row: dict, available: set[str]) -> None:
        mode = next(mode for mode in PRIMARY_MODES if mode in available)
        if row["name"] != row["variants"][mode]["name"]:
            raise ValueError(f"{row['id']}: name must match its {mode} in-game name '{row['variants'][mode]['name']}'")
        if "role" in row and row["role"] != row["variants"][mode]["role"]:
            raise ValueError(f"{row['id']}: role must match its {mode} role '{row['variants'][mode]['role']}'")
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
            if variant["status"] == "implemented":
                key = faction_name_key(mode_dirs(mode, "rules"), variant["engineFactionId"])
                require_name(f"faction {faction['id']}", mode, variant["name"], key)
        primary_name(faction, {mode for mode, variant in faction["variants"].items() if variant["status"] == "implemented"})
    for unit in units.values():
        faction = factions.get(unit["factionId"])
        if not faction or unit["id"] not in faction["unitIds"] or not unit["variants"]:
            raise ValueError("Orphaned unit")
        for mode, variant in unit["variants"].items():
            if mode not in modes or faction["variants"][mode]["status"] != "implemented":
                raise ValueError("Unit advertises an unavailable faction mode")
            root = roots[variant["repository"]]
            path = (root / variant["rulesPath"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Rules path escapes repository")
            source = path.read_text(encoding="utf-8")
            if not re.search(r"^" + re.escape(variant["actorId"]) + r":\s*$", source, re.MULTILINE):
                raise ValueError(f"Unresolved actor: {mode}/{variant['actorId']} in {path}")
            if not variant.get("role"):
                raise ValueError(f"Missing {mode} role for unit {unit['id']}")
            key = tooltip_name_key([variant["actorId"] + ":"] + yaml_block(source, variant["actorId"]))
            require_name(f"unit {unit['id']}", mode, variant["name"], key)
        primary_name(unit, set(unit["variants"]))
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
