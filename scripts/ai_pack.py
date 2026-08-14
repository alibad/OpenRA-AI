#!/usr/bin/env python3
"""Validate, download, and assemble the versioned local AI model pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK = REPOSITORY_ROOT / "packaging" / "ai-pack.lock.json"
DEFAULT_RUNTIME_LOCK = REPOSITORY_ROOT / "packaging" / "ai-runtime.lock.json"
DEFAULT_CACHE = REPOSITORY_ROOT / "artifacts" / "download-cache" / "ai-pack"
DEFAULT_RELEASES = REPOSITORY_ROOT / "artifacts" / "releases"
NOTICES = REPOSITORY_ROOT / "packaging" / "THIRD_PARTY_MODELS.md"
SHA256_LENGTH = 64


class PackError(RuntimeError):
    pass


def load_lock(path: Path) -> dict:
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackError(f"Unable to read AI pack lock {path}: {exc}") from exc
    validate_lock(lock)
    return lock


def validate_lock(lock: dict) -> None:
    if lock.get("schema_version") != 1:
        raise PackError("AI pack lock schema_version must be 1")
    if not str(lock.get("pack_version", "")).strip():
        raise PackError("AI pack lock requires pack_version")
    components = lock.get("components")
    if not isinstance(components, list) or not components:
        raise PackError("AI pack lock requires at least one component")

    ids: set[str] = set()
    destinations: set[str] = set()
    required = {"id", "capability", "license", "url", "sha256", "bytes", "destination"}
    for component in components:
        missing = required - set(component)
        if missing:
            raise PackError(f"AI component is missing {', '.join(sorted(missing))}")
        component_id = str(component["id"])
        if component_id in ids:
            raise PackError(f"Duplicate AI component id: {component_id}")
        ids.add(component_id)

        digest = str(component["sha256"]).lower()
        if len(digest) != SHA256_LENGTH or any(character not in "0123456789abcdef" for character in digest):
            raise PackError(f"Invalid SHA-256 for {component_id}")
        if not isinstance(component["bytes"], int) or component["bytes"] <= 0:
            raise PackError(f"Invalid byte length for {component_id}")
        if not str(component["url"]).startswith("https://"):
            raise PackError(f"Only HTTPS model sources are allowed: {component_id}")

        destination = PurePosixPath(str(component["destination"]))
        if destination.is_absolute() or ".." in destination.parts:
            raise PackError(f"Unsafe destination for {component_id}: {destination}")
        normalized = destination.as_posix()
        if normalized in destinations:
            raise PackError(f"Duplicate AI component destination: {normalized}")
        destinations.add(normalized)


def load_runtime_lock(path: Path, target: str) -> list[dict]:
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackError(f"Unable to read AI runtime lock {path}: {exc}") from exc
    if lock.get("schema_version") != 1 or not isinstance(lock.get("targets"), dict):
        raise PackError("AI runtime lock schema_version must be 1 and define targets")
    if target not in lock["targets"]:
        raise PackError(f"AI runtime lock does not define target {target}")
    components = lock["targets"][target].get("components")
    if not isinstance(components, list) or not components:
        raise PackError(f"AI runtime target {target} requires components")
    required = {"id", "license", "url", "sha256", "bytes", "destination", "archive"}
    for component in components:
        missing = required - set(component)
        if missing:
            raise PackError(f"AI runtime component is missing {', '.join(sorted(missing))}")
        if component["archive"] != "zip":
            raise PackError(f"Unsupported runtime archive for {component['id']}: {component['archive']}")
        if not str(component["url"]).startswith("https://"):
            raise PackError(f"Only HTTPS runtime sources are allowed: {component['id']}")
        digest = str(component["sha256"]).lower()
        if len(digest) != SHA256_LENGTH or any(character not in "0123456789abcdef" for character in digest):
            raise PackError(f"Invalid runtime SHA-256 for {component['id']}")
        destination = PurePosixPath(str(component["destination"]))
        if destination.is_absolute() or ".." in destination.parts:
            raise PackError(f"Unsafe runtime destination for {component['id']}: {destination}")
    return components


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cache_path(cache_root: Path, component: dict) -> Path:
    suffixes = "".join(Path(component["destination"]).suffixes)
    return cache_root / f"{component['sha256']}{suffixes}"


def hugging_face_reference(url: str) -> tuple[str, str, str] | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname not in {"huggingface.co", "www.huggingface.co"}:
        return None
    parts = [urllib.parse.unquote(part) for part in parsed.path.strip("/").split("/")]
    if len(parts) < 5 or parts[2] != "resolve":
        return None
    return f"{parts[0]}/{parts[1]}", parts[3], "/".join(parts[4:])


def verify_component(path: Path, component: dict) -> None:
    if not path.is_file():
        raise PackError(f"Missing cached component {component['id']}: {path}")
    actual_size = path.stat().st_size
    if actual_size != component["bytes"]:
        raise PackError(
            f"Size mismatch for {component['id']}: expected {component['bytes']}, got {actual_size}"
        )
    actual_hash = sha256(path)
    if actual_hash != component["sha256"]:
        raise PackError(
            f"SHA-256 mismatch for {component['id']}: expected {component['sha256']}, got {actual_hash}"
        )


def download_component(cache_root: Path, component: dict) -> Path:
    destination = cache_path(cache_root, component)
    if destination.exists():
        verify_component(destination, component)
        print(f"Using cached {component['id']}")
        return destination

    cache_root.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    existing = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "OpenRA-AI-Packager/1"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(component["url"], headers=headers)
    print(f"Downloading {component['id']} ({component['bytes'] / 1024 / 1024:.1f} MiB)")
    hub_reference = hugging_face_reference(component["url"])
    if hub_reference:
        try:
            from huggingface_hub import hf_hub_download

            repo_id, revision, filename = hub_reference
            downloaded = hf_hub_download(repo_id=repo_id, revision=revision, filename=filename)
            shutil.copyfile(downloaded, partial)
        except Exception as exc:
            raise PackError(f"Hugging Face download failed for {component['id']}: {exc}") from exc
    else:
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                resumed = existing > 0 and response.status == 206
                mode = "ab" if resumed else "wb"
                if existing and not resumed:
                    existing = 0
                with partial.open(mode) as output:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        output.write(block)
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise PackError(f"Download failed for {component['id']}: {exc}") from exc

    verify_component(partial, component)
    partial.replace(destination)
    return destination


def fetch(lock: dict, cache_root: Path) -> list[Path]:
    return [download_component(cache_root, component) for component in lock["components"]]


def deterministic_zip(source_root: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
        for path in sorted(item for item in source_root.rglob("*") if item.is_file()):
            relative = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED if path.suffix.lower() in {".json", ".md", ".txt"} else zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            info.file_size = path.stat().st_size
            with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
    temporary.replace(output)


def extract_runtime(source: Path, destination: Path, component: dict) -> None:
    strip_prefix = str(component.get("strip_prefix") or "").strip("/")
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            relative = PurePosixPath(member.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise PackError(f"Unsafe archive member in {component['id']}: {member.filename}")
            parts = list(relative.parts)
            if strip_prefix:
                prefix_parts = list(PurePosixPath(strip_prefix).parts)
                if parts[:len(prefix_parts)] != prefix_parts:
                    continue
                parts = parts[len(prefix_parts):]
            if not parts:
                continue
            output = destination.joinpath(*parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as input_stream, output.open("wb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)


def build(lock: dict, runtime_components: list[dict], cache_root: Path, release_root: Path,
          release_version: str, target: str) -> Path:
    cached = fetch(lock, cache_root)
    release_name = f"OpenRA-AI-AI-Pack-{release_version}-{target}"
    stage_root = REPOSITORY_ROOT / "artifacts" / "ai-pack" / release_name
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True)

    packaged_components: list[dict] = []
    for component, source in zip(lock["components"], cached, strict=True):
        destination = stage_root / Path(*PurePosixPath(component["destination"]).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        packaged_components.append({
            key: component[key]
            for key in ("id", "capability", "license", "source_revision", "sha256", "bytes", "destination")
            if key in component
        })

    packaged_runtimes: list[dict] = []
    for component in runtime_components:
        source = download_component(cache_root, component)
        destination = stage_root / Path(*PurePosixPath(component["destination"]).parts)
        extract_runtime(source, destination, component)
        packaged_runtimes.append({
            key: component[key]
            for key in ("id", "license", "source_revision", "sha256", "bytes", "destination")
            if key in component
        })

    shutil.copy2(NOTICES, stage_root / "THIRD_PARTY_MODELS.md")
    pack_manifest = {
        "schema_version": 1,
        "name": lock["name"],
        "release_version": release_version,
        "pack_version": lock["pack_version"],
        "target": target,
        "hardware_requirements": lock["hardware_requirements"],
        "payload_bytes": sum(component["bytes"] for component in lock["components"]),
        "components": packaged_components,
        "runtimes": packaged_runtimes,
    }
    (stage_root / "pack.json").write_text(
        json.dumps(pack_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    output = release_root / f"{release_name}.zip"
    deterministic_zip(stage_root, output)
    digest = sha256(output)
    output.with_name(output.name + ".sha256").write_text(digest + "\n", encoding="ascii")
    print(f"AI pack: {output}")
    print(f"SHA-256: {digest}")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "fetch", "build"))
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--runtime-lock", type=Path, default=DEFAULT_RUNTIME_LOCK)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASES)
    parser.add_argument("--release-version")
    parser.add_argument("--target", default="windows-x64")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        lock = load_lock(args.lock.resolve())
        runtime_components = load_runtime_lock(args.runtime_lock.resolve(), args.target)
        total = sum(component["bytes"] for component in lock["components"])
        print(f"AI pack lock is valid: {len(lock['components'])} components, {total / 1024 / 1024:.1f} MiB")
        if args.command == "fetch":
            fetch(lock, args.cache.resolve())
        elif args.command == "build":
            if not args.release_version:
                raise PackError("build requires --release-version")
            build(lock, runtime_components, args.cache.resolve(), args.release_root.resolve(), args.release_version, args.target)
    except PackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
