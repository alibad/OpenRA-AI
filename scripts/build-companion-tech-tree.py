#!/usr/bin/env python3
"""Build the co-commander's per-faction tech tree from the RTS AI mod's rules.

The live observation only names actors that are on the field or currently
buildable, so the companion cannot tell "Barracks" from nonsense, let alone say
what the Barracks still needs.  This script resolves the mod's MiniYAML rules
(files, inheritance and removals, as OpenRA does) and its Fluent names, then
writes, for every selectable faction, everything that faction can build: the
display name, queue, cost, palette order and the buildings that unlock it.
Catalog names and aliases from ``catalog/factions.json`` are added per faction.

    python scripts/build-companion-tech-tree.py \
        --profile rtsai=../RTSAI-Mod@main --profile standalone=../RTSAI-Mod@rtsai/standalone

A profile is ``name=<mod checkout>[@<git ref>]``; with a ref the files are read
from git, so the output does not depend on any worktree's state.  The result is
``services/companion/src/openra_ai_companion/data/tech_tree.json``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
OUTPUT = REPOSITORY / "services" / "companion" / "src" / "openra_ai_companion" / "data" / "tech_tree.json"
CATALOG = REPOSITORY / "catalog" / "factions.json"

# Engine-side producers (queues) that are not ordinary prerequisites.
QUEUES = ("Building", "Defense", "Infantry", "Vehicle", "Aircraft", "Ship", "Support", "Cloning")


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

class Source:
    """Read a mod checkout from the file system or from a git ref."""

    def __init__(self, root: Path, ref: str | None) -> None:
        self.root = root
        self.ref = ref

    def read(self, relative: str) -> str | None:
        if self.ref:
            result = subprocess.run(
                ["git", "-C", str(self.root), "show", f"{self.ref}:{relative}"],
                capture_output=True,
            )
            return result.stdout.decode("utf-8-sig") if result.returncode == 0 else None
        path = self.root / relative
        return path.read_text(encoding="utf-8-sig") if path.exists() else None

    def commit(self) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", self.ref or "HEAD"], capture_output=True, text=True
        )
        return result.stdout.strip()


# ---------------------------------------------------------------------------
# MiniYAML
# ---------------------------------------------------------------------------

@dataclass
class Node:
    key: str
    value: str = ""
    children: list["Node"] = field(default_factory=list)

    def child(self, key: str) -> "Node | None":
        return next((node for node in self.children if node.key == key), None)

    def get(self, key: str, default: str = "") -> str:
        node = self.child(key)
        return node.value if node is not None else default

    def copy(self) -> "Node":
        return Node(self.key, self.value, [child.copy() for child in self.children])


def _strip_comment(line: str) -> str:
    out = []
    escaped = False
    for character in line:
        if character == "#" and not escaped:
            break
        escaped = character == "\\"
        out.append(character)
    return "".join(out).replace("\\#", "#")


def parse_miniyaml(text: str) -> list[Node]:
    roots: list[Node] = []
    stack: list[tuple[int, Node]] = []
    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip("\t ")
        prefix = line[: len(line) - len(stripped)]
        level = prefix.count("\t") + prefix.count(" ") // 4
        key, _, value = stripped.partition(":")
        node = Node(key.strip(), value.strip())
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            stack[-1][1].children.append(node)
        else:
            roots.append(node)
        stack.append((level, node))
    return roots


def merge_children(base: list[Node], override: list[Node]) -> list[Node]:
    """OpenRA's merge: later values win, children merge by key, ``-Key`` removes."""
    result = [node.copy() for node in base]
    for node in override:
        if node.key.startswith("-"):
            target = node.key[1:]
            result = [existing for existing in result if existing.key != target]
            continue
        existing = next((candidate for candidate in result if candidate.key == node.key), None)
        if existing is None:
            result.append(node.copy())
        else:
            if node.value:
                existing.value = node.value
            existing.children = merge_children(existing.children, node.children)
    return result


def merge_files(documents: list[list[Node]]) -> dict[str, Node]:
    merged: dict[str, Node] = {}
    for document in documents:
        for node in document:
            if node.key.startswith("-"):
                merged.pop(node.key[1:], None)
                continue
            if node.key in merged:
                existing = merged[node.key]
                if node.value:
                    existing.value = node.value
                # Keep removals so inherited traits can be removed during resolution.
                existing.children = existing.children + [child.copy() for child in node.children]
            else:
                merged[node.key] = node.copy()
    return merged


