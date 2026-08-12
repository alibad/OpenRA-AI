from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import zipfile

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from iran_directional_assets import render_directional_asset, render_infantry

BUILD_SPEC = importlib.util.spec_from_file_location(
    "build_iran_sprites", ROOT / "scripts" / "build-iran-sprites.py"
)
assert BUILD_SPEC and BUILD_SPEC.loader
BUILD_MODULE = importlib.util.module_from_spec(BUILD_SPEC)
BUILD_SPEC.loader.exec_module(BUILD_MODULE)
quantize = BUILD_MODULE.quantize


def digest(image) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


def remap_share(frames) -> float:
    opaque = 0
    remap = 0
    for frame in frames:
        values = frame.tobytes()
        opaque += sum(value != 0 for value in values)
        remap += sum(80 <= value <= 95 for value in values)
    return remap / opaque


@pytest.mark.parametrize("role", ["basij", "atgm", "controller", "shadow"])
def test_infantry_has_complete_authored_facing_contract(role: str) -> None:
    frames = render_infantry(role)
    assert len(frames) == 713

    # Every facing-sensitive animation is stored facing-major.  Testing the
    # first phase from each facing catches a flat or duplicated facing ring.
    directional = {
        "stand": (0, 1),
        "stand2": (8, 1),
        "run": (16, 6),
        "shoot": (64, 8),
        "prone-stand": (128, 1),
        "prone-run": (136, 4),
        "liedown": (168, 2),
        "standup": (184, 2),
        "prone-shoot": (200, 8),
        "die1": (280, 8),
        "die2": (344, 8),
        "die3": (408, 8),
        "die4": (472, 12),
        "die5": (568, 18),
    }
    for sequence, (start, length) in directional.items():
        facing_frames = [frames[start + facing * length] for facing in range(8)]
        assert len({digest(frame) for frame in facing_frames}) == 8, sequence
        assert all(frame.getchannel("A").getbbox() for frame in facing_frames), sequence


