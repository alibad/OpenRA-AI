from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import wave


ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "engine" / "openra"
BITS = ENGINE / "mods" / "ra" / "bits"
RULES = (ENGINE / "mods" / "ra" / "rules" / "red-sea.yaml").read_text(encoding="utf-8")
SEQUENCES = (ENGINE / "mods" / "ra" / "sequences" / "red-sea.yaml").read_text(encoding="utf-8")


def load_renderer():
    source = ROOT / "scripts" / "red_sea_directional_vehicle.py"
    spec = importlib.util.spec_from_file_location("red_sea_directional_vehicle", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(image) -> str:
    return hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()


def dimensions(image) -> tuple[int, int]:
    box = image.convert("RGBA").getchannel("A").getbbox()
    assert box is not None
    return box[2] - box[0], box[3] - box[1]


def test_airframes_have_native_facing_contracts_and_stable_scale() -> None:
    renderer = load_renderer()
    samad = renderer.render_samad_frames()
    fighter = renderer.render_f15sa_frames()
    helicopter = renderer.render_ah64sa_frames()

    assert len(samad) == 32  # 16 level + 16 pitched terminal-dive facings
    assert len(fighter) == 16  # native plane contract, interpolated to 64 in YAML
    assert len(helicopter) == 32  # native classic helicopter contract
    assert len({digest(frame) for frame in samad[:16]}) == 16
    assert len({digest(frame) for frame in samad[16:]}) == 16
    assert all(digest(samad[index]) != digest(samad[index + 16]) for index in range(16))
    assert len({digest(frame) for frame in fighter}) == 16
    assert len({digest(frame) for frame in helicopter}) == 32

    samad_sizes = [dimensions(frame) for frame in samad]
    fighter_sizes = [dimensions(frame) for frame in fighter]
    helicopter_sizes = [dimensions(frame) for frame in helicopter]
    assert all(29 <= width <= 36 and 12 <= height <= 32 for width, height in samad_sizes)
    assert all(26 <= width <= 52 and 17 <= height <= 35 for width, height in fighter_sizes)
    assert all(28 <= width <= 53 and 22 <= height <= 47 for width, height in helicopter_sizes)


def test_rotor_muzzle_and_impact_are_dedicated_animations() -> None:
    renderer = load_renderer()
    rotor = renderer.render_ah64_rotor_frames()
    muzzle = renderer.render_air_muzzle_frames()
    impact = renderer.render_air_impact_frames()
    assert len(rotor) == 12 and len({digest(frame) for frame in rotor}) == 12
    assert len(muzzle) == 48 and len({digest(frame) for frame in muzzle}) == 48
    assert len(impact) == 9 and len({digest(frame) for frame in impact}) == 9


def test_samad_is_one_way_and_has_distinct_dive_sequence() -> None:
    actor = RULES.split("\nSAMAD:\n", 1)[1].split("\nM1A2S.Husk:\n", 1)[0]
    sequence = SEQUENCES.split("\nsamad:\n", 1)[1].split("\nf15sa:\n", 1)[0]
    assert "\t-AttackAircraft:" in actor
    assert "\tAttackDive:" in actor
    assert "\t-Rearmable:" in actor
    assert "\t-KillsSelf" not in actor
    assert "\tKillsSelf@PAYLOAD:" in actor
    assert "\tWithFacingSpriteBody@DIVE:" in actor
    assert "\tdive:\n\t\tStart: 16" in sequence

    dive_activity = (
        ENGINE / "OpenRA.Mods.Common" / "Activities" / "Air" / "DiveAttack.cs"
    ).read_text(encoding="utf-8")
    assert "desiredAltitude = Math.Min" in dive_activity
    assert "ReturnToBase" not in dive_activity
    assert "Rearm" not in dive_activity


def test_aircraft_are_rearmable_and_available_to_ai() -> None:
    fighter = RULES.split("\nF15SA:\n", 1)[1].split("\nAH64SA:\n", 1)[0]
    helicopter = RULES.split("\nAH64SA:\n", 1)[1].split("\nSAMAD:\n", 1)[0]
    assert "\tRearmable:" in fighter and "\tAmmoPools: aam, gun" in fighter
    assert "\tBuildAtProductionType: Helicopter" in fighter
    assert "\tRearmable:" in helicopter and "\tAmmoPools: cannon, rockets" in helicopter
    assert "f15sa:" in RULES and "ah64sa:" in RULES
    assert RULES.count("AirUnitsTypes: mig, yak, heli, hind, mh60, samad, f15sa, ah64sa") == 5


def test_observation_serializer_supports_multiple_aircraft_ammo_pools() -> None:
    serializer = (
        ENGINE
        / "OpenRA.Mods.Common"
        / "Traits"
        / "Player"
        / "ObservationSerializer.cs"
    ).read_text(encoding="utf-8")
    assert "TraitsImplementing<AmmoPool>().ToArray()" in serializer
    assert "Sum(pool => pool.CurrentAmmoCount)" in serializer


def test_air_audio_is_openra_pcm_and_bounded() -> None:
    files = (
        "redsea-drone-strike.wav",
        "redsea-drone-loiter.wav",
        "redsea-drone-impact.wav",
        "redsea-f15-missile.wav",
        "redsea-f15-cannon.wav",
        "redsea-ah64-cannon.wav",
        "redsea-ah64-rocket.wav",
        "rsa-air-select-ar.wav",
        "rsa-air-select-en.wav",
        "rsa-air-action-ar.wav",
        "rsa-air-action-en.wav",
        "rye-drone-select-ar.wav",
        "rye-drone-select-en.wav",
        "rye-drone-action-ar.wav",
        "rye-drone-action-en.wav",
    )
    for name in files:
        path = BITS / name
        assert path.is_file() and path.stat().st_size > 1000
        with wave.open(str(path), "rb") as audio:
            assert audio.getnchannels() == 1
            assert audio.getsampwidth() == 2
            assert audio.getframerate() == 44100
            duration = audio.getnframes() / audio.getframerate()
            assert 0.15 <= duration <= 4.5
