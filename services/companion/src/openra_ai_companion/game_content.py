from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import tempfile


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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
        try:
            with source.open("rb") as original, staging.open("wb") as stream:
                shutil.copyfileobj(original, stream)
            if digest(staging) != hashes[name]:
                raise ValueError(f"Source changed while importing {name}; please retry")
            os.link(staging, target)
        finally:
            staging.unlink(missing_ok=True)
    return hashes


def ra2_content_root() -> Path:
    support = os.environ.get("OPENRA_AI_SUPPORT_DIR")
    if not support:
        raise ValueError("Launch OpenRA AI to import game content into its configured library.")
    return Path(support) / "Content/ra2"


def import_owned_ra2() -> dict:
    home = Path.home()
    depots = home / (
        "Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS/"
        "steamapps/content/app_2229850"
    )
    preview = home / "Library/Application Support/OpenRA AI/RA2 Preview/Content/ra2"
    candidates = [(preview, preview), (depots / "depot_2229851", depots / "depot_2229852")]
    for base, language in candidates:
        try:
            content_file(base, "ra2.mix")
            content_file(language, "language.mix")
        except ValueError:
            continue
        hashes = import_content(base, language, ra2_content_root())
        return {"installed": True, "content_sha256": hashes}
    raise ValueError("RA2 game files were not found. Install your owned Steam RA2 base and English content, then retry. No game files are downloaded by this importer.")
