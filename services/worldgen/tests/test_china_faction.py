from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
import subprocess
import wave
import zipfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
ENGINE = Path(os.environ.get("OPENRA_ENGINE_ROOT", ROOT / "engine" / "openra"))
RA = ENGINE / "mods" / "ra"
BITS = RA / "bits"
FRAMES = ROOT / "generated" / "china-faction-sprites"
RULES = (RA / "rules" / "china.yaml").read_text(encoding="utf-8")
SEQUENCES = (RA / "sequences" / "china.yaml").read_text(encoding="utf-8")
WORLD = (RA / "rules" / "world.yaml").read_text(encoding="utf-8")
MISSION_SOURCE = ROOT / "missions" / "china-faction" / "haitan-network"
MISSION = ROOT / "generated" / "missions" / "haitan-network-2026.oramap"
UTILITY = ENGINE / "bin" / ("OpenRA.Utility.exe" if os.name == "nt" else "OpenRA.Utility")


def shp_frames(name: str) -> int:
    with (BITS / f"{name}.shp").open("rb") as stream:
        return struct.unpack("<H", stream.read(2))[0]


def digest(path: Path) -> str:
    with Image.open(path) as frame:
        return hashlib.sha256(frame.convert("RGBA").tobytes()).hexdigest()


def alpha_dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as frame:
        box = frame.convert("RGBA").getchannel("A").getbbox()
    assert box is not None
    return box[2] - box[0], box[3] - box[1]


def test_faction_selector_registers_china_and_hidpi_flag() -> None:
    chrome = (RA / "chrome.yaml").read_text(encoding="utf-8")
    assert "Faction@china:" in WORLD
    assert "Name: faction-china" in WORLD
    assert "InternalName: china" in WORLD
    match = re.search(r"china: (\d+), (\d+), 30, 15", chrome)
    assert match is not None
    selector_x, selector_y = (int(value) for value in match.groups())
    assert "sidebar-china:" in chrome
    assert "Inherits: sidebar-allies" in chrome.split("sidebar-china:", 1)[1].split("\n\n", 1)[0]
    assert "command-button-china-highlighted-disabled:" in chrome
    for scale, suffix in ((1, ""), (2, "-2x"), (3, "-3x")):
        with Image.open(RA / "uibits" / f"glyphs-redsea{suffix}.png") as atlas:
            flag = atlas.crop(
                (
                    selector_x * scale,
                    selector_y * scale,
                    (selector_x + 30) * scale,
                    (selector_y + 15) * scale,
                )
            ).convert("RGB")
            colors = set(flag.get_flattened_data())
        assert (222, 41, 16) in colors
        assert (255, 222, 0) in colors


def test_china_inherits_complete_economy_repair_and_production_chain() -> None:
    contracts = {
        "FACT": ("structures.allies", "structures.china"),
        "WEAP": ("vehicles.china",),
        "HPAD": ("aircraft.china",),
        "TENT": ("infantry.china",),
        "SYRD": ("ships.china",),
    }
    for actor, prerequisites in contracts.items():
        block = RULES.split(f"\n{actor}:\n", 1)[1].split("\n\n", 1)[0]
        assert "Factions: china" in block
        if actor == "FACT":
            assert "ProvidesPrerequisite@chinaalliedtree:" in block
        for prerequisite in prerequisites:
            assert f"Prerequisite: {prerequisite}" in block
    for native_actor in ("FACT", "PROC", "HARV", "FIX", "DOME", "ATEK", "TENT", "WEAP", "HPAD", "SYRD"):
        assert re.search(rf"(?m)^{native_actor}:", "\n".join(path.read_text(encoding="utf-8") for path in (RA / "rules").glob("*.yaml")))