def resolve(rules: dict[str, Node]) -> dict[str, Node]:
    resolved: dict[str, Node] = {}

    def build(name: str, trail: tuple[str, ...] = ()) -> Node:
        if name in resolved:
            return resolved[name]
        if name in trail:
            raise ValueError(f"inheritance loop: {' -> '.join(trail + (name,))}")
        node = rules[name]
        children: list[Node] = []
        own: list[Node] = []
        for child in node.children:
            if child.key == "Inherits" or child.key.startswith("Inherits@"):
                if child.value in rules:
                    children = merge_children(children, build(child.value, trail + (name,)).children)
            else:
                own.append(child)
        result = Node(name, node.value, merge_children(children, own))
        resolved[name] = result
        return result

    for name in rules:
        build(name)
    return resolved


# ---------------------------------------------------------------------------
# Fluent (actor names only: "key = value" lines)
# ---------------------------------------------------------------------------

def parse_fluent(text: str) -> dict[str, str]:
    messages: dict[str, str] = {}
    for line in text.splitlines():
        found = re.match(r"^([A-Za-z0-9][A-Za-z0-9_-]*)\s*=\s*(\S.*)$", line)
        if found:
            messages[found.group(1)] = found.group(2).strip()
    return messages


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def manifest_lists(text: str, section: str) -> list[str]:
    nodes = parse_miniyaml(text)
    node = next((candidate for candidate in nodes if candidate.key == section), None)
    if node is None:
        return []
    return [child.key for child in node.children]


def mod_paths(entries: list[str], mod_dir: str) -> list[str]:
    paths = []
    for entry in entries:
        package, _, relative = entry.partition("|")
        if package == "ra2":
            paths.append(f"{mod_dir}/{relative}")
        # common| and engine packages hold no faction actors.
    return paths


def split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Tech tree
# ---------------------------------------------------------------------------

@dataclass
class Actor:
    id: str
    name: str
    queues: list[str]
    prerequisites: list[str]
    order: int
    cost: int
    build_limit: int
    provides: list[tuple[str, list[str]]]  # (token, factions)
    produces: list[str]
    transforms: str
    roles: list[str] = field(default_factory=list)


def actors_from_rules(rules: dict[str, Node], names: dict[str, str]) -> dict[str, Actor]:
    actors: dict[str, Actor] = {}
    for actor_id, node in rules.items():
        if actor_id.startswith("^") or actor_id in {"World", "Player", "EditorWorld"}:
            continue
        buildable = node.child("Buildable")
        tooltip = next((child for child in node.children if child.key == "Tooltip" or child.key.startswith("Tooltip@")), None) or next(
            (child for child in node.children if child.key.split("@", 1)[0].endswith("Tooltip") and child.get("Name")), None
        )
        raw_name = tooltip.get("Name") if tooltip else ""
        name = names.get(raw_name, raw_name) if raw_name else ""
        provides: list[tuple[str, list[str]]] = []
        for child in node.children:
            if not (child.key == "ProvidesPrerequisite" or child.key.startswith("ProvidesPrerequisite@")):
                continue
            condition = child.get("RequiresCondition")
            if condition and not condition.startswith("!"):
                # Conditional providers (infiltration, upgrades) are not part of the normal tree.
                continue
            token = child.get("Prerequisite") or actor_id
            provides.append((token.lower(), [faction.lower() for faction in split_list(child.get("Factions"))]))
        production = next((child for child in node.children if child.key == "Production" or child.key.startswith("Production@")), None)
        transforms = node.child("Transforms")
        valued = node.child("Valued")
        strategic_role = node.child("StrategicRole")
        actors[actor_id.lower()] = Actor(
            id=actor_id.lower(),
            name=name,
            queues=split_list(buildable.get("Queue")) if buildable else [],
            prerequisites=[item.lower() for item in split_list(buildable.get("Prerequisites"))] if buildable else [],
            order=int(re.sub(r"[^0-9-]", "", buildable.get("BuildPaletteOrder", "0")) or 0) if buildable else 0,
            cost=int(re.sub(r"[^0-9]", "", valued.get("Cost", "0")) or 0) if valued else 0,
            build_limit=int(re.sub(r"[^0-9]", "", buildable.get("BuildLimit", "0")) or 0) if buildable else 0,
            provides=provides,
            produces=split_list(production.get("Produces")) if production else [],
            transforms=(transforms.get("IntoActor").lower() if transforms else ""),
            roles=split_list(strategic_role.get("Roles")) if strategic_role else [],
        )
    return actors