@pytest.mark.parametrize("role", ["basij", "atgm", "controller", "shadow"])
def test_infantry_has_native_scale_and_explicit_player_color(role: str) -> None:
    palette = Image.new("P", (1, 1))
    palette.putpalette([channel for value in range(256) for channel in (value, value, value)])
    frames = render_infantry(role)
    indexed = [quantize(frame, palette) for frame in frames[:128]]
    assert remap_share(indexed) >= (0.22 if role == "shadow" else 0.38)

    # The old Iran figures averaged only ~34 px of bounding-box area compared
    # with ~200 px for native E1/E3/E7. Keep the live silhouette substantial.
    areas = []
    for frame in frames[:128]:
        bbox = frame.getchannel("A").getbbox()
        assert bbox
        areas.append((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    assert sum(areas) / len(areas) >= 90

    if role == "shadow":
        for frame in frames[:8]:
            bbox = frame.getchannel("A").getbbox()
            assert bbox
            assert bbox[3] - bbox[1] > bbox[2] - bbox[0]


@pytest.mark.parametrize(
    ("name", "size", "facings", "frame_count"),
    [
        ("irkarr", 40, 32, 64),
        ("irraad", 40, 32, 64),
        ("irfajr", 40, 32, 96),
        ("ircoast", 40, 32, 64),
        ("irazar", 56, 16, 16),
        ("irtoufan", 56, 32, 32),
        ("irmohajer", 44, 16, 16),
        ("irloiter", 40, 16, 32),
        ("irpey", 44, 16, 48),
        ("irghadir", 44, 16, 16),
    ],
)
def test_directional_models_have_unique_authored_frames(
    name: str, size: int, facings: int, frame_count: int
) -> None:
    frames = render_directional_asset(name, size, facings)
    assert len(frames) == frame_count
    assert len({digest(frame) for frame in frames}) == frame_count
    assert all(frame.size == (size, size) for frame in frames)
    assert all(frame.getchannel("A").getbbox() for frame in frames)


@pytest.mark.parametrize(
    ("name", "size", "facings"),
    [
        ("irkarr", 40, 32), ("irraad", 40, 32), ("irfajr", 40, 32),
        ("ircoast", 40, 32), ("irazar", 56, 16), ("irtoufan", 56, 32),
        ("irmohajer", 44, 16), ("irloiter", 40, 16),
        ("irpey", 44, 16), ("irghadir", 44, 16),
    ],
)
def test_every_directional_unit_has_explicit_player_color(name: str, size: int, facings: int) -> None:
    palette = Image.new("P", (1, 1))
    palette.putpalette([channel for value in range(256) for channel in (value, value, value)])
    frames = render_directional_asset(name, size, facings)
    indexed = [quantize(frame, palette) for frame in frames]
    assert remap_share(indexed) >= 0.30


def test_generated_packages_match_declared_frame_counts() -> None:
    root = ROOT / "generated" / "iran-sprites"
    if not root.exists():
        pytest.skip("run scripts/build-iran-assets.ps1 to audit generated packages")
    expected = {
        "irbas": 713, "iratgm": 713, "irdc": 713, "shadowone": 713,
        "irkarr": 64, "irraad": 64, "irfajr": 96, "ircoast": 64,
        "irazar": 16, "irtoufan": 32, "irmohajer": 16, "irloiter": 32,
        "irpey": 48, "irghadir": 16,
        "irkarrhusk": 64, "irraadhusk": 64, "irfajrhusk": 64, "ircoasthusk": 64,
        "irazarhusk": 16, "irtoufanhusk": 32, "irmohajerhusk": 16,
        "irpeysink": 128, "irghadirsink": 128, "irtoufanrotor": 12,
        "irmuzzle": 48, "irimpact": 10, "irsabotage": 12, "ircloak": 8,
        "irwake": 6, "irmissile": 32,
    }
    for name, count in expected.items():
        frames = sorted((root / name).glob(f"{name}-[0-9][0-9][0-9][0-9].png"))
        assert len(frames) == count, name
        assert (ROOT / "engine" / "openra" / "mods" / "ra" / "bits" / f"{name}.shp").is_file(), name


def test_faction_selector_and_skirmish_package_are_installed() -> None:
    assert (ROOT / "engine" / "openra" / "mods" / "ra" / "uibits" / "glyphs-redsea.png").is_file()
    assert (ROOT / "engine" / "openra" / "mods" / "ra" / "maps" / "iran-doctrine-range.oramap").is_file()


def test_doctrine_range_cannot_end_during_live_fire_sequence() -> None:
    path = ROOT / "engine" / "openra" / "mods" / "ra" / "maps" / "iran-doctrine-range.oramap"
    with zipfile.ZipFile(path) as package:
        rules = package.read("rules.yaml").decode("utf-8")
    assert "ShortGameCheckboxEnabled: False" in rules
    assert "ShortGameCheckboxLocked: True" in rules


def actor_module(text: str, module: str, personality: str) -> str:
    match = re.search(
        rf"^\t{re.escape(module)}@{personality}:\n(?P<body>(?:\t\t.*\n|\t\t.*$)+)",
        text,
        re.MULTILINE,
    )
    assert match, f"{module}@{personality}"
    return match.group("body")


def test_every_standard_bot_has_construction_and_mixed_force_contracts() -> None:
    text = (ROOT / "engine" / "openra" / "mods" / "ra" / "rules" / "iran.yaml").read_text(
        encoding="utf-8"
    )
    personalities = ("beginner", "easy", "medium", "rush", "normal", "turtle", "naval")
    domains = (
        {"irbas", "iratgm", "irdc", "shadowone"},
        {"irkarr", "irraad", "irfajr", "ircoast"},
        {"irazar", "irtoufan", "irmohajer", "irloiter"},
        {"irpey", "irghadir"},
    )
    for personality in personalities:
        base = actor_module(text, "BaseBuilderBotModule", personality)
        assert "ProductionTypes:" in base
        assert all(kind in base for kind in ("barr", "weap", "afld", "spen"))
        assert all(kind in base for kind in ("dome", "fix"))

        units = actor_module(text, "UnitBuilderBotModule", personality)
        configured = {
            name
            for name in set().union(*domains)
            if re.search(rf"^\t\t\t{re.escape(name)}:\s+\d+", units, re.MULTILINE)
        }
        assert all(configured & domain for domain in domains), personality

        squads = actor_module(text, "SquadManagerBotModule", personality)
        assert all(name in squads for name in ("irpey", "irghadir", "irazar", "irtoufan", "irmohajer", "irloiter"))


def test_native_progression_and_build_limit_contracts() -> None:
    text = (ROOT / "engine" / "openra" / "mods" / "ra" / "rules" / "iran.yaml").read_text(
        encoding="utf-8"
    )
    for factory, prerequisite in (
        ("FACT", "structures.iran"),
        ("BARR", "infantry.iran"),
        ("WEAP", "vehicles.iran"),
        ("AFLD", "aircraft.iran"),
        ("SPEN", "ships.iran"),
    ):
        assert re.search(
            rf"^{factory}:.*?Prerequisite: {re.escape(prerequisite)}$",
            text,
            re.MULTILINE | re.DOTALL,
        )
    shadow = re.search(r"^SHADOWONE:.*?(?=^[A-Z0-9.]+:)", text, re.MULTILINE | re.DOTALL)
    assert shadow
    assert "BuildLimit: 1" in shadow.group(0)
    assert "CloakedAlpha: 0.72" in shadow.group(0)
    assert "UncloakOn: Attack, Unload, Infiltrate, Demolish, Move" in shadow.group(0)
    assert "IranSabotageCharge" in shadow.group(0)


def test_generated_audio_and_voice_provenance_are_complete() -> None:
    bits = ROOT / "engine" / "openra" / "mods" / "ra" / "bits"
    sound_manifest = ROOT / "assets" / "iran-faction" / "sound-provenance.json"
    voice_manifest = ROOT / "assets" / "iran-faction" / "voice-provenance.json"
    sounds = json.loads(sound_manifest.read_text(encoding="utf-8"))["files"]
    voices = json.loads(voice_manifest.read_text(encoding="utf-8"))["lines"]
    assert len(sounds) == 20
    assert len(voices) == 52
    assert all((bits / item["file"]).is_file() for item in sounds)
    assert all((bits / item["filename"]).is_file() for item in voices)
    assert len({hashlib.sha256((bits / item["file"]).read_bytes()).hexdigest() for item in sounds}) == 20
    assert len({hashlib.sha256((bits / item["filename"]).read_bytes()).hexdigest() for item in voices}) == 52