def test_required_infantry_and_fictional_hero_use_native_traits() -> None:
    for actor in ("CNRIFLE", "CNNETWORK", "CNPORTABLE", "REDSPEAR"):
        block = RULES.split(f"\n{actor}:\n", 1)[1].split("\n\n", 1)[0]
        assert "Inherits: ^Soldier" in block
        assert "WithInfantryBody:" in block
        assert "RenderSprites:" in block
    assert "GrantConditionOnDeploy:" in RULES.split("\nCNNETWORK:\n", 1)[1].split("\nCNPORTABLE:\n", 1)[0]
    assert "JamsMissiles:" in RULES
    portable = RULES.split("\nCNPORTABLE:\n", 1)[1].split("\nREDSPEAR:\n", 1)[0]
    assert "Weapon: ChinaPortableAT" in portable and "Weapon: ChinaPortableAA" in portable
    hero = RULES.split("\nREDSPEAR:\n", 1)[1].split("\nCNQILIN:\n", 1)[0]
    assert "BuildLimit: 1" in hero
    assert "ProximityExternalCondition@COMMANDNETWORK:" in hero
    assert "Demolition:" not in hero and "C4" not in hero and "Tanya" not in hero


def test_every_infantry_package_matches_e1_frame_contract() -> None:
    families = {
        "stand": lambda facing: facing,
        "stand2": lambda facing: 8 + facing,
        "run": lambda facing: 16 + facing * 6,
        "fire": lambda facing: 64 + facing * 8,
        "liedown": lambda facing: 128 + facing * 2,
        "prone": lambda facing: 144 + facing * 4,
        "standup": lambda facing: 176 + facing * 2,
        "prone-fire": lambda facing: 192 + facing * 8,
    }
    for actor in ("cnrifle", "cnnetwork", "cnportable", "redspear"):
        assert shp_frames(actor) == 378
        assert len(list((FRAMES / actor).glob(f"{actor}-*.png"))) == 378
        for family, index_for_facing in families.items():
            hashes = {
                digest(FRAMES / actor / f"{actor}-{index_for_facing(facing):04d}.png")
                for facing in range(8)
            }
            assert len(hashes) == 8, f"{actor} {family} must have eight authored facings"
        for start, length in ((288, 8), (296, 8), (304, 8), (312, 12), (324, 18)):
            hashes = {digest(FRAMES / actor / f"{actor}-{index:04d}.png") for index in range(start, start + length)}
            assert len(hashes) >= min(6, length), f"{actor} death family at {start}"
    assert "Start: 377" in SEQUENCES
    assert "prone-shoot:" in SEQUENCES and "Start: 192" in SEQUENCES


def test_ground_vehicles_use_native_layering_and_directional_wrecks() -> None:
    for actor in ("cnqilin", "cnlynx", "cnzbd", "cnmantis"):
        assert shp_frames(actor) == 64
        assert shp_frames(f"{actor}husk") == 64
        for start in (0, 32):
            hashes = {digest(FRAMES / actor / f"{actor}-{index:04d}.png") for index in range(start, start + 32)}
            assert len(hashes) == 32
        sequence = SEQUENCES.split(f"\n{actor}:\n", 1)[1].split("\n\n", 1)[0]
        assert "UseClassicFacings: True" in sequence
        assert "Start: 32" in sequence
        assert f"Actor: {actor.upper()}.Husk" in RULES
    assert shp_frames("cnphl") == 64 and shp_frames("cnphlhusk") == 32
    renderer = (ROOT / "scripts" / "china_directional_assets.py").read_text(encoding="utf-8")
    assert ".rotate(" not in renderer
    assert "classic=True" in renderer


def test_planes_helicopter_and_ships_match_native_facing_contracts() -> None:
    for actor in ("cnskyspear", "cncloud"):
        assert shp_frames(actor) == 16
        assert len({digest(FRAMES / actor / f"{actor}-{i:04d}.png") for i in range(16)}) == 16
        block = SEQUENCES.split(f"\n{actor}:\n", 1)[1].split("\n\n", 1)[0]
        assert "Facings: 16" in block and "InterpolatedFacings: 64" in block
    assert shp_frames("cncrane") == 32
    assert len({digest(FRAMES / "cncrane" / f"cncrane-{i:04d}.png") for i in range(32)}) == 32
    assert shp_frames("cncranerotor") == 12
    for actor in ("cnluyang", "cnhaiwang", "cnhaiying", "cnkunlun"):
        assert shp_frames(actor) == (144 if actor == "cnkunlun" else 16)
        assert shp_frames(f"{actor}turret") == 32
        assert shp_frames(f"{actor}sink") == 64
        block = RULES.split(f"\n{actor.upper()}:\n", 1)[1].split("\n\n", 1)[0]
        for trait in ("Inherits: ^Ship", "WithSpriteTurret:", "LeavesTrails@WAKE:", "SpawnActorOnDeath:"):
            assert trait in block
    assert shp_frames("cnkunlun") == 144
    assert "WithLandingCraftAnimation:" in RULES.split("\nCNKUNLUN:\n", 1)[1].split("\nCNJIAOLONG:\n", 1)[0]
    assert shp_frames("cnjiaolong") == 16 and shp_frames("cnjiaolongsink") == 64
    submarine = RULES.split("\nCNJIAOLONG:\n", 1)[1].split("\nCNQILIN.Husk:\n", 1)[0]
    assert "Inherits: ^Submarine" in submarine and "Weapon: ChinaTorpedo" in submarine
    assert shp_frames("china-wake") == 8


