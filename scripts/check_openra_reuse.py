#!/usr/bin/env python3
"""Validate the pinned OpenRA reuse catalog, component manifests, and roadmap."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import re

from jsonschema import Draft202012Validator
from openra_upstream_inventory import target_baseline


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "upstream-reuse"
REFERENCES = ROOT.parent / "OpenRA-Upstreams"


def composer_component_ids(path: Path) -> tuple[set[str], set[str]]:
    """Read the small fixed-indent ExperienceCatalog without treating MiniYAML as YAML."""
    component_ids: set[str] = set()
    default_components: set[str] = set()
    section = None
    profile = None
    component_pattern = re.compile(r"^\t\t([a-z0-9]+(?:-[a-z0-9]+)*):$")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "\tComponents:":
            section = "components"
            continue
        if line == "\tProfiles:":
            section = "profiles"
            continue

        match = component_pattern.match(line)
        if match and section == "components":
            component_ids.add(match.group(1))
        elif match and section == "profiles":
            profile = match.group(1)
        elif section == "profiles" and profile == "world-war-iii" and line.startswith("\t\t\tComponents:"):
            value = line.split(":", 1)[1]
            default_components.update(part.strip() for part in value.split(",") if part.strip())

    return component_ids, default_components


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def git_head(path: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    sources_document = load(DOCS / "sources.json")
    source_list = sources_document["projects"]
    sources = {source["id"]: source for source in source_list}
    if len(sources) != len(source_list):
        fail(errors, "sources.json contains duplicate project IDs")

    for source_id, source in sources.items():
        checkout = REFERENCES / source["checkout"]
        if not checkout.is_dir():
            fail(errors, f"{source_id}: missing checkout {checkout}")
            continue
        actual = git_head(checkout)
        if actual != source["commit"]:
            fail(errors, f"{source_id}: expected {source['commit']}, found {actual}")

    catalog = load(DOCS / "generated" / "catalog.json")
    _, current_target = target_baseline()
    if catalog["target"] != current_target:
        fail(errors, "generated catalog target baseline is stale; rebuild the inventory")
    catalog_sources = {project["id"]: project for project in catalog["projects"]}
    if set(catalog_sources) != set(sources):
        fail(errors, "generated catalog project IDs do not match sources.json")
    for source_id, source in sources.items():
        if source_id in catalog_sources and catalog_sources[source_id]["commit"] != source["commit"]:
            fail(errors, f"{source_id}: generated catalog pin is stale")

    schema = load(DOCS / "component.schema.json")
    validator = Draft202012Validator(schema)
    manifests: dict[str, dict] = {}
    for path in sorted((DOCS / "components").glob("*.json")):
        manifest = load(path)
        schema_errors = sorted(validator.iter_errors(manifest), key=lambda error: list(error.path))
        for error in schema_errors:
            location = ".".join(str(part) for part in error.path) or "<root>"
            fail(errors, f"{path.name}:{location}: {error.message}")

        component_id = manifest.get("id")
        if component_id in manifests:
            fail(errors, f"duplicate component manifest ID: {component_id}")
        manifests[component_id] = manifest

        for origin in manifest.get("sources", []):
            source_id = origin["project"]
            source = sources.get(source_id)
            if source is None:
                fail(errors, f"{path.name}: unknown source {source_id}")
                continue
            if origin["commit"] != source["commit"]:
                fail(errors, f"{path.name}: source pin for {source_id} differs from sources.json")
            checkout = REFERENCES / source["checkout"]
            for relative in origin["paths"]:
                if not (checkout / Path(relative)).exists():
                    fail(errors, f"{path.name}: missing upstream path {source_id}/{relative}")

        for relative in manifest.get("integration", {}).get("files", []):
            if not (ROOT / Path(relative)).exists():
                fail(errors, f"{path.name}: missing integration file {relative}")

        if manifest.get("status") in {"integrated", "verified"}:
            verification = manifest.get("verification", {})
            if verification.get("build") != "passed" or verification.get("lint") != "passed":
                fail(errors, f"{path.name}: integrated component must pass build and lint")

    roadmap = load(DOCS / "roadmap.json")
    roadmap_items = roadmap["components"]
    roadmap_ids = [item["id"] for item in roadmap_items]
    if len(roadmap_ids) != len(set(roadmap_ids)):
        fail(errors, "roadmap.json contains duplicate component IDs")
    for item in roadmap_items:
        for source_id in item["sources"]:
            if source_id not in sources:
                fail(errors, f"roadmap {item['id']}: unknown source {source_id}")
        if item["status"] == "integrated" and item["id"] not in manifests:
            fail(errors, f"roadmap {item['id']}: integrated item has no component manifest")

    composer_ids, default_components = composer_component_ids(
        ROOT / "engine" / "openra" / "mods" / "ra" / "experiences.yaml"
    )
    roadmap_set = set(roadmap_ids)
    if composer_ids != roadmap_set:
        fail(errors, f"Experience Composer IDs differ from roadmap: missing={sorted(roadmap_set - composer_ids)}, extra={sorted(composer_ids - roadmap_set)}")
    if default_components != roadmap_set:
        fail(errors, f"World War III profile does not enable the full roadmap: missing={sorted(roadmap_set - default_components)}, extra={sorted(default_components - roadmap_set)}")
    if set(manifests) != roadmap_set:
        fail(errors, f"component manifest IDs differ from roadmap: missing={sorted(roadmap_set - set(manifests))}, extra={sorted(set(manifests) - roadmap_set)}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"reuse validation failed with {len(errors)} error(s)", file=sys.stderr)
        return 1

    print(
        f"validated {len(sources)} pinned sources, {len(catalog_sources)} catalog projects, "
        f"{len(manifests)} component manifests, and {len(roadmap_items)} roadmap components"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