def player_tokens(rules: dict[str, Node], faction: str) -> set[str]:
    tokens: set[str] = set()
    player = rules.get("Player")
    if player is None:
        return tokens
    for child in player.children:
        if child.key == "ProvidesPrerequisite" or child.key.startswith("ProvidesPrerequisite@"):
            factions = [item.lower() for item in split_list(child.get("Factions"))]
            if not factions or faction in factions:
                tokens.add(child.get("Prerequisite").lower())
        if child.key.startswith("ProvidesTechPrerequisite"):
            tokens.update(item.lower() for item in split_list(child.get("Prerequisites")))
    return tokens


def _applies(factions: list[str], faction: str) -> bool:
    return not factions or faction in factions


def requirement_met(token: str, available: set[str]) -> bool:
    bare = token.lstrip("~")
    if bare.startswith("!"):
        return bare[1:] not in available
    return bare in available


def faction_tree(rules: dict[str, Node], actors: dict[str, Actor], faction: str) -> dict:
    world = rules["World"]
    base_actors = [
        child.get("BaseActor").lower()
        for child in world.children
        if child.key.startswith("StartingUnits") and faction in [item.lower() for item in split_list(child.get("Factions"))]
        and child.get("BaseActor")
    ]
    base = base_actors[0] if base_actors else ""
    owned: set[str] = set()
    if base:
        owned.add(base)
        if base in actors and actors[base].transforms:
            owned.add(actors[base].transforms)
    static = player_tokens(rules, faction)

    def tokens_of(ids: set[str]) -> set[str]:
        provided = set(static)
        for actor_id in ids:
            actor = actors.get(actor_id)
            if actor is None:
                continue
            for token, factions in actor.provides:
                if _applies(factions, faction):
                    provided.add(token)
            for queue in actor.produces:
                provided.add(f"queue:{queue.lower()}")
        return provided

    buildable: set[str] = set()
    changed = True
    while changed:
        changed = False
        provided = tokens_of(owned | buildable)
        for actor in actors.values():
            if actor.id in buildable or not actor.queues or "~disabled" in actor.prerequisites:
                continue
            positives = [token for token in actor.prerequisites if not token.lstrip("~").startswith("!")]
            negatives = [token.lstrip("~")[1:] for token in actor.prerequisites if token.lstrip("~").startswith("!")]
            if any(token in static for token in negatives):
                continue
            if not all(token.lstrip("~") in provided for token in positives):
                continue
            if not any(f"queue:{queue.lower()}" in provided for queue in actor.queues):
                continue
            buildable.add(actor.id)
            changed = True
    final_tokens = tokens_of(owned | buildable)
    # Items replaced by another one the faction can reach ("!infantry.iraq").
    buildable = {
        actor_id for actor_id in buildable
        if not any(
            token.lstrip("~").startswith("!") and token.lstrip("~")[1:] in final_tokens and token.lstrip("~")[1:] not in static
            for token in actors[actor_id].prerequisites
        )
    }

    reachable = owned | buildable

    def providers(token: str) -> list[str]:
        if token.startswith("queue:"):
            queue = token.split(":", 1)[1]
            found = [actor_id for actor_id in reachable if queue in [item.lower() for item in actors[actor_id].produces]]
        else:
            found = [
                actor_id for actor_id in reachable
                if any(provided == token and _applies(factions, faction) for provided, factions in actors[actor_id].provides)
            ]
        return sorted(found, key=lambda actor_id: (actors[actor_id].order or 9999, actors[actor_id].cost, actor_id))

    items: dict[str, dict] = {}
    for actor_id in sorted(reachable):
        actor = actors[actor_id]
        needs: list[list[str]] = []
        for token in actor.prerequisites:
            bare = token.lstrip("~")
            if bare.startswith("!") or bare in static:
                continue
            group = providers(bare)
            if group and actor_id not in group and group not in needs:
                needs.append(group)
        for queue in actor.queues:
            group = providers(f"queue:{queue.lower()}")
            if group and actor_id not in group and not any(set(group) == set(existing) for existing in needs):
                needs.append(group)
                break
        kind = "building" if any(queue in {"Building", "Defense", "Support"} for queue in actor.queues) else "unit"
        if actor_id in owned and not actor.queues:
            kind = "building" if not actor.transforms else "unit"
        items[actor_id] = {
            "name": actor.name or actor_id,
            "queue": actor.queues[0] if actor.queues else "",
            "kind": kind,
            "cost": actor.cost,
            "order": actor.order,
            **({"limit": actor.build_limit} if actor.build_limit else {}),
            "needs": needs,
            "provides": sorted({token for token, factions in actor.provides if _applies(factions, faction)}),
            **({"roles": actor.roles} if actor.roles else {}),
            **({"produces": sorted({queue.lower() for queue in actor.produces})} if actor.produces else {}),
        }
    return {"base": base, "start": sorted(owned), "items": items}


