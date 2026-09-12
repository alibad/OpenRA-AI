from __future__ import annotations

import hashlib
import os
import re
import sys
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


def steam_roots() -> list[Path]:
    """Discover registered Steam libraries, including non-system drives."""
    roots = []
    if sys.platform == "win32":
        import winreg
        for hive, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                 (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(hive, key) as entry:
                    roots.append(Path(winreg.QueryValueEx(entry, value)[0]))
            except OSError:
                pass
        roots.append(Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Steam")
    else:
        roots.extend((Path.home() / "Library/Application Support/Steam",
                      Path.home() / ".local/share/Steam"))
    for root in list(roots):
        library_file = root / "steamapps/libraryfolders.vdf"
        if library_file.is_file():
            for value in re.findall(r'"path"\s+"([^"\n]+)"', library_file.read_text(encoding="utf-8")):
                roots.append(Path(value.replace("\\\\", "\\")))
    return list(dict.fromkeys(roots))


def owned_ra2_candidates() -> list[tuple[Path, Path]]:
    home = Path.home()
    depots = home / (
        "Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS/"
        "steamapps/content/app_2229850"
    )
    preview = home / "Library/Application Support/OpenRA AI/RA2 Preview/Content/ra2"
    candidates = [(preview, preview), (depots / "depot_2229851", depots / "depot_2229852")]
    explicit = os.environ.get("OPENRA_AI_RA2_CONTENT_DIR")
    if explicit:
        candidates.insert(0, (Path(explicit), Path(explicit)))
    for root in steam_roots():
        manifest = root / "steamapps/appmanifest_2229850.acf"
        if manifest.is_file():
            match = re.search(r'"installdir"\s+"([^"\n]+)"', manifest.read_text(encoding="utf-8"))
            if match:
                directory = (root / "steamapps/common" / match[1]).resolve()
                if directory.is_relative_to((root / "steamapps/common").resolve()):
                    candidates.append((directory, directory))
        depot = root / "steamapps/content/app_2229850"
        candidates.append((depot / "depot_2229851", depot / "depot_2229852"))
    return candidates


def import_owned_ra2() -> dict:
    destination = ra2_content_root()
    try:
        for name in ("ra2.mix", "language.mix"):
            content_file(destination, name)
        return {"installed": True, "already_installed": True}
    except ValueError:
        pass
    candidates = owned_ra2_candidates()
    for base, language in candidates:
        try:
            content_file(base, "ra2.mix")
            content_file(language, "language.mix")
        except ValueError:
            continue
        hashes = import_content(base, language, ra2_content_root())
        return {"installed": True, "content_sha256": hashes}
    raise ValueError("Owned RA2 content is required. Install Command & Conquer Red Alert 2 and Yuri's Revenge (Steam app 2229850), then choose Red Alert 2 again. All registered Steam libraries are checked automatically. No commercial game files are bundled or downloaded by this importer.")
