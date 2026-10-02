"""Install a checksum-pinned AI pack profile from the command line.

Used by the RTS AI Windows installer, which runs it through NSIS so every
progress line appears in the setup window:

    rtsai-companion.exe pack install --profile voice-only --root <companion dir>

The files, their sizes and SHA-256 digests come from packaging/ai-pack.lock.json.
Sources, in order: an offline archive (--archive, e.g. the voice pack zip next to
setup.exe), a local directory that already holds the files (--from-dir), then the
pinned HTTPS URLs. Nothing unverified is ever left under <root>/ai: downloads go to
``.partial`` files (resumable) and are renamed only after the digest matches. The
receipt (<root>/ai/pack.json) uses the same format as LocalAIManager, so the
companion treats a pack installed here exactly like one installed in game.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .model_selection import Hardware, choose_profile, selected_components, validate_profiles, voice_only_profile

PROFILE_ALIASES = {"voice": "voice-only", "full": "recommended", "local": "recommended"}


class PackInstallError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _destination(root: Path, component: dict) -> Path:
    relative = PurePosixPath(str(component["destination"]))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise PackInstallError(f"Unsafe destination for {component.get('id', 'component')}")
    return root / Path(*relative.parts)


def load_manifest(lock_path: Path) -> dict:
    try:
        manifest = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackInstallError(f"Cannot read the AI pack lock {lock_path}: {exc}") from exc
    if manifest.get("schema_version") != 1 or not manifest.get("components"):
        raise PackInstallError("The AI pack lock is not a schema 1 manifest")
    for component in manifest["components"]:
        digest = str(component.get("sha256", "")).lower()
        if (not str(component.get("url", "")).startswith("https://") or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest) or int(component.get("bytes", 0)) <= 0):
            raise PackInstallError(f"Invalid component in the AI pack lock: {component.get('id')}")
    validate_profiles(manifest)
    return manifest


def resolve_profile(manifest: dict, requested: str) -> dict:
    requested = PROFILE_ALIASES.get(requested, requested)
    if requested == "voice-only":
        profile = voice_only_profile(manifest)
    elif requested == "auto":
        profile = choose_profile(manifest, Hardware.detect(), "auto")
    else:
        profile = next((dict(p) for p in manifest.get("model_profiles", []) if p.get("id") == requested), {})
    if not profile:
        raise PackInstallError(f"Unknown AI pack profile: {requested}")
    return profile


class Progress:
    def __init__(self, total: int, stream=None):
        self.total = max(1, total)
        self.done = 0
        self.stream = stream or sys.stdout
        self._last_percent = -1
        self._last_time = 0.0

    def add(self, count: int, label: str) -> None:
        self.done += count
        percent = min(100, int(self.done * 100 / self.total))
        now = time.monotonic()
        if percent != self._last_percent and (percent - self._last_percent >= 2 or now - self._last_time > 5 or percent == 100):
            self._last_percent = percent
            self._last_time = now
            print(f"AI pack {percent:3d}%  {self.done / 1e6:7.1f} / {self.total / 1e6:.1f} MB  {label}",
                  file=self.stream, flush=True)


def _verified(path: Path, component: dict) -> bool:
    return (path.is_file() and path.stat().st_size == int(component["bytes"])
            and _sha256(path) == str(component["sha256"]).lower())


def _place_verified(source: Path, target: Path, component: dict, *, move: bool) -> bool:
    if not _verified(source, component):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    if move:
        os.replace(source, partial)
    else:
        shutil.copyfile(source, partial)
    if not _verified(partial, component):
        partial.unlink(missing_ok=True)
        return False
    os.replace(partial, target)
    return True


def _download(component: dict, target: Path, progress: Progress, timeout: float) -> None:
    expected = int(component["bytes"])
    partial = target.with_name(target.name + ".partial")
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = partial.stat().st_size if partial.is_file() else 0
    if existing > expected:
        partial.unlink()
        existing = 0
    headers = {"User-Agent": "RTSAI-Setup/1"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(str(component["url"]), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            resumed = existing > 0 and response.status == 206
            if not resumed:
                existing = 0
            progress.add(existing, component["id"])
            with partial.open("ab" if resumed else "wb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
                    progress.add(len(block), component["id"])
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise PackInstallError(f"Download failed for {component['id']}: {exc}") from exc
    if partial.stat().st_size != expected:
        raise PackInstallError(f"Size check failed for {component['id']}: expected {expected}, got {partial.stat().st_size}")
    if _sha256(partial) != str(component["sha256"]).lower():
        partial.unlink()
        raise PackInstallError(f"Security check failed for {component['id']}: SHA-256 does not match")
    os.replace(partial, target)


def install(root: Path, lock_path: Path, profile_id: str, *, archive: Path | None = None,
            from_dir: Path | None = None, timeout: float = 60.0, stream=None) -> dict:
    """Install one profile under root/ai and write the receipt. Returns the receipt."""
    stream = stream or sys.stdout
    manifest = load_manifest(lock_path)
    profile = resolve_profile(manifest, profile_id)
    components = selected_components(manifest, profile)
    pack_root = root / "ai"
    pack_root.mkdir(parents=True, exist_ok=True)
    total = sum(int(component["bytes"]) for component in components)
    free = shutil.disk_usage(pack_root).free
    if free < total + 256 * 1024 * 1024:
        raise PackInstallError(f"The AI pack needs {total / 1e9:.2f} GB plus working space; only {free / 1e9:.2f} GB is free")
    print(f"Installing the {profile.get('label', profile['id'])} pack ({total / 1e6:.0f} MB) into {pack_root}",
          file=stream, flush=True)
    progress = Progress(total, stream)
    archive_file = zipfile.ZipFile(archive) if archive else None
    try:
        for component in components:
            target = _destination(pack_root, component)
            if _verified(target, component):
                progress.add(int(component["bytes"]), f"{component['id']} (already installed)")
                continue
            if archive_file is not None:
                member = str(component["destination"])
                names = {name.replace("\\", "/").removeprefix("./"): name for name in archive_file.namelist()}
                for candidate in (member, f"ai/{member}"):
                    if candidate in names:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        staged = target.with_name(target.name + ".archive")
                        with archive_file.open(names[candidate]) as source, staged.open("wb") as output:
                            shutil.copyfileobj(source, output, 1024 * 1024)
                        placed = _place_verified(staged, target, component, move=True)
                        staged.unlink(missing_ok=True)
                        if placed:
                            break
                if _verified(target, component):
                    progress.add(int(component["bytes"]), f"{component['id']} (from {archive.name})")
                    continue
            if from_dir is not None:
                local = _destination(from_dir, component)
                if _place_verified(local, target, component, move=False):
                    progress.add(int(component["bytes"]), f"{component['id']} (local copy)")
                    continue
            _download(component, target, progress, timeout)
    finally:
        if archive_file is not None:
            archive_file.close()
    receipt_path = pack_root / "pack.json"
    previous: dict = {}
    if receipt_path.is_file():
        try:
            previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    entries = {entry["id"]: entry for entry in previous.get("components", [])
               if previous.get("pack_version") == manifest["pack_version"] and isinstance(entry, dict) and "id" in entry}
    for component in components:
        entries[component["id"]] = {key: component[key] for key in ("id", "sha256", "bytes", "destination")}
    receipt = {
        "schema_version": 1,
        "name": manifest.get("name", "OpenRA AI Local AI Pack"),
        "pack_version": manifest["pack_version"],
        "profile": profile,
        "installed_at": int(time.time()),
        "components": sorted(entries.values(), key=lambda entry: entry["id"]),
    }
    temporary = receipt_path.with_suffix(".json.partial")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, receipt_path)
    print(f"AI pack ready: {profile['id']} ({len(components)} files verified)", file=stream, flush=True)
    return receipt


def status(root: Path, lock_path: Path, profile_id: str) -> dict:
    manifest = load_manifest(lock_path)
    profile = resolve_profile(manifest, profile_id)
    components = selected_components(manifest, profile)
    pack_root = root / "ai"
    present = [component["id"] for component in components
               if (_destination(pack_root, component)).is_file()
               and _destination(pack_root, component).stat().st_size == int(component["bytes"])]
    return {"profile": profile["id"], "installed": len(present) == len(components),
            "present": present, "total_bytes": sum(int(c["bytes"]) for c in components)}


def default_lock(root: Path) -> Path:
    return root / "packaging" / "ai-pack.lock.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rtsai-companion pack")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "status"):
        command = commands.add_parser(name)
        command.add_argument("--profile", default="voice-only",
                             help="voice-only (hosted AI + local voice), recommended (full local AI), lightweight or auto")
        command.add_argument("--root", type=Path, default=Path(sys.executable).resolve().parent,
                             help="companion folder; the pack goes to <root>/ai")
        command.add_argument("--lock", type=Path, help="ai-pack.lock.json (default <root>/packaging/ai-pack.lock.json)")
        if name == "install":
            command.add_argument("--archive", type=Path, help="offline pack zip to use before downloading")
            command.add_argument("--from-dir", type=Path, help="directory laid out like ai/ that already holds the files")
            command.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    lock = (args.lock or default_lock(root)).resolve()
    try:
        if args.command == "status":
            print(json.dumps(status(root, lock, args.profile)))
            return 0
        archive = args.archive.resolve() if args.archive and args.archive.is_file() else None
        if args.archive and archive is None:
            print(f"Offline pack not found: {args.archive}; downloading instead.", flush=True)
        install(root, lock, args.profile, archive=archive,
                from_dir=args.from_dir.resolve() if args.from_dir else None, timeout=args.timeout)
        return 0
    except (PackInstallError, ValueError, zipfile.BadZipFile) as exc:
        print(f"AI pack installation failed: {exc}", file=sys.stderr, flush=True)
        print(f"AI pack installation failed: {exc}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
