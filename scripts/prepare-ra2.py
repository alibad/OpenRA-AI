#!/usr/bin/env python3
"""Prepare RA2 as an integrated OpenRA AI game, without proprietary content."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ra2_source", ROOT / "scripts/build-ra2-preview.py")
SOURCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SOURCE)

FLAG_SIZE = (30, 15)
MODERN_FLAGS = (("china", 192, 128), ("iran", 226, 33), ("turkey", 226, 113))


def combined_replacements(modern: Path) -> str:
    prerequisites = {}
    for country in ("china", "iran", "turkey"):
        actor = None
        source = modern / (country + "-replacements.yaml")
        for line in source.read_text().splitlines():
            if line and not line[0].isspace() and not line.startswith("#"):
                actor = line.removesuffix(":")
            elif line.startswith("\t\tPrerequisites: "):
                items = line.split(": ", 1)[1].split(", ")
                base = [item for item in items if not item.startswith("~!faction.")]
                previous = prerequisites.setdefault(actor, [base, []])
                if previous[0] != base:
                    raise ValueError(f"Inconsistent original prerequisites for {actor}: {previous[0]} vs {base}")
                previous[1].append("~!faction." + country)
    return "\n".join(
        f"{actor}:\n\tBuildable:\n\t\tPrerequisites: {', '.join(base + exclusions)}\n"
        for actor, (base, exclusions) in sorted(prerequisites.items())
    )


def extend_flag_atlas(original: Image.Image, flags: Image.Image) -> tuple[Image.Image, str]:
    """Keep flag pixels inside the native lobby's 30x15 slot.

    ImageWidget draws at the sprite's intrinsic size, not its widget bounds.
    Upstream's 45x21 atlas cells contain padding: stretching our flags to fill
    that cell makes them overlap the country label and the following row.
    """
    width, height = FLAG_SIZE
    required = (max(original.width, len(MODERN_FLAGS) * width), original.height + height)
    atlas = Image.new("RGBA", tuple(1 << (size - 1).bit_length() for size in required))
    atlas.paste(original.convert("RGBA"), (0, 0))
    regions = []
    for i, (country, x, y) in enumerate(MODERN_FLAGS):
        if x + width > flags.width or y + height > flags.height:
            raise ValueError(f"Source atlas is missing the {country} flag")
        flag = flags.crop((x, y, x + width, y + height)).convert("RGBA")
        atlas.paste(flag, (width * i, original.height))
        regions.append(f"\t\t{country}: {width * i}, {original.height}, {width}, {height}\n")
    return atlas, "".join(regions)


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if text.count(old) != 1:
        raise ValueError(f"Expected one integration anchor in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1))


def trim_off_map_fences(text: str) -> str:
    bounds = re.search(r"^Bounds: (\d+),(\d+),(\d+),(\d+)$", text, re.MULTILINE)
    if bounds is None:
        raise ValueError("RA2 map has no rectangular bounds")
    left, top, width, height = map(int, bounds.groups())

    def keep_actor(match: re.Match[str]) -> str:
        block = match.group()
        if not re.match(r"\t[^:\n]+: cafncp\n", block):
            return block
        location = re.search(r"\t\tLocation: (-?\d+),(-?\d+)", block)
        if location is None:
            raise ValueError("Fence has no map location")
        x, y = map(int, location.groups())
        v = x + y
        u = (v - (v & 1)) // 2 - y
        return block if left <= u < left + width and top <= v < top + height else ""

    return re.sub(r"^\t[^\t\n][^\n]*\n(?:\t\t[^\n]*\n)*", keep_actor, text, flags=re.MULTILINE)


def integrate(source: Path, engine: Path, version: str) -> None:
    mod = source / "mods/ra2"
    manifest = mod / "mod.yaml"
    replace_once(manifest, "~^maps/ra2/", "~^SupportDir|maps/ra2/")
    replace_once(manifest, "ra2|chrome/native-mainmenu.yaml", "common|chrome/mainmenu.yaml")
    replace_once(manifest, "ra2|chrome/native-settings.yaml", "common|chrome/settings.yaml\n\tcommon|chrome/settings-ai.yaml")
    replace_once(manifest, "Rules:\n", "Rules:\n\tra2|rules/companion.yaml\n")
    replace_once(manifest, "PackageFormats:", "Include: experiences.yaml\n\nPackageFormats:")
    replace_once(manifest, "ChromeLayout:\n", "ChromeLayout:\n\tra2|chrome/experience-composer.yaml\n\tra2|chrome/experience-review.yaml\n\tcommon|chrome/earth-mission-studio.yaml\n")
    for name in ("experience-composer.yaml", "experience-review.yaml"):
        shutil.copy2(engine / "mods/ra/chrome" / name, mod / "chrome" / name)
    (mod / "rules/companion.yaml").write_text("^BaseWorld:\n\tCompanionBridge:\n")
    ra_hud = (engine / "mods/ra/chrome/ingame-player.yaml").read_text()
    start = ra_hud.index("\t\tBackground@AI_COMPANION_STRIP:")
    end = ra_hud.index("\t\tLogicKeyListener@PLAYER_KEYHANDLER:", start)
    replace_once(mod / "chrome/ingame-player.yaml", "\t\tContainer@CHAT_ROOT:\n",
                 "\t\tContainer@CHAT_ROOT:\n" + ra_hud[start:end])
    ai = (mod / "rules/ai.yaml").read_text().removeprefix("Player:\n")
    profiles = []
    for profile in ("normal", "medium", "rush", "turtle", "naval"):
        rules = ai.replace("@testai", "@" + profile).replace("@test", "@" + profile)
        rules = rules.replace("enable-test-ai", f"enable-{profile}-ai")
        rules = rules.replace("Type: test", f"Type: {profile}").replace("Bots: test", f"Bots: {profile}")
        rules = rules.replace("Name: Test AI", f"Name: ra2-bot-{profile}")
        for module in ("HarvesterBotModule", "BuildingRepairBotModule"):
            rules = rules.replace(f"\t{module}:\n", f"\t{module}@{profile}:\n")
        if profile == "rush":
            rules = rules.replace("SquadSize: 5", "SquadSize: 3")
        elif profile == "turtle":
            rules = rules.replace("SquadSize: 5", "SquadSize: 12").replace("gapill: 10", "gapill: 25").replace("nalasr: 10", "nalasr: 25")
        elif profile == "naval":
            rules = rules.replace("dest: 20", "dest: 60").replace("sub: 20", "sub: 60")
        profiles.append(rules)
    (mod / "rules/ai.yaml").write_text("Player:\n" + "".join(profiles))
    modern = ROOT / "apps/installer/ra2/modern-factions"
    shutil.copytree(modern, mod / "modern-factions")
    (mod / "modern-factions/shared-replacements.yaml").write_text(combined_replacements(modern))
    shutil.copy2(engine / "mods/ra/uibits/experience-previews/unit-composition-doctrine-ai.png",
                 mod / "modern-factions/previews/combined-arms-ai.png")
    # Reuse original bilingual faction performances, not proprietary RA1 audio.
    faction_audio = mod / "modern-factions/audio"
    faction_audio.mkdir()
    for pattern in ("tr-*.wav", "rcn-*.wav", "china-role-*.wav", "china-network-*.wav", "iran-*.wav", "shadow-*.wav"):
        for voice in (engine / "mods/ra/bits").glob(pattern):
            shutil.copy2(voice, faction_audio / voice.name)
    shutil.copy2(modern / "experiences.yaml", mod / "experiences.yaml")
    # Upstream carrier declares RevealsShroud twice. It becomes an ambiguous
    # merge when the Turkey pack adds its faction exclusion to that actor.
    replace_once(mod / "rules/allied-naval.yaml",
                 "\tMobile:\n\t\tTurnSpeed: 4\n\t\tSpeed: 60\n\tRevealsShroud:\n\t\tRange: 7c0\n\tAttackFrontal:",
                 "\tMobile:\n\t\tTurnSpeed: 4\n\t\tSpeed: 60\n\tAttackFrontal:")
    # Model sequences are manifest-level data. Unused models are harmless when
    # a pack is off; gameplay rules/weapons/sprite sequences remain conditional.
    replace_once(manifest, "ModelSequences:\n", "ModelSequences:\n\tra2|modern-factions/voxels.yaml\n\tra2|modern-factions/turkey-voxels.yaml\n\tra2|modern-factions/china-voxels.yaml\n\tra2|modern-factions/iran-voxels.yaml\n")
    replace_once(manifest, "FluentMessages:\n", "FluentMessages:\n\tra2|modern-factions/messages.ftl\n\tra2|modern-factions/turkey-messages.ftl\n\tra2|modern-factions/china-messages.ftl\n\tra2|modern-factions/iran-messages.ftl\n")
    metrics = mod / "metrics.yaml"
    metrics.write_text(metrics.read_text().replace("Metrics:\n", "Metrics:\n\tFactionSuffix-china: allies\n\tFactionSuffix-turkey: allies\n\tFactionSuffix-iran: soviets\n", 1))
    # Extend the upstream UI atlas at build time, reusing our existing country
    # flags. Do not ship a replacement that could lose any stock UI regions.
    buttons = mod / "uibits/buttons.png"
    with Image.open(buttons) as original, Image.open(engine / "mods/ra/uibits/glyphs-redsea.png") as flags:
        atlas, regions = extend_flag_atlas(original, flags)
        atlas.save(buttons)
    replace_once(mod / "chrome.yaml", "flags:\n\tImage: buttons.png\n\tRegions:\n",
                 "flags:\n\tImage: buttons.png\n\tRegions:\n" + regions)
    (mod / "languages/native-preview.ftl").write_text(
        "ra2-preview-window-title = OpenRA AI — Red Alert 2\n"
        "ra2-preview-note = Red Alert 2 with the shared AI assistant. Original campaigns and Yuri’s Revenge are not included.\n"
        + "".join(f"ra2-bot-{profile} = RA2 {profile.title()} AI\n" for profile in ("normal", "medium", "rush", "turtle", "naval"))
    )
    for path in (mod / "maps").glob("*/map.yaml"):
        path.write_text(trim_off_map_fences(path.read_text()))
    for path in mod.rglob("*.yaml"):
        path.write_text(path.read_text().replace("{DEV_VERSION}", version))


def prepare(resources: Path, binaries: Path, version: str, allow_engine_changes: bool = False, runtime: str = "osx-arm64") -> Path:
    engine = ROOT / "engine/openra"
    manifest = json.loads((SOURCE.CONFIG / "upstream.json").read_text())
    actual = subprocess.check_output(["git", "-C", str(engine), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(engine), "status", "--porcelain"], text=True).strip()
    if not allow_engine_changes and (actual != manifest["engine_commit"] or dirty):
        raise ValueError("RA2 packaging requires the clean pinned engine. Use --allow-engine-changes only for development validation.")
    if (resources / "mods/ra2").exists():
        raise ValueError("Refusing to replace an existing RA2 payload; use an empty package stage.")
    cache = ROOT / "artifacts/ra2-native"
    cache.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="integrated-", dir=cache))
    source = SOURCE.extract_source(SOURCE.download_source(manifest, cache), workspace, manifest["commit"])
    SOURCE.run("git", "apply", "--check", SOURCE.CONFIG / "compatibility.patch", cwd=source)
    SOURCE.run("git", "apply", SOURCE.CONFIG / "compatibility.patch", cwd=source)
    integrate(source, engine, version)
    SOURCE.run("dotnet", "build", source / "OpenRA.Mods.RA2/OpenRA.Mods.RA2.csproj", "-c", "Release",
               f"-p:EngineRootPath={engine}", f"-p:OutputPath={workspace / 'bin'}", f"-p:TargetPlatform={runtime}", "--nologo")
    shutil.copytree(source / "mods/ra2", resources / "mods/ra2")
    shutil.copy2(engine / "mods/ts/uibits/glyphs.png", resources / "mods/common/native-ra2-glyphs.png")
    for suffix in (".dll", ".deps.json"):
        shutil.copy2(workspace / "bin" / ("OpenRA.Mods.RA2" + suffix), binaries)
    evidence = {**manifest, "engine_commit": actual, "engine_dirty": bool(dirty), "version": version, "runtime": runtime,
                "ai_assistant": True, "game_selection": ["ra", "ra2"], "proprietary_content_bundled": False}
    (resources / "RA2-BUILD.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if any((resources / "mods/ra2").rglob("*.mix")):
        raise ValueError("Proprietary RA2 data must not be packaged")
    return workspace


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--binaries", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--allow-engine-changes", action="store_true")
    parser.add_argument("--runtime", choices=("osx-arm64", "osx-x64"), default="osx-arm64")
    args = parser.parse_args()
    print(prepare(args.resources, args.binaries, args.version, args.allow_engine_changes, args.runtime))
