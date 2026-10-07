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
MOD = PRODUCT.parent / "RTSAI-Mod"
# Classic (ra) mode is checked against the canonical alibad/OpenRA main checkout beside this repository, as the
# tests do. The engine/openra submodule pins an older engine without the Classic Israel and Hezbollah packs.
# Packagers pass --engine with the engine they are packaging.
ENGINE = PRODUCT.parent / "OpenRA"
# Where each mode's faction rules and player-facing Fluent strings live. RA2 is the
# product mode (the RTS AI mod), so its in-game names are canonical; Classic is
# recorded as shipped in the parked public alpha.
MODE_SOURCES = {
    "ra": {"repository": "engine", "rules": ("mods/ra/rules", "mods/ra/experiences"), "fluent": ("mods/ra/fluent",)},
    "ra2": {"repository": "mod", "rules": ("mods/rtsai/modern-factions", "mods/rtsai/rules"),
            "fluent": ("mods/rtsai/modern-factions", "mods/rtsai/languages", "mods/rtsai/languages/rules")},
}
PRIMARY_MODES = ("ra2", "ra")
# Faction narrative: each faction's in-world self story (identity), what named rivals say about it (rivalViews:
# propaganda or grievance, never a claim of real-world truth) and loading/voice flavour. Public and marketing-facing,
# so every faction gets the same depth and no voice may dehumanize, attack a faith or invoke atrocities.
RIVAL_KINDS = {"propaganda", "grievance"}
NARRATIVE_FORBIDDEN = re.compile(
    r"\b(terrorists?|terrorism|vermin|savages?|barbarians?|subhumans?|animals|cockroach(?:es)?|infidels?|heretics?|"
    r"apostates?|kafirs?|crusaders?|zionists?|genocides?|massacres?)\b", re.IGNORECASE)
STORY_PARITY = 1.35  # the longest identity story may be at most this multiple of the shortest


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


def narrative_text(subject: str, value, low: int, high: int, sentences: tuple[int, int] | None = None) -> None:
    if not isinstance(value, str) or value != value.strip() or "\n" in value or not low <= len(value) <= high:
        raise ValueError(f"{subject} must be one line of {low}-{high} characters")
    if NARRATIVE_FORBIDDEN.search(value):
        raise ValueError(f"{subject} uses a term the narrative guardrails forbid")
    if sentences:
        count = len(re.split(r"(?<=[.!?])\s+", value))
        if not value.endswith((".", "!", "?")) or not sentences[0] <= count <= sentences[1]:
            raise ValueError(f"{subject} must be {sentences[0]}-{sentences[1]} complete sentences")


def validate_narrative(catalog: dict) -> None:
    """Every faction needs an identity, rival views from existing factions and flavour lines, with equal depth."""
    narrative_text("narrative framing", (catalog.get("narrative") or {}).get("framing"), 80, 400)
    factions = {row["id"]: row for row in catalog["factions"]}
    voiced = set()
    for faction_id, faction in factions.items():
        identity = faction.get("identity") or {}
        narrative_text(f"{faction_id} motto", identity.get("motto"), 10, 60, (1, 2))
        narrative_text(f"{faction_id} identity story", identity.get("story"), 300, 600, (3, 5))
        keywords = identity.get("keywords")
        if (not isinstance(keywords, list) or len(keywords) != 3 or len({str(k).casefold() for k in keywords}) != 3
                or not all(isinstance(k, str) and len(k) <= 20 and re.fullmatch(r"[A-Z][a-z]+( [A-Za-z][a-z]+)?", k) for k in keywords)):
            raise ValueError(f"{faction_id} needs three distinct capitalized keywords of one or two words")
        views = faction.get("rivalViews")
        if not isinstance(views, list) or not 2 <= len(views) <= 3:
            raise ValueError(f"{faction_id} needs 2-3 rival views")
        rivals = [view.get("rival") for view in views]
        if len(set(rivals)) != len(rivals) or any(rival not in factions or rival == faction_id for rival in rivals):
            raise ValueError(f"{faction_id} rival views must come from distinct other factions in the catalog")
        for view in views:
            if view.get("kind") not in RIVAL_KINDS:
                raise ValueError(f"{faction_id} rival view by {view['rival']} must be framed as {sorted(RIVAL_KINDS)}")
            narrative_text(f"{faction_id} rival view by {view['rival']}", view.get("text"), 100, 300, (2, 3))
        voiced.update(rivals)
        flavour = faction.get("flavour") or {}
        loading = flavour.get("loading")
        if not isinstance(loading, list) or sorted(str(line.get("perspective")) for line in loading) != ["rival", "self"]:
            raise ValueError(f"{faction_id} needs one self and one rival loading line")
        for line in loading:
            named = line["perspective"] == "rival"
            if ("rival" in line) != named or (named and line["rival"] not in rivals):
                raise ValueError(f"{faction_id}: only the rival loading line names a rival, and it must be one of its rival views")
            narrative_text(f"{faction_id} {line['perspective']} loading line", line.get("text"), 20, 120)
        voices = flavour.get("voiceIdeas")
        if not isinstance(voices, list) or not 1 <= len(voices) <= 2 or len(set(voices)) != len(voices):
            raise ValueError(f"{faction_id} needs 1-2 distinct voice ideas")
        for voice in voices:
            narrative_text(f"{faction_id} voice idea", voice, 8, 60)
    # Equal dignity: the same number of rival views, comparable story depth, and no faction is only ever the target.
    if len({len(faction["rivalViews"]) for faction in factions.values()}) != 1:
        raise ValueError("Every faction needs the same number of rival views")
    lengths = [len(faction["identity"]["story"]) for faction in factions.values()]
    if max(lengths) > STORY_PARITY * min(lengths):
        raise ValueError(f"Identity stories must be of comparable length (longest at most {STORY_PARITY}x the shortest)")
    if voiced != set(factions):
        raise ValueError(f"Every faction must voice at least one rival view: missing {sorted(set(factions) - voiced)}")


def validate(catalog: dict, engine: Path, product: Path = PRODUCT, mod: Path = MOD) -> None:
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
    validate_narrative(catalog)
    roots = {"engine": engine.resolve(), "product": product.resolve(), "mod": mod.resolve()}

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
    parser.add_argument("--engine", type=Path, default=ENGINE,
                        help="Classic engine checkout (default: ../OpenRA, the canonical alibad/OpenRA main)")
    parser.add_argument("--mod", type=Path, default=MOD, help="RTS AI mod checkout (alibad/RTSAI-Mod)")
    parser.add_argument("--stage", type=Path, help="Package root; copies catalog to catalog/factions.json")
    args = parser.parse_args()
    validate(json.loads(CATALOG.read_text(encoding="utf-8")), args.engine, mod=args.mod)
    if args.stage:
        destination = args.stage / "catalog" / "factions.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CATALOG, destination)
    print(json.dumps({"catalog": "catalog/factions.json", "sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(), "valid": True}))


if __name__ == "__main__":
    main()