def test_china_defenses_cover_ground_air_and_information_control() -> None:
    contracts = {
        "CNBASTION": ("^AutoTargetGround", "Weapon: ChinaBastionGun"),
        "CNSKYSHIELD": ("^AutoTargetAir", "Weapon: ChinaSkyShieldAA"),
        "CNSPECTRUM": ("JamsMissiles:", "CreatesShroud:"),
    }
    for actor, traits in contracts.items():
        block = RULES.split(f"\n{actor}:\n", 1)[1].split("\n\n", 1)[0]
        assert "Inherits: ^Defense" in block and "~structures.china" in block
        assert all(trait in block for trait in traits)
        name = actor.lower()
        assert shp_frames(name) == 12 and shp_frames(f"{name}top") in {32, 64}


def test_unit_scale_and_cameo_contracts() -> None:
    limits = {
        "cnqilin": (44, 44), "cnlynx": (32, 32), "cnzbd": (42, 42), "cnphl": (44, 44),
        "cnskyspear": (56, 56), "cncloud": (48, 48), "cncrane": (56, 56),
        "cnmantis": (46, 46), "cnluyang": (64, 64), "cnhaiwang": (72, 72),
        "cnhaiying": (52, 52), "cnkunlun": (76, 76), "cnjiaolong": (60, 60),
    }
    for actor, canvas in limits.items():
        with Image.open(FRAMES / actor / f"{actor}-0000.png") as image:
            assert image.size == canvas
        width, height = alpha_dimensions(FRAMES / actor / f"{actor}-0000.png")
        assert width > 6 and height > 6
    for actor in ("cnrifle", "cnnetwork", "cnportable", "redspear", "cnqilin", "cnlynx", "cnzbd", "cnphl",
                  "cnmantis", "cnskyspear", "cncloud", "cncrane", "cnluyang", "cnhaiwang",
                  "cnhaiying", "cnkunlun", "cnjiaolong", "cnbastion", "cnskyshield", "cnspectrum"):
        icon = f"{actor}icon"
        assert shp_frames(icon) == 1
        with Image.open(FRAMES / icon / f"{icon}-0000.png") as image:
            assert image.size == (64, 48) and image.mode == "P"
            assert 0 not in image.tobytes()


def test_native_ammo_rearm_transport_veterancy_and_projectile_systems() -> None:
    for trait in ("AmmoPool@AAM:", "Rearmable:", "Cargo:", "^GainsExperience", "AttackAircraft:"):
        assert trait in RULES
    weapons = (RA / "weapons" / "china.yaml").read_text(encoding="utf-8")
    assert "Projectile: Missile" in weapons
    assert "Image: china_missile" in weapons
    assert "Image: china_drone_projectile" in weapons
    assert "Warhead@" in weapons


def test_ai_has_complete_combined_land_air_naval_roster() -> None:
    normal_ai = RULES.split("\n\tUnitBuilderBotModule@normal:\n", 1)[1].split("\n\tUnitBuilderBotModule@turtle:\n", 1)[0]
    for actor in ("cnrifle", "cnportable", "cnnetwork", "redspear", "cnlynx", "cnzbd", "cnqilin", "cnphl",
                  "cncloud", "cncrane", "cnskyspear", "cnmantis", "cnluyang", "cnhaiwang",
                  "cnhaiying", "cnkunlun", "cnjiaolong"):
        assert actor in normal_ai
    assert "TechTypes: mslo, dome, atek, stek, fix, afld, hpad" in RULES
    assert RULES.count("AirUnitsTypes:") >= 5
    assert RULES.count("NavalUnitsTypes:") >= 5
    assert RULES.count("DefenseTypes:") >= 6
    for actor in ("cnbastion", "cnskyshield", "cnspectrum"):
        assert RULES.count(actor) >= 6
    assert "NavalProductionTypes: spen, syrd" in (RA / "rules" / "ai.yaml").read_text(encoding="utf-8")


