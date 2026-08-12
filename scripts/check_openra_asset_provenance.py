#!/usr/bin/env python3
"""Validate reusable asset provenance, exact hashes, and acceptance evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "upstream-reuse"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    validator = Draft202012Validator(load(DOCS / "asset.schema.json"))
    errors: list[str] = []
    manifests = sorted((DOCS / "assets").glob("*.json"))
    seen_ids: set[str] = set()

    for path in manifests:
        document = load(path)
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path)):
            location = ".".join(str(part) for part in error.path) or "<root>"
            errors.append(f"{path.name}:{location}: {error.message}")

        manifest_id = document.get("id")
        if manifest_id in seen_ids:
            errors.append(f"duplicate asset manifest ID: {manifest_id}")
        seen_ids.add(manifest_id)

        for source in document.get("generator", {}).get("sources", []):
            if not (ROOT / source).is_file():
                errors.append(f"{path.name}: missing generator source {source}")

        for asset in document.get("assets", []):
            asset_path = ROOT / asset["path"]
            if not asset_path.is_file():
                errors.append(f"{path.name}: missing asset {asset['path']}")
                continue
            digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
            if digest != asset["sha256"]:
                errors.append(f"{path.name}: hash mismatch for {asset['path']}")

        for evidence in document.get("verification", {}).get("evidence", []):
            if not (ROOT / evidence).exists():
                errors.append(f"{path.name}: missing verification evidence {evidence}")

        verification = document.get("verification", {})
        if verification.get("structural") == "passed" and verification.get("live_turn") != "passed":
            errors.append(f"{path.name}: structural sprite checks cannot replace live turning validation")

    if not manifests:
        errors.append("no asset provenance manifests found")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    asset_count = sum(len(load(path)["assets"]) for path in manifests)
    print(f"validated {len(manifests)} asset manifest(s) and {asset_count} exact file hash(es)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
