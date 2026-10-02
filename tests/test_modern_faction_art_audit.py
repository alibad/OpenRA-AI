"""Unit tests for the modern-faction art audit, palette quantizer and generator fixes."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys

import numpy as np
import pytest
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import faction_palette as fp  # noqa: E402
import modern_faction_art_audit as audit  # noqa: E402
import modern_faction_mesh_lint as mesh_lint  # noqa: E402


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- MiniYaml


def test_miniyaml_parses_nesting_comments_and_escapes() -> None:
    text = "﻿cnqilin:\n\tDefaults:\n\t\tFilename: cnqilin.shp # comment\n\tidle:\n\t\tFacings: 32\n\ticon:\n\t\tLabel: A\\#1\n"
    nodes = audit.parse_miniyaml(text)
    assert [n.key for n in nodes] == ["cnqilin"]
    image = nodes[0]
    assert image.get("Defaults").value_of("Filename") == "cnqilin.shp"
    assert image.get("idle").value_of("Facings") == "32"
    assert image.get("icon").value_of("Label") == "A#1"


def test_saved_count_and_rules_key_candidates() -> None:
    assert audit.parse_saved_count("Saved minigun-[0..47].png") == 48
    assert "CNQILIN.Husk" in audit.rules_key_candidates("cnqilin.husk")
    assert "F15SA.STRIKE" in audit.rules_key_candidates("f15sa.strike")


# --------------------------------------------------------------------------- frame resolution


def sequence(**fields: str) -> audit.SequenceSpec:
    body = "".join(f"\t{key}: {value}\n" for key, value in fields.items())
    nodes = audit.parse_miniyaml(f"seq:\n{body}")
    return audit.parse_sequences("test", nodes)["seq"]


def test_frame_indices_follow_default_sprite_sequence() -> None:
    turret = sequence(Filename="a.shp", Start="32", Facings="32")
    groups = turret.frame_indices(64)
    assert groups[0] == [32] and groups[31] == [63]

    muzzle = sequence(Filename="m.shp", Length="6", Facings="8")
    assert muzzle.frame_indices(48)[1] == [6, 7, 8, 9, 10, 11]

    unload = sequence(Filename="k.shp", Start="19", Facings="16", Stride="4")
    assert [group[0] for group in unload.frame_indices(144)[:3]] == [19, 23, 27]

    reversed_ring = sequence(Filename="r.shp", Facings="-4")
    assert [group[0] for group in reversed_ring.frame_indices(4)] == [0, 3, 2, 1]

    transposed = sequence(Filename="t.shp", Length="2", Facings="4", Transpose="True")
    assert transposed.frame_indices(8)[1] == [1, 5]

    explicit = sequence(Filename="e.shp", Frames="5, 3, 1", Length="*")
    assert explicit.frame_indices(6) == [[5, 3, 1]]

    shadowed = sequence(Filename="s.shp", Length="2", ShadowStart="10")
    assert shadowed.frame_indices(12) == [[0, 1, 10, 11]]


def test_facing_angles_classic_and_uniform() -> None:
    classic = sequence(Filename="a.shp", Facings="32", UseClassicFacings="True")
    uniform = sequence(Filename="a.shp", Facings="16")
    assert [classic.facing_angle(i) for i in (0, 8, 16, 24)] == [0, 256, 512, 768]
    assert classic.facing_angle(1) == 40
    assert uniform.facing_angle(4) == 256


def test_screen_direction_and_turret_offset_follow_openra() -> None:
    assert audit.expected_screen_direction(0) == pytest.approx((0.0, -1.0))
    assert audit.expected_screen_direction(256) == pytest.approx((-1.0, 0.0), abs=1e-9)
    # 1024 units forward: straight up at north (with the classic 40 degree fudge),
    # straight left at west.
    dx, dy = audit.turret_screen_offset((1024, 0, 0), 0)
    assert dx == pytest.approx(0.0, abs=1e-9) and dy == pytest.approx(-24 * 658 / 1024)
    dx, dy = audit.turret_screen_offset((1024, 0, 0), 256)
    assert dx == pytest.approx(-24.0) and dy == pytest.approx(0.0, abs=1e-9)
    # Positive local Y is to the right of the hull.
    dx, _ = audit.turret_screen_offset((0, 1024, 0), 0)
    assert dx == pytest.approx(24.0)


# --------------------------------------------------------------------------- geometry metrics


def bar(angle: int, *, mirrored: bool = False, size: int = 41, length: int = 16, width: int = 3) -> np.ndarray:
    dx, dy = audit.expected_screen_direction(angle)
    if mirrored:
        dx = -dx
    image = Image.new("L", (size, size), 0)
    c = size / 2
    ImageDraw.Draw(image).line((c, c, c + dx * length, c + dy * length), fill=255, width=width)
    return np.array(image) > 0


def test_handedness_and_front_landmark_detect_mirrored_rings() -> None:
    angles = [i * 1024 // 16 for i in range(16)]
    native = [bar(a) for a in angles]
    mirrored = [bar(a, mirrored=True) for a in angles]
    axes = [audit.principal_axis(mask) for mask in native]
    scores = audit.handedness_scores(axes, angles)
    assert scores["native"] > 0.9 > scores["mirrored"]
    scores = audit.handedness_scores([audit.principal_axis(m) for m in mirrored], angles)
    assert scores["mirrored"] > 0.9 > scores["native"]
    front = audit.front_landmark_scores(native, angles, (20.5, 20.5))
    assert front["best_hypothesis"] == "native" and front["median_error_degrees"] < 10
    front = audit.front_landmark_scores(mirrored, angles, (20.5, 20.5))
    assert front["best_hypothesis"] == "mirrored_x"


def test_pivot_fit_separates_rotation_from_orbit() -> None:
    angles = [i * 1024 // 32 for i in range(32)]
    in_place = [(20.0 + 1.5 * math.cos(a * math.tau / 1024), 20.0) for a in angles]
    fit = audit.pivot_fit(in_place, angles)
    assert fit["center"] == pytest.approx([20.0, 20.0], abs=0.01) and fit["rms_wobble"] < 0.01
    jitter = [(20.0 + (1.8 if i % 2 else -1.8), 20.0) for i in range(32)]
    assert audit.pivot_fit(jitter, angles)["rms_wobble"] > 1.5


def test_enclosed_holes_and_planform_aspect() -> None:
    frame = np.zeros((20, 20), dtype=np.uint8)
    frame[4:16, 4:16] = 90
    frame[7:13, 7:13] = 0
    assert audit.enclosed_holes(frame) == 36
    needle = np.zeros((40, 40), dtype=bool)
    needle[5:35, 19:21] = True
    assert audit.planform_aspect(needle) < 0.1
    plane = needle.copy()
    plane[15:18, 5:35] = True
    assert audit.planform_aspect(plane) > 0.8


def test_player_palette_remaps_only_the_ramp() -> None:
    base = np.zeros((256, 4), dtype=np.uint8)
    base[:, 3] = 255
    base[:, 0] = np.arange(256)
    base[80:96, :3] = np.linspace(230, 30, 16)[:, None].astype(np.uint8)
    remapped = audit.player_palette(base, (40, 90, 230))
    assert (remapped[:80] == base[:80]).all() and (remapped[96:] == base[96:]).all()
    assert remapped[80, 2] > remapped[80, 0]  # blue player
    assert remapped[80, 2] > remapped[95, 2]  # ramp keeps its brightness order


# --------------------------------------------------------------------------- palette quantizer


def reference_palette() -> Image.Image:
    palette = [0, 0, 0] * 256
    for index in range(256):
        palette[index * 3:index * 3 + 3] = [(index * 37) % 256, (index * 91) % 256, (index * 53) % 256]
    for offset, value in enumerate(np.linspace(230, 20, 16).astype(int)):
        palette[(80 + offset) * 3:(80 + offset) * 3 + 3] = [value, int(value * 0.85), int(value * 0.4)]
    for index in (1, 3, 4, 12):
        palette[index * 3:index * 3 + 3] = [0, 0, 0]
    image = Image.new("P", (1, 1))
    image.putpalette(palette)
    return image


def test_quantizer_maps_markers_shadow_and_reserved_indices() -> None:
    palette = reference_palette()
    image = Image.new("RGBA", (8, 1), (0, 0, 0, 0))
    image.putpixel((0, 0), (*fp.team_marker(1.0), 255))
    image.putpixel((1, 0), (*fp.team_marker(0.45), 255))
    image.putpixel((2, 0), (0, 0, 0, 255))  # opaque black: never 1/3/4
    image.putpixel((3, 0), (0, 0, 0, 70))  # translucent contact shadow
    image.putpixel((4, 0), (0, 0, 0, 10))  # faint: transparent
    image.putpixel((5, 0), (200, 180, 90, 255))  # ordinary sand: never the remap ramp
    result = np.array(fp.quantize_sprite(image, palette)).ravel().tolist()
    assert 80 <= result[0] < result[1] <= 93
    assert result[2] not in (0, 1, 3, 4)
    assert result[3] == fp.SHADOW and result[4] == 0
    assert not 80 <= result[5] <= 103
    again = np.array(fp.quantize_sprite(image, palette)).ravel().tolist()
    assert again == result


def test_neutralized_markers_are_not_team_colored() -> None:
    image = Image.new("RGBA", (2, 1), (*fp.team_marker(0.8), 255))
    neutral = np.array(fp.neutralize_team_markers(image))
    assert not fp.is_team_marker(neutral[..., :3]).any()


# --------------------------------------------------------------------------- generator regressions


def assert_ring_points_along_facings(frames: list[Image.Image], length: int, facings: int) -> None:
    """Every facing's flash/projectile far end must point along the OpenRA facing."""

    for facing in range(facings):
        frame = frames[facing * length]
        mask = np.array(frame.getchannel("A")) >= 96
        pivot = (frame.width / 2, frame.height / 2)
        direction = audit.front_direction(mask, pivot, fraction=0.2)
        expected = audit.expected_screen_direction(facing * 1024 // facings)
        assert direction is not None
        error = math.degrees(math.acos(max(-1.0, min(1.0, direction[0] * expected[0] + direction[1] * expected[1]))))
        assert error < 35, (facing, error)


def test_muzzle_flashes_point_along_openra_facings() -> None:
    import red_sea_directional_vehicle as red_sea

    assert_ring_points_along_facings(red_sea.render_air_muzzle_frames(48), 6, 8)
    china = load_script("build_china_assets", "build-china-assets.py")
    assert_ring_points_along_facings(china.muzzle_frames(48, True), 6, 8)
    import iran_directional_assets as iran

    assert_ring_points_along_facings(iran.render_effect("muzzle", 48), 6, 8)


def test_projectiles_turn_counter_clockwise() -> None:
    china = load_script("build_china_assets", "build-china-assets.py")
    frames = china.projectile_frames("missile")
    angles = [i * 1024 // 16 for i in range(16)]
    axes = [audit.principal_axis(np.array(frame.getchannel("A")) >= 96) for frame in frames]
    scores = audit.handedness_scores(axes, angles)
    assert scores["native"] > 0.8 > scores["mirrored"]


def test_classic_meshes_have_no_culled_panels_or_open_hulls() -> None:
    results = mesh_lint.lint_all()
    failures = {label: mesh_lint.classic_failures(result) for label, result in results.items()}
    assert {label: problems for label, problems in failures.items() if problems} == {}


def test_turkey_ship_turret_rotates_in_place() -> None:
    import turkey_directional_assets as turkey

    frames = turkey.render_ship("ege", 56)[16:]
    hubs = [audit.hub(np.array(frame.getchannel("A")) >= 96) for frame in frames]
    angles = [audit.CLASSIC_SPRITE_FACINGS[i] for i in range(32)]
    fit = audit.pivot_fit(hubs, angles)
    assert max(fit["orbit"]) < 2.0


def test_wingless_aircraft_regression() -> None:
    import iran_directional_assets as iran

    frames = iran.render_azar(56, 16)
    aspects = [audit.planform_aspect(np.array(frame.getchannel("A")) >= 96) for frame in frames]
    assert np.median(aspects) > 0.4