def test_audio_is_original_pcm_and_generic_bilingual_voice_is_disclosed() -> None:
    audio_paths = sorted(BITS.glob("china-*.wav")) + sorted(BITS.glob("rcn-*.wav"))
    assert len(audio_paths) >= 51
    for path in audio_paths:
        with wave.open(str(path), "rb") as audio:
            assert audio.getnchannels() == 1 and audio.getsampwidth() == 2 and audio.getframerate() == 44_100
            frames = audio.readframes(audio.getnframes())
        samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
        peak = max(abs(value) for value in samples)
        assert peak > 100
        assert sum(abs(value) >= 32767 for value in samples) == 0
        assert 20 * math.log10(peak / 32768) <= -1.5
    provenance = json.loads((ROOT / "assets" / "china-faction" / "voice-provenance.json").read_text(encoding="utf-8"))
    assert {"zh-CN", "en-US"}.issubset({line["language"] for line in provenance["lines"]})
    assert all(line["synthetic_voice_disclosed"] and not line["real_person_imitation"] for line in provenance["lines"])


def test_haitan_mission_is_deterministic_fictional_and_water_gated() -> None:
    required = {"map.yaml", "map.bin", "map.png", "rules.yaml", "map.ftl", "haitan-network.lua", "china-mission-manifest.json"}
    with zipfile.ZipFile(MISSION) as archive:
        assert required.issubset(archive.namelist())
        assert all(info.date_time == (2026, 8, 12, 0, 0, 0) for info in archive.infolist())
        map_yaml = archive.read("map.yaml").decode("utf-8")
        script = archive.read("haitan-network.lua").decode("utf-8")
        manifest = json.loads(archive.read("china-mission-manifest.json"))
    assert "Visibility: MissionSelector" in map_yaml and "Faction: china" in map_yaml
    assert "AmphibiousGate" in map_yaml and "EastBeach" in map_yaml
    assert "PassedSeaGate[actor]" in script and "RegisterLanding" in script
    assert all(term in script for term in ("SendGroundWave", "SendAirWave", "SendNavalWave", "EstablishNetwork"))
    assert manifest["fictional"] and not manifest["real_persons"]
    assert manifest["terrain"]["tracked_reachable_spawns"] == "2/2"


def test_research_records_dated_authoritative_sources_and_translation_boundary() -> None:
    research = (ROOT / "docs" / "china-faction-research.md").read_text(encoding="utf-8")
    assert research.count("2024-") + research.count("2025-") + research.count("2026-") >= 9
    assert "eng.mod.gov.cn" in research and "eng.chinamil.com.cn" in research and "media.defense.gov" in research
    assert "does not reproduce a real attack" in research and "fictional" in research.lower()


def test_resolved_rules_and_mission_pass_engine_utility() -> None:
    environment = os.environ.copy()
    environment["ENGINE_DIR"] = ".."
    environment["DOTNET_ROLL_FORWARD"] = "Major"
    result = subprocess.run(
        [str(UTILITY), "ra", "--resolved-rules", "CNQILIN", str(MISSION)],
        cwd=ENGINE, env=environment, text=True, capture_output=True, check=True,
    )
    assert "Weapon: ChinaQilin125mm" in result.stdout
    assert "VoiceSet: ChinaVehicleVoice" in result.stdout
    factory = subprocess.run(
        [str(UTILITY), "ra", "--resolved-rules", "FACT"],
        cwd=ENGINE, env=environment, text=True, capture_output=True, check=True,
    )
    assert "ProvidesPrerequisite@chinaalliedtree:" in factory.stdout
    assert "Prerequisite: structures.allies" in factory.stdout