def build_profile(source: Source, mod_dir: str) -> tuple[dict, dict[str, str]]:
    manifest = source.read(f"{mod_dir}/mod.yaml")
    if manifest is None:
        raise SystemExit(f"{source.root}: no {mod_dir}/mod.yaml")
    documents = []
    for path in mod_paths(manifest_lists(manifest, "Rules"), mod_dir):
        text = source.read(path)
        if text is None:
            raise SystemExit(f"{source.root}: missing rules file {path}")
        documents.append(parse_miniyaml(text))
    names: dict[str, str] = {}
    for path in mod_paths(manifest_lists(manifest, "FluentMessages"), mod_dir):
        text = source.read(path)
        if text is not None:
            names.update(parse_fluent(text))
    rules = resolve(merge_files(documents))
    actors = actors_from_rules(rules, names)
    factions: dict[str, dict] = {}
    for child in rules["World"].children:
        if not child.key.startswith("Faction@"):
            continue
        internal = child.get("InternalName").lower()
        if not internal or child.get("RandomFactionMembers") or child.get("Selectable", "True").lower() == "false":
            continue
        tree = faction_tree(rules, actors, internal)
        if not tree["items"] or len(tree["items"]) <= len(tree["start"]):
            continue
        display = names.get(child.get("Name"), child.get("Name"))
        factions[internal] = {"name": display, "side": child.get("Side"), **tree}
    return factions, names


def catalog_aliases() -> dict[str, dict]:
    """Catalog names (and their Classic variants) for each RA2 actor, by faction."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    engine_ids = {
        faction["id"]: (faction.get("variants", {}).get("ra2", {}) or {}).get("engineFactionId", faction["id"])
        for faction in catalog["factions"]
    }
    aliases: dict[str, dict] = {}
    for unit in catalog["units"]:
        variant = (unit.get("variants") or {}).get("ra2") or {}
        actor_id = str(variant.get("actorId", "")).lower()
        if not actor_id:
            continue
        names = [unit.get("name", ""), variant.get("name", ""), ((unit.get("variants") or {}).get("ra") or {}).get("name", "")]
        aliases[actor_id] = {
            "faction": engine_ids.get(unit.get("factionId", ""), unit.get("factionId", "")),
            "names": sorted({name for name in names if name}),
            "role": variant.get("role") or unit.get("role", ""),
        }
    return aliases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", action="append", required=True,
                        help="name=<mod checkout>[@<git ref>], e.g. rtsai=../RTSAI-Mod@main")
    parser.add_argument("--mod-dir", default="mods/rtsai")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    profiles: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    for spec in args.profile:
        name, _, location = spec.partition("=")
        root, _, ref = location.partition("@")
        source = Source((REPOSITORY / root).resolve() if not Path(root).is_absolute() else Path(root), ref or None)
        factions, _ = build_profile(source, args.mod_dir)
        profiles[name] = {"factions": factions}
        sources[name] = {"ref": ref or "worktree", "commit": source.commit()}

    document = {
        "schema": 1,
        "description": "Per-faction build options, names and prerequisites resolved from the RTS AI mod rules "
                       "(scripts/build-companion-tech-tree.py). 'needs' lists groups of alternative buildings; "
                       "one building of every group must be owned.",
        "sources": sources,
        "catalog": catalog_aliases(),
        "profiles": profiles,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, profile in profiles.items():
        counts = ", ".join(f"{faction} {len(tree['items'])}" for faction, tree in sorted(profile["factions"].items()))
        print(f"{name}: {counts}")
    print(f"wrote {args.output.resolve()} ({args.output.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
