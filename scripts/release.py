#!/usr/bin/env python3
"""Cross-platform, local-only release orchestrator for OpenRA AI."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = REPOSITORY_ROOT / "packaging" / "release-plan.json"
RELEASE_ROOT = REPOSITORY_ROOT / "artifacts" / "releases"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?$")


class ReleaseError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_value(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=REPOSITORY_ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def load_plan() -> dict:
    try:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"Unable to read release plan: {exc}") from exc
    if plan.get("schema_version") != 1 or not isinstance(plan.get("targets"), dict):
        raise ReleaseError("Unsupported or invalid release plan")
    return plan


def host_name() -> str:
    return {"Windows": "windows", "Darwin": "darwin", "Linux": "linux"}.get(platform.system(), "unknown")


def normalized_architecture() -> str:
    return platform.machine().lower()


def validate_version(version: str) -> None:
    if not VERSION_PATTERN.fullmatch(version):
        raise ReleaseError("Version must look like 0.1.0 or 0.1.0-alpha.9")


def dirty_paths() -> list[str]:
    output = git_value("status", "--porcelain")
    return output.splitlines() if output else []


def format_command(command: dict, version: str) -> list[str]:
    values = {"version": version, "repository_root": str(REPOSITORY_ROOT)}
    return [str(command["program"]).format(**values), *[
        str(argument).format(**values) for argument in command.get("arguments", [])
    ]]


def run_command(command: dict, version: str, dry_run: bool) -> None:
    arguments = format_command(command, version)
    print("+ " + subprocess.list2cmdline(arguments), flush=True)
    if not dry_run:
        subprocess.run(arguments, cwd=REPOSITORY_ROOT, check=True)


def selected_target(plan: dict, target_name: str, *, enforce_host: bool = True) -> dict:
    try:
        target = plan["targets"][target_name]
    except KeyError as exc:
        raise ReleaseError(f"Unknown release target: {target_name}") from exc
    current_host = host_name()
    if enforce_host and current_host not in target.get("hosts", []):
        expected = ", ".join(target.get("hosts", []))
        raise ReleaseError(
            f"{target_name} requires a {expected} host; this machine is {current_host}. "
            "Apple .app/DMG creation, signing, and notarization must run on macOS."
        )
    architectures = [value.lower() for value in target.get("architectures", [])]
    if enforce_host and architectures and normalized_architecture() not in architectures:
        raise ReleaseError(
            f"{target_name} requires {', '.join(architectures)}; this machine is {normalized_architecture()}"
        )
    return target


def artifact_record(path: Path, target: str) -> dict:
    return {
        "name": path.name,
        "target": target,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def build_index(plan: dict, version: str, require_target: str | None = None) -> Path:
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    missing_required: list[str] = []
    for target_name, target in plan["targets"].items():
        for pattern in target.get("artifacts", []):
            artifact_name = pattern.format(version=version)
            artifact = RELEASE_ROOT / artifact_name
            if artifact.is_file():
                records.append(artifact_record(artifact, target_name))
            elif target_name == require_target:
                missing_required.append(artifact_name)

    for ai_pack in RELEASE_ROOT.glob(f"OpenRA-AI-AI-Pack-{version}-*.zip"):
        target = ai_pack.stem.removeprefix(f"OpenRA-AI-AI-Pack-{version}-")
        records.append(artifact_record(ai_pack, target))
    if missing_required:
        raise ReleaseError("Expected release artifacts are missing: " + ", ".join(missing_required))
    if not records:
        raise ReleaseError(f"No release artifacts found for {version}")

    product_commit = git_value("rev-parse", "HEAD")
    engine_commit = git_value("-C", "engine/openra", "rev-parse", "HEAD")
    index = {
        "schema_version": 1,
        "product": plan["product"],
        "version": version,
        "product_commit": product_commit,
        "engine_commit": engine_commit,
        "worktree_dirty": bool(dirty_paths()),
        "generated_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "artifacts": sorted(records, key=lambda record: (record["target"], record["name"])),
    }
    output = RELEASE_ROOT / f"OpenRA-AI-{version}-release-index.json"
    output.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output.with_name(output.name + ".sha256").write_text(sha256(output) + "\n", encoding="ascii")
    print(f"Release index: {output}")
    return output


def verify_index(version: str) -> None:
    index_path = RELEASE_ROOT / f"OpenRA-AI-{version}-release-index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"Unable to read release index: {exc}") from exc
    if index.get("version") != version or index.get("schema_version") != 1:
        raise ReleaseError("Release index version or schema does not match")
    for record in index.get("artifacts", []):
        path = RELEASE_ROOT / record["name"]
        if not path.is_file():
            raise ReleaseError(f"Indexed artifact is missing: {path.name}")
        if path.stat().st_size != record["bytes"]:
            raise ReleaseError(f"Indexed artifact size changed: {path.name}")
        actual = sha256(path)
        if actual != record["sha256"]:
            raise ReleaseError(f"Indexed artifact checksum changed: {path.name}")
    print(f"Verified {len(index.get('artifacts', []))} release artifacts for {version}")


def build(args: argparse.Namespace, plan: dict) -> None:
    target = selected_target(plan, args.target)
    changes = dirty_paths()
    if changes and not args.allow_dirty:
        preview = "\n".join(changes[:10])
        raise ReleaseError(f"Release builds require a clean worktree. Changed paths:\n{preview}")

    if not args.skip_checks:
        if host_name() == "windows":
            run_command({
                "program": "powershell.exe",
                "arguments": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/check.ps1", "-FullEngine"],
            }, args.version, args.dry_run)
        else:
            print("macOS validation is performed by package-macos.sh and the DMG smoke test.")

    include_ai_pack = args.include_ai_pack or target.get("include_ai_pack_by_default", False)
    if include_ai_pack:
        command = [
            sys.executable,
            "scripts/ai_pack.py",
            "build",
            "--release-version",
            args.version,
            "--target",
            args.target,
        ]
        print("+ " + subprocess.list2cmdline(command), flush=True)
        if not args.dry_run:
            subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)
    run_command(target["build"], args.version, args.dry_run)
    if not args.skip_smoke:
        for command in target.get("smoke", []):
            run_command(command, args.version, args.dry_run)
    if not args.dry_run:
        build_index(plan, args.version, require_target=args.target)


def show_plan(args: argparse.Namespace, plan: dict) -> None:
    target = selected_target(plan, args.target, enforce_host=False)
    print(f"Target: {args.target}")
    print(f"Required hosts: {', '.join(target.get('hosts', []))}")
    print(f"Required architectures: {', '.join(target.get('architectures', []))}")
    print(f"Current host: {host_name()} {normalized_architecture()}")
    print("Build: " + subprocess.list2cmdline(format_command(target["build"], args.version)))
    if target.get("include_ai_pack_by_default", False):
        print("Local AI pack: built by default")
    for command in target.get("smoke", []):
        print("Smoke: " + subprocess.list2cmdline(format_command(command, args.version)))
    print("Artifacts:")
    for artifact in target.get("artifacts", []):
        print(f"  {artifact.format(version=args.version)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "build"):
        command = subparsers.add_parser(name)
        command.add_argument("--version", required=True)
        command.add_argument("--target", required=True)
        if name == "build":
            command.add_argument("--skip-checks", action="store_true")
            command.add_argument("--skip-smoke", action="store_true")
            command.add_argument("--include-ai-pack", action="store_true")
            command.add_argument("--allow-dirty", action="store_true")
            command.add_argument("--dry-run", action="store_true")
    index = subparsers.add_parser("index")
    index.add_argument("--version", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--version", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate_version(args.version)
        plan = load_plan()
        if args.command == "plan":
            show_plan(args, plan)
        elif args.command == "build":
            build(args, plan)
        elif args.command == "index":
            build_index(plan, args.version)
        elif args.command == "verify":
            verify_index(args.version)
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
