#!/usr/bin/env python3
"""Inventory OpenRA mods without treating MiniYAML as ordinary YAML.

The scanner deliberately uses conservative text parsing. It inventories every
top-level actor, weapon, sequence, faction, mission, and C# TraitInfo visible in
the pinned source-only checkouts. Binary paths come from ``git ls-tree`` so the
large or non-redistributable blobs do not need to be downloaded.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ROOT / "docs" / "upstream-reuse" / "sources.json"
DEFAULT_REFERENCES = ROOT.parent / "OpenRA-Upstreams"
DEFAULT_JSON = ROOT / "docs" / "upstream-reuse" / "generated" / "catalog.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "upstream-reuse" / "generated" / "catalog.md"
TARGET_ENGINE = ROOT / "engine" / "openra"

TOP_LEVEL = re.compile(r"^([^\s#][^:]*):(?:\s*(?:#.*)?)?$")
NESTED_KEY = re.compile(r"^\s+([^\s#][^:]*):")
CONFIG_VALUE = re.compile(r'^\s*([A-Z0-9_]+)="([^"]*)"', re.MULTILINE)
CLASS_INFO = re.compile(
    r"\b(?:public|internal|private|protected|sealed|abstract|partial|static|\s)+"
    r"class\s+(\w+Info)\b"
)
LUA_CALL = re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\s*\(")

MISSION_PATTERN_MATCHERS = {
    "objectives": re.compile(r"Add(?:Primary|Secondary)Objective|Mark(?:Completed|Failed)Objective|Objective", re.I),
    "reinforcements": re.compile(r"Reinforce|Reinforcements\.|Paradrop", re.I),
    "timers-and-delays": re.compile(r"DateTime\.(?:AfterDelay|Seconds|Minutes)|MissionText|Timer", re.I),
    "briefing-and-dialogue": re.compile(r"DisplayMessage|PlaySpeechNotification|PlayMovie|PlaySound|MissionText", re.I),
    "camera-and-reveals": re.compile(r"Camera\.|Beacon\.|RevealsShroud|Reveal", re.I),
    "capture-and-infiltration": re.compile(r"Capture|Captured|Infiltrat|Entered", re.I),
    "base-building": re.compile(r"Build|Production|BaseBuilder|Harvester|Repair", re.I),
    "actor-spawning": re.compile(r"Actor\.Create|CreateActor|SpawnActor", re.I),
    "patrols-and-hunts": re.compile(r"Patrol|Hunt|AttackMove|IdleHunt", re.I),
    "transports-and-evacuation": re.compile(r"Transport|Passenger|Unload|Evacuat|Extract", re.I),
    "difficulty-branches": re.compile(r"Difficulty|easy|normal|hard|tough", re.I),
    "waves-and-survival": re.compile(r"Wave|Survival|AttackGroup|SendAttack", re.I),
}

TEXT_EXTENSIONS = {".yaml", ".yml", ".cs", ".lua", ".ftl", ".json", ".md", ".txt"}
IMAGE_EXTENSIONS = {".shp", ".vxl", ".hva", ".png", ".pcx", ".bmp", ".dds", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTENSIONS = {".aud", ".wav", ".ogg", ".mp3", ".flac"}
VIDEO_EXTENSIONS = {".vqa", ".mp4", ".webm", ".avi"}
MAP_EXTENSIONS = {".oramap", ".mpr", ".map"}

AI_MARKERS = ("botmodule", "modularbot", "squadmanager", "basebuilder", "harvesterbot")
UPGRADE_MARKERS = ("upgrade", "veteran", "rank", "experience", "promotion", "level")
STRATEGY_MARKERS = ("strategy", "doctrine", "general", "commander", "tactic")
SUPPORT_POWER_SUFFIXES = ("power", "powerinfo")


def run_git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", os.fspath(path), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip()


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def indentation(line: str) -> int:
    prefix = line[: len(line) - len(line.lstrip(" \t"))]
    return prefix.count("\t") + (len(prefix.replace("\t", "")) // 4)


def canonical_key(raw: str) -> str:
    key = raw.strip().lstrip("+-")
    return key.split("@", 1)[0]


def parse_config(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {match.group(1): match.group(2) for match in CONFIG_VALUE.finditer(read_text(path))}


def is_rule_file(path: Path, root: Path) -> bool:
    rel = relative(path, root).lower()
    parts = rel.split("/")
    if path.suffix.lower() not in {".yaml", ".yml"}:
        return False
    if path.name.lower() in {"mod.yaml", "content.yaml", "map.yaml", "missions.yaml"}:
        return False
    excluded = {
        "audio", "chrome", "cursors", "fluent", "hotkeys", "music", "notifications",
        "palettes", "sequences", "tilesets", "voices", "weapons",
    }
    if any(part in excluded for part in parts):
        return False
    return (
        "rules" in parts
        or "ai" in parts
        or path.name.lower() in {"rules.yaml", "rules.yml"}
        or ("contentpacks" in parts and "yaml" in parts)
    )


def is_weapon_file(path: Path, root: Path) -> bool:
    rel = relative(path, root).lower()
    parts = rel.split("/")
    return path.suffix.lower() in {".yaml", ".yml"} and (
        "weapons" in parts or path.name.lower() in {"weapons.yaml", "weapons.yml"}
    )


def is_sequence_file(path: Path, root: Path) -> bool:
    rel = relative(path, root).lower()
    return path.suffix.lower() in {".yaml", ".yml"} and "sequences" in rel.split("/")


def top_level_names(path: Path) -> list[str]:
    names: list[str] = []
    for line in read_text(path).splitlines():
        if line.startswith((" ", "\t")):
            continue
        match = TOP_LEVEL.match(line.rstrip())
        if match:
            names.append(match.group(1).strip())
    return names


def parse_actor_blocks(path: Path, root: Path) -> list[dict[str, Any]]:
    actors: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_trait = ""

    for number, line in enumerate(read_text(path).splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        level = indentation(line)
        if level == 0:
            match = TOP_LEVEL.match(line.rstrip())
            if not match:
                current = None
                continue
            current = {
                "id": match.group(1).strip(),
                "path": relative(path, root),
                "line": number,
                "traits": [],
                "inherits": [],
                "weapons": [],
                "factions": [],
                "prerequisites": [],
                "queue": None,
                "cost": None,
                "name": None,
                "description": None,
                "render_image": None,
            }
            actors.append(current)
            current_trait = ""
            continue

        if current is None:
            continue

        match = NESTED_KEY.match(line)
        if not match:
            continue
        raw_key = match.group(1).strip()
        key = canonical_key(raw_key)
        value = line.split(":", 1)[1].strip().split(" #", 1)[0].strip()

        if level == 1:
            current_trait = key
            if key not in current["traits"]:
                current["traits"].append(key)
            if key == "Inherits" and value:
                current["inherits"].append(value)
            continue

        if key == "Weapon" and value:
            current["weapons"].append(value)
        elif key == "Factions" and value:
            current["factions"].extend(part.strip() for part in value.split(",") if part.strip())
        elif key == "Prerequisites" and value:
            current["prerequisites"].extend(part.strip() for part in value.split(",") if part.strip())
        elif current_trait == "Buildable" and key == "Queue":
            current["queue"] = value
        elif current_trait == "Valued" and key == "Cost":
            current["cost"] = value
        elif current_trait == "Tooltip" and key == "Name":
            current["name"] = value
        elif current_trait == "Buildable" and key == "Description":
            current["description"] = value
        elif current_trait == "RenderSprites" and key == "Image":
            current["render_image"] = value

    for actor in actors:
        actor["traits"].sort(key=str.casefold)
        actor["inherits"] = sorted(set(actor["inherits"]), key=str.casefold)
        actor["weapons"] = sorted(set(actor["weapons"]), key=str.casefold)
        actor["factions"] = sorted(set(actor["factions"]), key=str.casefold)
        actor["prerequisites"] = sorted(set(actor["prerequisites"]), key=str.casefold)
        actor["category"] = classify_actor(actor)
    return actors


def classify_actor(actor: dict[str, Any]) -> str:
    path = actor["path"].lower()
    traits = {trait.lower() for trait in actor["traits"]}
    queue = (actor.get("queue") or "").lower()
    if actor["id"].startswith("^"):
        return "template"
    if "aircraft" in traits or "aircraft" in path or queue == "aircraft":
        return "aircraft"
    if any(token in path for token in ("ships", "naval", "boats")) or queue in {"ship", "naval"}:
        return "naval"
    if "building" in traits or any(token in path for token in ("structures", "buildings")):
        if any(trait.startswith("attack") for trait in traits):
            return "defense"
        return "building"
    if "withinfantrybody" in traits or "infantry" in path or queue == "infantry":
        return "infantry"
    if "mobile" in traits or "vehicle" in path or queue == "vehicle":
        return "vehicle"
    if actor["id"].lower() in {"world", "player"}:
        return "world"
    return "other"


def parse_factions(path: Path, root: Path) -> list[dict[str, Any]]:
    factions: list[dict[str, Any]] = []
    active: dict[str, Any] | None = None
    for number, line in enumerate(read_text(path).splitlines(), start=1):
        level = indentation(line)
        match = NESTED_KEY.match(line) if level else None
        raw_key = match.group(1).strip().lstrip("+-") if match else ""
        if level == 1 and match and canonical_key(raw_key).lower().startswith("faction"):
            raw = raw_key
            active = {
                "slot": raw.split("@", 1)[1] if "@" in raw else raw,
                "path": relative(path, root),
                "line": number,
                "internal_name": None,
                "name": None,
                "side": None,
                "selectable": True,
            }
            factions.append(active)
            continue
        if active is None:
            continue
        if level <= 1:
            active = None
            continue
        if not match:
            continue
        key = canonical_key(match.group(1))
        value = line.split(":", 1)[1].strip().split(" #", 1)[0].strip()
        if key == "InternalName":
            active["internal_name"] = value
        elif key == "Name":
            active["name"] = value
        elif key == "Side":
            active["side"] = value
        elif key == "Selectable":
            active["selectable"] = value.lower() != "false"
    return factions


def csharp_trait_infos(paths: Iterable[Path], root: Path) -> list[dict[str, Any]]:
    traits: list[dict[str, Any]] = []
    for path in paths:
        for number, line in enumerate(read_text(path).splitlines(), start=1):
            match = CLASS_INFO.search(line)
            if match:
                traits.append({"name": match.group(1), "path": relative(path, root), "line": number})
    return traits


def mission_inventory(paths: Iterable[Path], root: Path) -> list[dict[str, Any]]:
    by_directory: dict[Path, dict[str, Any]] = {}
    for path in paths:
        if path.suffix.lower() != ".lua":
            continue
        directory = path.parent
        entry = by_directory.setdefault(
            directory,
            {
                "id": relative(directory, root),
                "path": relative(directory, root),
                "lua": [],
                "has_map_yaml": False,
                "lua_calls": [],
                "story_patterns": [],
            },
        )
        entry["lua"].append(path.name)
        entry["has_map_yaml"] = (directory / "map.yaml").exists()
        text = read_text(path)
        entry["lua_calls"].extend(LUA_CALL.findall(text))
        entry["story_patterns"].extend(
            name for name, matcher in MISSION_PATTERN_MATCHERS.items() if matcher.search(text)
        )

    for entry in by_directory.values():
        entry["lua"].sort(key=str.casefold)
        entry["lua_calls"] = sorted(set(entry["lua_calls"]), key=str.casefold)
        entry["story_patterns"] = sorted(set(entry["story_patterns"]), key=str.casefold)
    return sorted(by_directory.values(), key=lambda item: item["id"].casefold())


def file_kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in MAP_EXTENSIONS:
        return "map"
    if suffix in TEXT_EXTENSIONS:
        return "text"
    return "other"


def unique_names(items: Iterable[dict[str, Any]]) -> list[str]:
    return sorted({item["name"] for item in items}, key=str.casefold)


def scan_project(project: dict[str, Any], reference_root: Path, baseline_traits: set[str]) -> dict[str, Any]:
    checkout = reference_root / project["checkout"]
    if not checkout.exists():
        raise FileNotFoundError(f"missing checkout: {checkout}")

    actual_commit = run_git(checkout, "rev-parse", "HEAD")
    if actual_commit != project["commit"]:
        raise RuntimeError(
            f"{project['id']} expected {project['commit']} but checkout is {actual_commit}; update pins intentionally"
        )

    tracked_paths = [line for line in run_git(checkout, "ls-tree", "-r", "--name-only", "HEAD").splitlines() if line]
    materialized = [
        path for path in checkout.rglob("*")
        if path.is_file() and ".git" not in path.parts and path.suffix.lower() in TEXT_EXTENSIONS
    ]
    yaml_paths = [path for path in materialized if path.suffix.lower() in {".yaml", ".yml"}]
    rule_paths = [path for path in yaml_paths if is_rule_file(path, checkout)]
    weapon_paths = [path for path in yaml_paths if is_weapon_file(path, checkout)]
    sequence_paths = [path for path in yaml_paths if is_sequence_file(path, checkout)]
    cs_paths = [path for path in materialized if path.suffix.lower() == ".cs"]

    actors = [actor for path in rule_paths for actor in parse_actor_blocks(path, checkout)]
    factions = [faction for path in rule_paths for faction in parse_factions(path, checkout)]
    trait_infos = csharp_trait_infos(cs_paths, checkout)
    novel_traits = [item for item in trait_infos if item["name"] not in baseline_traits]
    all_traits = sorted({trait for actor in actors for trait in actor["traits"]}, key=str.casefold)
    support_powers = sorted(
        {trait for trait in all_traits if trait.lower().endswith(SUPPORT_POWER_SUFFIXES)},
        key=str.casefold,
    )
    ai_modules = sorted(
        {trait for trait in all_traits if any(marker in trait.lower() for marker in AI_MARKERS)},
        key=str.casefold,
    )
    upgrade_traits = sorted(
        {trait for trait in all_traits if any(marker in trait.lower() for marker in UPGRADE_MARKERS)},
        key=str.casefold,
    )
    strategy_traits = sorted(
        {trait for trait in all_traits if any(marker in trait.lower() for marker in STRATEGY_MARKERS)},
        key=str.casefold,
    )

    category_counts = collections.Counter(actor["category"] for actor in actors)
    kinds = collections.Counter(file_kind(path) for path in tracked_paths)
    extensions = collections.Counter(Path(path).suffix.lower() or "<none>" for path in tracked_paths)
    config = parse_config(checkout / "mod.config")
    missions = mission_inventory(materialized, checkout)
    mission_pattern_counts = collections.Counter(
        pattern for mission in missions for pattern in mission["story_patterns"]
    )

    result = dict(project)
    result.update(
        {
            "actual_commit": actual_commit,
            "mod_id": config.get("MOD_ID"),
            "engine_version": config.get("ENGINE_VERSION"),
            "file_counts": dict(sorted(kinds.items())),
            "top_extensions": dict(extensions.most_common(30)),
            "actors": actors,
            "actor_counts": dict(sorted(category_counts.items())),
            "weapons": sorted({name for path in weapon_paths for name in top_level_names(path)}, key=str.casefold),
            "sequences": sorted({name for path in sequence_paths for name in top_level_names(path)}, key=str.casefold),
            "factions": factions,
            "missions": missions,
            "mission_pattern_counts": dict(sorted(mission_pattern_counts.items())),
            "csharp_trait_infos": trait_infos,
            "novel_csharp_trait_infos": novel_traits,
            "support_powers": support_powers,
            "ai_modules": ai_modules,
            "upgrade_traits": upgrade_traits,
            "strategy_traits": strategy_traits,
            "asset_paths": {
                "images": [path for path in tracked_paths if file_kind(path) == "image"],
                "audio": [path for path in tracked_paths if file_kind(path) == "audio"],
                "video": [path for path in tracked_paths if file_kind(path) == "video"],
                "maps": [path for path in tracked_paths if file_kind(path) == "map"],
            },
        }
    )
    return result


def target_baseline() -> tuple[set[str], dict[str, Any]]:
    cs_paths = [path for path in TARGET_ENGINE.rglob("*.cs") if ".git" not in path.parts]
    traits = csharp_trait_infos(cs_paths, TARGET_ENGINE)
    metadata = {
        "engine_path": "engine/openra",
        "engine_commit": run_git(TARGET_ENGINE, "rev-parse", "HEAD"),
        "engine_branch": run_git(TARGET_ENGINE, "rev-parse", "--abbrev-ref", "HEAD"),
        "trait_info_count": len(unique_names(traits)),
    }
    return set(unique_names(traits)), metadata


def markdown_report(catalog: dict[str, Any]) -> str:
    lines = [
        "# OpenRA upstream reuse catalog",
        "",
        f"Generated `{catalog['generated_at']}` from pinned source-only checkouts.",
        "Binary paths are inventoried from Git trees; their blobs are not automatically imported.",
        "",
        "## Target baseline",
        "",
        f"- Engine branch: `{catalog['target']['engine_branch']}`",
        f"- Engine commit: `{catalog['target']['engine_commit']}`",
        f"- Known TraitInfo classes: {catalog['target']['trait_info_count']}",
        "",
        "## Portfolio summary",
        "",
        "| Project | Engine | Actors | Factions | Weapons | Missions | Novel C# traits | Images | Audio |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for project in catalog["projects"]:
        lines.append(
            "| {name} | `{engine}` | {actors} | {factions} | {weapons} | {missions} | {novel} | {images} | {audio} |".format(
                name=project["name"],
                engine=project.get("engine_version") or "n/a",
                actors=len(project["actors"]),
                factions=len(project["factions"]),
                weapons=len(project["weapons"]),
                missions=len(project["missions"]),
                novel=len(project["novel_csharp_trait_infos"]),
                images=len(project["asset_paths"]["images"]),
                audio=len(project["asset_paths"]["audio"]),
            )
        )

    for project in catalog["projects"]:
        lines.extend(
            [
                "",
                f"## {project['name']}",
                "",
                f"- Source: [{project['repository']}]({project['repository']}) at `{project['commit']}`",
                f"- Engine: `{project.get('engine_version') or 'not declared'}`; mod id: `{project.get('mod_id') or 'not declared'}`",
                f"- Reuse role: {project['reuse_role']}",
                f"- Content gate: {project['content_policy']}",
                f"- Actor categories: `{json.dumps(project['actor_counts'], sort_keys=True)}`",
                f"- Support powers ({len(project['support_powers'])}): "
                + (", ".join(f"`{name}`" for name in project["support_powers"][:80]) or "none detected"),
                f"- AI modules ({len(project['ai_modules'])}): "
                + (", ".join(f"`{name}`" for name in project["ai_modules"][:80]) or "none detected"),
                f"- Upgrade/experience traits ({len(project['upgrade_traits'])}): "
                + (", ".join(f"`{name}`" for name in project["upgrade_traits"][:80]) or "none detected"),
                f"- Mission/story patterns: `{json.dumps(project['mission_pattern_counts'], sort_keys=True)}`",
                f"- Target-novel C# TraitInfo classes ({len(project['novel_csharp_trait_infos'])}): "
                + (
                    ", ".join(f"`{item['name']}`" for item in project["novel_csharp_trait_infos"][:120])
                    or "none detected"
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- MiniYAML inheritance is not resolved in this inventory; actor categories describe declared blocks.",
            "- A target-novel C# class may still depend on an upstream engine fork and is not automatically portable.",
            "- GPL-compatible code does not grant rights to unrelated art, sound, music, video, names, or trademarks.",
            "- Detailed actors, weapons, sequences, source locations, and asset paths are in `catalog.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--reference-root", type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--check", action="store_true", help="validate pins and scan without writing reports")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sources = json.loads(read_text(args.sources))
    baseline_traits, target = target_baseline()
    projects = [scan_project(project, args.reference_root, baseline_traits) for project in sources["projects"]]
    catalog = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "target": target,
        "projects": projects,
    }
    if args.check:
        print(f"validated {len(projects)} pinned projects and {sum(len(p['actors']) for p in projects)} actor blocks")
        return 0

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.output_markdown.write_text(markdown_report(catalog), encoding="utf-8")
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
