#!/usr/bin/env python3
"""Build an isolated native RA2 preview using locally owned game data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "apps/installer/ra2"
SUPPORT = Path.home() / "Library/Application Support/OpenRA AI/RA2 Preview"
STEAM_DEPOTS = Path.home() / (
    "Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS/"
    "steamapps/content/app_2229850"
)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(*args: object, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def content_file(directory: Path, name: str) -> Path:
    if not directory.is_dir():
        raise ValueError(f"Game data directory does not exist: {directory}")
    matches = [p for p in directory.iterdir() if p.name.lower() == name.lower()]
    if len(matches) != 1 or not matches[0].is_file() or matches[0].is_symlink():
        raise ValueError(f"Expected one regular {name} file in {directory}")
    if matches[0].stat().st_size < 1024:
        raise ValueError(f"{matches[0]} is not a complete game archive")
    return matches[0]


def import_content(base: Path, language: Path, destination: Path) -> dict[str, str]:
    sources = {
        "ra2.mix": content_file(base, "ra2.mix"),
        "language.mix": content_file(language, "language.mix"),
    }
    if any(p.name.lower() == "theme.mix" for p in base.iterdir()):
        sources["theme.mix"] = content_file(base, "theme.mix")
    hashes = {name: digest(path) for name, path in sources.items()}
    destination.mkdir(parents=True, exist_ok=True)
    for name in sources:
        target = destination / name
        if target.is_symlink() or (target.exists() and digest(target) != hashes[name]):
            raise ValueError(f"Refusing to replace different existing game data: {target}")
    for name, source in sources.items():
        target = destination / name
        if target.exists():
            continue
        with tempfile.NamedTemporaryFile(dir=destination, prefix=".import-", delete=False) as stream:
            staging = Path(stream.name)
            with source.open("rb") as original:
                shutil.copyfileobj(original, stream)
        try:
            if digest(staging) != hashes[name]:
                raise ValueError(f"Source changed while importing {name}; please retry")
            os.link(staging, target)
        finally:
            staging.unlink(missing_ok=True)
    return hashes


def extract_source(archive: Path, destination: Path, commit: str) -> Path:
    prefix = f"ra2-{commit}"
    with tarfile.open(archive, "r:gz") as bundle:
        members = []
        for member in bundle.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or path.parts[0] != prefix:
                raise ValueError(f"Unsafe source archive path: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"Unsupported source archive entry: {member.name}")
            if ".github" not in path.parts and ".vscode" not in path.parts:
                members.append(member)
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
    return destination / prefix


def download_source(manifest: dict, cache: Path) -> Path:
    archive = cache / f"ra2-{manifest['commit']}.tar.gz"
    if archive.exists():
        if digest(archive) != manifest["archive_sha256"]:
            raise ValueError(f"Cached source checksum mismatch: {archive}")
        return archive
    with tempfile.NamedTemporaryFile(dir=cache, prefix=".download-", delete=False) as stream:
        staging = Path(stream.name)
        try:
            request = urllib.request.Request(
                manifest["archive_url"], headers={"User-Agent": "RTSAI-native-preview"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                shutil.copyfileobj(response, stream)
            stream.flush()
            if digest(staging) != manifest["archive_sha256"]:
                raise ValueError("RA2 source download checksum mismatch")
            os.link(staging, archive)
        finally:
            staging.unlink(missing_ok=True)
    return archive


def build(args: argparse.Namespace) -> Path:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("This native preview currently targets Apple Silicon macOS only")
    manifest = json.loads((CONFIG / "upstream.json").read_text())
    engine = ROOT / "engine/openra"
    actual = subprocess.check_output(["git", "-C", str(engine), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(engine), "status", "--porcelain"], text=True)
    if actual != manifest["engine_commit"] or dirty.strip():
        raise ValueError("RA2 compatibility requires the clean pinned engine; no checkout was changed")
    install = Path("/Applications/Red Alert 2 Preview.app")
    if args.install and install.exists():
        raise ValueError(f"Will not overwrite {install}; move the older preview aside first")
    cache = ROOT / "artifacts/ra2-native"
    cache.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="build-", dir=cache))
    print(f"Isolated build: {workspace}", flush=True)
    source = extract_source(download_source(manifest, cache), workspace, manifest["commit"])
    run("git", "apply", "--check", CONFIG / "compatibility.patch", cwd=source)
    run("git", "apply", CONFIG / "compatibility.patch", cwd=source)
    for path in (source / "mods/ra2").rglob("*.yaml"):
        path.write_text(path.read_text().replace("{DEV_VERSION}", manifest["version"]))
    binaries = workspace / "bin"
    properties = (
        "-c", "Release", f"-p:EngineRootPath={engine}",
        f"-p:OutputPath={binaries}", "-p:TargetPlatform=osx-arm64", "--nologo",
    )
    run("dotnet", "build", engine / "OpenRA.slnx", *properties)
    run("dotnet", "build", source / "OpenRA.Mods.RA2/OpenRA.Mods.RA2.csproj", *properties)
    app = workspace / "Red Alert 2 Preview.app"
    macos = app / "Contents/MacOS"
    resources = app / "Contents/Resources"
    run("dotnet", "publish", CONFIG / "RA2Launcher.csproj",
        *properties, "-p:OutputPath=" + str(workspace / "launcher-bin"),
        "-r", "osx-arm64", "--self-contained", "true", "-o", macos)
    resources.mkdir(parents=True)
    shutil.copy2(CONFIG / "Info.plist", app / "Contents/Info.plist")
    for name in ("AUTHORS", "COPYING", "global mix database.dat"):
        shutil.copy2(engine / name, resources / name)
    (resources / "VERSION").write_text(manifest["version"] + "\n")
    shutil.copytree(engine / "glsl", resources / "glsl")
    shutil.copytree(engine / "mods/common", resources / "mods/common")
    shutil.copy2(engine / "mods/ts/uibits/glyphs.png", resources / "mods/common/native-ra2-glyphs.png")
    shutil.copytree(source / "mods/ra2", resources / "mods/ra2")
    for path in binaries.iterdir():
        if path.suffix in (".dll", ".dylib") or path.name.endswith(".deps.json"):
            shutil.copy2(path, macos / path.name)
    owned_hashes = import_content(args.base_content, args.language_content, SUPPORT / "Content/ra2")
    environment = dict(os.environ, ENGINE_DIR=str(resources), SUPPORT_DIR=str(SUPPORT))
    with (workspace / "ra2-lint.log").open("w") as output:
        subprocess.run(
            ["dotnet", str(binaries / "OpenRA.Utility.dll"), str(resources / "mods/ra2"), "--check-yaml"],
            env=environment, cwd=workspace, stdout=output, stderr=subprocess.STDOUT, check=True,
        )
    print(f"RA2 rules/maps validation passed. Warnings: {workspace / 'ra2-lint.log'}", flush=True)
    evidence = {
        **manifest, "product_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "content_sha256": owned_hashes, "release_status": "local-preview-not-an-official-release",
        "ai_assistant": False, "original_campaigns": False, "yuris_revenge": False,
    }
    (resources / "BUILD.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if any(resources.rglob("*.mix")):
        raise ValueError("Proprietary game data must never be bundled in the app")
    run("codesign", "--force", "--deep", "--sign", "-", app)
    run("codesign", "--force", "--sign", "-", "--entitlements",
        ROOT / "apps/installer/macos/OpenRAAI.entitlements", macos / "RA2Launcher")
    run("codesign", "--force", "--sign", "-", "--entitlements",
        ROOT / "apps/installer/macos/OpenRAAI.entitlements", app)
    run("codesign", "--verify", "--deep", "--strict", app)
    if args.install:
        run("ditto", app, install)
        run("codesign", "--verify", "--deep", "--strict", install)
        app = install
    if args.launch:
        run("open", app)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-content", type=Path, default=STEAM_DEPOTS / "depot_2229851")
    parser.add_argument("--language-content", type=Path, default=STEAM_DEPOTS / "depot_2229852")
    parser.add_argument("--install", action="store_true", help="Install alongside existing OpenRA AI; never overwrite")
    parser.add_argument("--launch", action="store_true", help="Open the main menu, never auto-start a match")
    args = parser.parse_args()
    try:
        print(f"Ready: {build(args)}")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"RA2 preview: {error}\n")


if __name__ == "__main__":
    main()
