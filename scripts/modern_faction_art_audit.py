#!/usr/bin/env python3
"""Domain-wide art audit for the Classic (``ra``) optional modern factions.

The audit reads exactly what the game reads:

* the Experience catalog (``mods/ra/experiences.yaml``) supplies each faction
  pack's declared roster and presentation preview;
* ``OpenRA.Utility --resolved-rules`` and ``--resolved-sequences`` supply the
  merged actor rules and sequence definitions for the World War III profile,
  so inheritance, removals and experience overlays are applied by the engine;
* ``OpenRA.Utility --extract`` and ``--png`` decode every sprite with the
  engine's own frame loaders, including native reference sprites stored in
  the Red Alert content packages.

It then checks file hashes, dimensions, palette indices, transparency,
player-colour remap use, palette-animated indices, frame counts against the
YAML frame ranges, sequence reachability from actor traits, facing counts,
OpenRA facing handedness, pivot stability, turret seating, shadows, clipping,
duplicate and palette-only art across actors and factions, production icons
and faction previews.  Contact sheets are rendered by
``modern_faction_art_sheets.py`` from the same decoded frames.

Numeric checks are structural evidence only.  Every sheet must still be
inspected and the units must be seen moving in a rendered game.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]

TRANSPARENT_INDEX = 0
PLAYER_SHADOW_INDEX = 4
REMAP_INDICES = range(80, 96)
# RotationPaletteEffect@actorswater cycles 0x60..0x66 in the player/effect
# palettes and LightPaletteRotator rewrites index 103 in the player palette.
WATER_CYCLE_INDICES = range(96, 103)
LIGHT_ROTATOR_INDEX = 103
TILE_SIZE = 24
CAMERA_PITCH_SIN = 658 / 1024  # WAngle.FromDegrees(40).Sin() / 1024

# Authored yaw of each classic 32-facing frame (OpenRA.Mods.Cnc.Util.SpriteFacings).
CLASSIC_SPRITE_FACINGS = (
    0, 40, 74, 112, 146, 172, 200, 228,
    256, 284, 312, 340, 370, 402, 436, 472,
    512, 552, 588, 626, 658, 684, 712, 740,
    768, 796, 824, 852, 882, 914, 948, 984,
)

TILESETS = ("TEMPERAT", "SNOW", "DESERT")
TERRAIN_PALETTES = {"TEMPERAT": "temperat.pal", "SNOW": "snow.pal", "DESERT": "desert.pal"}
TERRAIN_TILES = {"TEMPERAT": "clear1.tem", "SNOW": "clear1.sno", "DESERT": "clear1.des"}

DOMAINS = ("Infantry", "Vehicles", "Aircraft", "Navy", "Buildings", "Defenses")

# Role-paired native Red Alert references.  Each custom actor is compared with
# a stock actor that performs the same battlefield job.
ROLE_PAIRS = {
    # China
    "CNRIFLE": "E1", "CNNETWORK": "E6", "CNPORTABLE": "E3", "REDSPEAR": "E7",
    "CNQILIN": "3TNK", "CNLYNX": "JEEP", "CNZBD": "APC", "CNPHL": "V2RL", "CNMANTIS": "FTRK",
    "CNSKYSPEAR": "MIG", "CNCLOUD": "YAK", "CNCRANE": "TRAN",
    "CNLUYANG": "DD", "CNHAIWANG": "CA", "CNHAIYING": "PT", "CNKUNLUN": "LST", "CNJIAOLONG": "SS",
    "CNBASTION": "GUN", "CNSKYSHIELD": "SAM", "CNSPECTRUM": "GAP",
    # Iran
    "IRBAS": "E1", "IRATGM": "E3", "IRDC": "E6", "SHADOWONE": "SPY",
    "IRKARR": "3TNK", "IRRAAD": "FTRK", "IRFAJR": "V2RL", "IRCOAST": "V2RL",
    "IRAZAR": "MIG", "IRTOUFAN": "HIND", "IRMOHAJER": "YAK", "IRLOITER": "YAK",
    "IRPEY": "PT", "IRGHADIR": "SS", "IRHPAD": "HPAD",
    # Saudi Arabia
    "SANG": "E1", "SAJTAC": "E6", "SAAT": "E3", "FALCON1": "E7",
    "M1A2S": "2TNK", "SADS": "FTRK", "F15SA": "MIG", "AH64SA": "HELI",
    "SA_FRGT": "DD", "SA_INTC": "PT", "SA_FSS": "DD", "SAFLD": "AFLD",
    # Yemen
    "YMR": "E1", "YRPG": "E3", "YSPOT": "E6", "WADIGHOST": "SPY",
    "TECH": "JEEP", "YMLR": "V2RL", "SAMAD": "YAK",
    "YE_MSLC": "PT", "YE_USV": "PT", "YE_SURVE": "PT",
    # Turkey
    "TRRIFLE": "E1", "TRAT": "E3", "TRDRONEOP": "E6", "GREYWOLF": "E7",
    "BOZKIR": "2TNK", "ARAS8": "APC", "YILDIRIM": "ARTY", "GOKKALKAN": "FTRK",
    "SANCAK": "2TNK", "DENIZKAPLAN": "APC",
    "KUZGUNM": "YAK", "TURNAAH": "HELI", "SAHINX": "MIG",
    "MARMARA": "DD", "EGE": "PT", "POYRAZ": "PT",
}

# How each generator produces its production cameo, recorded from the
# generator source.  A cameo derived from an in-game world frame is not an
# authored production portrait (roadmap gate 4).
ICON_PROVENANCE: dict[str, str] = {
    **{f"{name}icon.shp": "authored painted cameo atlas (build-china-assets.py icon_frames)" for name in (
        "cnqilin", "cnlynx", "cnzbd", "cnphl", "cnmantis", "cnskyspear", "cncloud", "cncrane",
        "cnluyang", "cnhaiwang", "cnhaiying", "cnkunlun", "cnjiaolong", "cnbastion", "cnskyshield", "cnspectrum")},
    **{f"{name}icon.shp": "authored painted source (build-red-sea-sprites.py save_icon_frame)" for name in (
        "m1a2s", "sads", "tech", "ymlr", "samad", "f15sa", "ah64sa")},
}
for _name in ("irkarr", "irraad", "irfajr", "ircoast", "irazar", "irtoufan", "irmohajer", "irloiter", "irpey", "irghadir"):
    ICON_PROVENANCE[f"{_name}icon.shp"] = "authored flat vector illustration (build-iran-sprites.py _directional_icon)"
for _name in ("bozkir", "aras8", "yildirim", "gokkalkan", "sancak", "denizkaplan", "kuzgunm", "turnaah", "sahinx",
              "marmara", "ege", "poyraz"):
    ICON_PROVENANCE[f"{_name}icon.shp"] = "dedicated three-quarter portrait render (build-turkey-sprites.py portrait)"
for _name in ("sa_frgt", "sa_intc", "sa_fss", "ye_mslc", "ye_usv", "ye_surve"):
    ICON_PROVENANCE[f"{_name}_icon.shp"] = ("dedicated three-quarter portrait on an opaque sea plate "
                                            "(packaging/naval/generate_naval_assets.py icon_for)")
# Provenance recorded before the 2026-09 audit fixes; pass --icon-provenance
# before to evaluate a pre-fix engine checkout.
PRE_FIX_ICON_PROVENANCE: dict[str, str] = {
    **{f"{name}icon.shp": "world-frame: build-turkey-sprites.py passed the facing-0 world frame (hull only) to icon_frame"
       for name in ("bozkir", "aras8", "yildirim", "gokkalkan", "sancak", "denizkaplan", "kuzgunm", "turnaah", "sahinx",
                    "marmara", "ege", "poyraz")},
    **{f"{name}_icon.shp": "world-frame: generate_naval_assets.py icon_for pasted the facing-4 world frame over a transparent canvas"
       for name in ("sa_frgt", "sa_intc", "sa_fss", "ye_mslc", "ye_usv", "ye_surve")},
}

FACTION_PACKS = {
    "china": "china-faction",
    "iran": "iran-faction",
    "saudi": "saudi-arabia-faction",
    "yemen": "yemen-faction",
    "turkey": "turkey-faction",
}


# ---------------------------------------------------------------------------
# MiniYaml


@dataclasses.dataclass
class YamlNode:
    key: str
    value: str
    nodes: list["YamlNode"] = dataclasses.field(default_factory=list)

    def get(self, key: str) -> "YamlNode | None":
        for node in self.nodes:
            if node.key == key:
                return node
        return None

    def value_of(self, key: str, default: str | None = None) -> str | None:
        node = self.get(key)
        return node.value if node is not None and node.value != "" else default

    def to_dict(self) -> dict[str, Any]:
        return {node.key: (node.value if not node.nodes else node.to_dict() | ({"": node.value} if node.value else {}))
                for node in self.nodes}


def _strip_comment(text: str) -> str:
    result = []
    escaped = False
    for character in text:
        if character == "\\" and not escaped:
            escaped = True
            continue
        if character == "#" and not escaped:
            break
        result.append(character)
        escaped = False
    return "".join(result)


def parse_miniyaml(text: str) -> list[YamlNode]:
    """Parse MiniYaml into a node tree.

    Indentation is one tab (or four spaces) per level, as written by
    ``MiniYaml.WriteToString``.  Comments start with an unescaped ``#``.
    """

    root = YamlNode("", "")
    stack: list[tuple[int, YamlNode]] = [(-1, root)]
    for raw in text.lstrip("﻿").splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = 0
        position = 0
        while position < len(line):
            if line[position] == "\t":
                indent += 1
                position += 1
            elif line.startswith("    ", position):
                indent += 1
                position += 4
            else:
                break
        body = line[position:]
        if ":" in body:
            key, _, value = body.partition(":")
        else:
            key, value = body, ""
        node = YamlNode(key.strip(), value.strip())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack[-1][1].nodes.append(node)
        stack.append((indent, node))
    return root.nodes


def yaml_find(nodes: Iterable[YamlNode], key: str) -> YamlNode | None:
    for node in nodes:
        if node.key == key:
            return node
    return None


def split_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Sequence frame resolution (mirrors DefaultSpriteSequence.CalculateFrameIndices)


@dataclasses.dataclass
class SequenceSpec:
    image: str
    name: str
    filename: str | None
    tileset_filenames: dict[str, str]
    start: int
    length: int | None  # None means "*"
    stride: int | None
    facings: int
    reverse_facings: bool
    interpolated_facings: int | None
    frames: list[int] | None
    transpose: bool
    shadow_start: int
    use_classic_facings: bool
    tick: int
    z_offset: str
    combine: bool
    raw: dict[str, str]

    def filename_for(self, tileset: str) -> str | None:
        return self.tileset_filenames.get(tileset, self.filename)

    def frame_indices(self, frame_count: int) -> list[list[int]]:
        """Return source frame indices grouped per facing (facing-major)."""

        length = self.length
        source = list(self.frames) if self.frames is not None else list(range(frame_count))
        if length is None:
            length = len(source) - self.start
        stride = self.stride if self.stride is not None else length
        groups: list[list[int]] = []
        for facing in range(self.facings):
            inner = (self.facings - facing) % self.facings if self.reverse_facings else facing
            group = []
            for frame in range(length):
                index = frame * self.facings + inner if self.transpose else inner * stride + frame
                if self.frames is not None:
                    # Frames remaps the loaded list; Start/stride index into it.
                    position = self.start + index if self.start else index
                    group.append(source[position] if 0 <= position < len(source) else -1)
                else:
                    group.append(self.start + index)
            groups.append(group)
        if self.shadow_start >= 0:
            offset = self.shadow_start - self.start
            groups = [group + [value + offset for value in group] for group in groups]
        return groups

    def facing_angle(self, facing: int) -> int:
        """WAngle (0..1023, counter-clockwise from north) authored for a facing."""

        if self.use_classic_facings and self.facings == 32:
            return CLASSIC_SPRITE_FACINGS[facing]
        return (facing * 1024 // self.facings) % 1024


def _int(value: str | None, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value.strip())


def parse_sequences(image: str, nodes: list[YamlNode]) -> dict[str, SequenceSpec]:
    """Build SequenceSpec objects from an engine-resolved sequence tree."""

    defaults = yaml_find(nodes, "Defaults")
    defaults_map = {n.key: n for n in defaults.nodes} if defaults else {}
    result: dict[str, SequenceSpec] = {}
    for node in nodes:
        if node.key in ("Defaults", "Inherits") or node.key.startswith("-"):
            continue
        own = {n.key: n for n in node.nodes}

        def field(key: str) -> str | None:
            if key in own:
                return own[key].value
            if key in defaults_map:
                return defaults_map[key].value
            return None

        def field_node(key: str) -> YamlNode | None:
            return own.get(key) or defaults_map.get(key)

        tileset_node = field_node("TilesetFilenames")
        tileset_filenames = {n.key: n.value for n in tileset_node.nodes} if tileset_node else {}
        length_value = field("Length")
        length: int | None = None if length_value == "*" else _int(length_value, 1)
        facings = _int(field("Facings"), 1)
        frames_value = field("Frames")
        frames = [int(v) for v in split_list(frames_value)] if frames_value else None
        stride_value = field("Stride")
        interpolated = field("InterpolatedFacings")
        result[node.key] = SequenceSpec(
            image=image,
            name=node.key,
            filename=field("Filename"),
            tileset_filenames=tileset_filenames,
            start=_int(field("Start"), 0),
            length=length,
            stride=_int(stride_value, 0) if stride_value else None,
            facings=abs(facings),
            reverse_facings=facings < 0,
            interpolated_facings=abs(int(interpolated)) if interpolated else None,
            frames=frames,
            transpose=(field("Transpose") or "").lower() == "true",
            shadow_start=_int(field("ShadowStart"), -1),
            use_classic_facings=(field("UseClassicFacings") or "").lower() == "true",
            tick=_int(field("Tick"), 40),
            z_offset=field("ZOffset") or "0",
            combine=field_node("Combine") is not None,
            raw={n.key: n.value for n in node.nodes},
        )
    return result


# ---------------------------------------------------------------------------
# Geometry and colour helpers


def expected_screen_direction(angle: int) -> tuple[float, float]:
    """Screen direction (x right, y down) of a WAngle facing (north = up, CCW)."""

    theta = angle * 2 * math.pi / 1024
    return (-math.sin(theta), -math.cos(theta))


def turret_screen_offset(offset: tuple[int, int, int], body_angle: int) -> tuple[float, float]:
    """Screen pixel offset of a Turreted.Offset for a body facing.

    Mirrors ``BodyOrientationInfo.LocalToWorld(Offset.Rotate(WRot.FromYaw(a)))``
    with the classic perspective fudge and ``WorldRenderer.ScreenPxOffset``.
    """

    forward, right, up = offset
    theta = body_angle * 2 * math.pi / 1024
    rotated_x = forward * math.cos(theta) + right * math.sin(theta)
    rotated_y = -forward * math.sin(theta) + right * math.cos(theta)
    world_x = rotated_y
    world_y = -CAMERA_PITCH_SIN * rotated_x
    world_z = up
    return (TILE_SIZE * world_x / 1024, TILE_SIZE * (world_y - world_z) / 1024)


def solid_mask(frame: np.ndarray) -> np.ndarray:
    """Opaque pixels excluding transparent and shadow indices."""

    return (frame != TRANSPARENT_INDEX) & (frame != PLAYER_SHADOW_INDEX)


def principal_axis(mask: np.ndarray) -> tuple[float, float] | None:
    """Return (axis angle in radians mod pi, elongation) of a pixel mask."""

    ys, xs = np.nonzero(mask)
    if len(xs) < 6:
        return None
    x = xs - xs.mean()
    y = ys - ys.mean()
    cxx = float((x * x).mean())
    cyy = float((y * y).mean())
    cxy = float((x * y).mean())
    angle = 0.5 * math.atan2(2 * cxy, cxx - cyy)
    spread = math.sqrt(((cxx - cyy) / 2) ** 2 + cxy ** 2)
    major = (cxx + cyy) / 2 + spread
    minor = max((cxx + cyy) / 2 - spread, 1e-6)
    return (angle % math.pi, math.sqrt(major / minor))


def handedness_scores(axes: list[tuple[float, float] | None], angles: list[int], min_elongation: float = 1.25) -> dict[str, Any]:
    """Compare measured principal axes with the native and mirrored facing rings.

    Returns the mean cos(2*delta) agreement (1 = aligned) for the native
    counter-clockwise ring and for a mirrored (clockwise) ring.  Only frames
    whose silhouettes are clearly elongated contribute.
    """

    native = []
    mirrored = []
    worst = 0.0
    for axis, angle in zip(axes, angles):
        if axis is None or axis[1] < min_elongation:
            continue
        dx, dy = expected_screen_direction(angle)
        expected = math.atan2(dy, dx) % math.pi
        mirrored_expected = math.atan2(dy, -dx) % math.pi
        native.append(math.cos(2 * (axis[0] - expected)))
        mirrored.append(math.cos(2 * (axis[0] - mirrored_expected)))
        delta = abs((axis[0] - expected + math.pi / 2) % math.pi - math.pi / 2)
        worst = max(worst, math.degrees(delta))
    if not native:
        return {"samples": 0, "native": None, "mirrored": None, "worst_axis_error_degrees": None}
    return {
        "samples": len(native),
        "native": round(float(np.mean(native)), 3),
        "mirrored": round(float(np.mean(mirrored)), 3),
        "worst_axis_error_degrees": round(worst, 1),
    }


def front_direction(mask: np.ndarray, pivot: tuple[float, float], fraction: float = 0.12) -> tuple[float, float] | None:
    """Direction from the pivot to the farthest pixels (e.g. a barrel tip)."""

    ys, xs = np.nonzero(mask)
    if len(xs) < 4:
        return None
    dx = xs + 0.5 - pivot[0]
    dy = ys + 0.5 - pivot[1]
    distance = np.hypot(dx, dy)
    count = max(2, int(len(xs) * fraction))
    order = np.argsort(distance)[-count:]
    vx, vy = float(dx[order].mean()), float(dy[order].mean())
    norm = math.hypot(vx, vy)
    if norm < 1.5:
        return None
    return (vx / norm, vy / norm)


def front_landmark_scores(masks: list[np.ndarray], angles: list[int], pivot: tuple[float, float]) -> dict[str, Any]:
    """Check that a directional part's far end (barrel/nose) points along each facing."""

    hypotheses = {"native": (1, 1), "mirrored_x": (-1, 1), "mirrored_y": (1, -1), "reversed": (-1, -1)}
    errors: dict[str, list[float]] = {name: [] for name in hypotheses}
    for mask, angle in zip(masks, angles):
        direction = front_direction(mask, pivot)
        if direction is None:
            continue
        ex, ey = expected_screen_direction(angle)
        for name, (sx, sy) in hypotheses.items():
            dot = direction[0] * ex * sx + direction[1] * ey * sy
            errors[name].append(math.degrees(math.acos(max(-1.0, min(1.0, dot)))))
    if not errors["native"]:
        return {"samples": 0}
    medians = {name: round(float(np.median(values)), 1) for name, values in errors.items()}
    best = min(medians, key=medians.get)
    return {
        "samples": len(errors["native"]),
        "median_error_degrees": medians["native"],
        "max_error_degrees": round(float(np.max(errors["native"])), 1),
        "mirrored_median_error_degrees": medians["mirrored_x"],
        "flipped_median_error_degrees": medians["mirrored_y"],
        "reversed_median_error_degrees": medians["reversed"],
        "best_hypothesis": best,
        "frames_over_60_degrees": int(sum(1 for value in errors["native"] if value > 60)),
    }


def pivot_fit(centroids: list[tuple[float, float] | None], angles: list[int]) -> dict[str, Any] | None:
    """Fit c = p + A[cos, sin] to per-facing centroids.

    ``p`` is the rotation centre implied by the artwork and the residual RMS
    measures wobble: a stable pivot traces a smooth ellipse around ``p``.
    """

    rows = []
    targets_x = []
    targets_y = []
    for centroid, angle in zip(centroids, angles):
        if centroid is None:
            continue
        theta = angle * 2 * math.pi / 1024
        rows.append([1.0, math.cos(theta), math.sin(theta)])
        targets_x.append(centroid[0])
        targets_y.append(centroid[1])
    if len(rows) < 4:
        return None
    matrix = np.array(rows)
    solution_x, *_ = np.linalg.lstsq(matrix, np.array(targets_x), rcond=None)
    solution_y, *_ = np.linalg.lstsq(matrix, np.array(targets_y), rcond=None)
    residual_x = np.array(targets_x) - matrix @ solution_x
    residual_y = np.array(targets_y) - matrix @ solution_y
    residual = np.hypot(residual_x, residual_y)
    return {
        "center": [round(float(solution_x[0]), 2), round(float(solution_y[0]), 2)],
        "orbit": [round(float(math.hypot(solution_x[1], solution_x[2])), 2), round(float(math.hypot(solution_y[1], solution_y[2])), 2)],
        "rms_wobble": round(float(np.sqrt((residual ** 2).mean())), 2),
        "max_wobble": round(float(residual.max()), 2),
    }


def centroid(mask: np.ndarray) -> tuple[float, float] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return (float(xs.mean()) + 0.5, float(ys.mean()) + 0.5)


def enclosed_holes(frame: np.ndarray) -> int:
    """Transparent pixels fully enclosed by artwork (see-through geometry)."""

    empty = frame == TRANSPARENT_INDEX
    height, width = empty.shape
    outside = np.zeros_like(empty)
    stack = [(y, x) for y in range(height) for x in (0, width - 1) if empty[y, x]]
    stack += [(y, x) for x in range(width) for y in (0, height - 1) if empty[y, x]]
    while stack:
        y, x = stack.pop()
        if outside[y, x] or not empty[y, x]:
            continue
        outside[y, x] = True
        if y > 0:
            stack.append((y - 1, x))
        if y < height - 1:
            stack.append((y + 1, x))
        if x > 0:
            stack.append((y, x - 1))
        if x < width - 1:
            stack.append((y, x + 1))
    return int((empty & ~outside).sum())


def planform_aspect(mask: np.ndarray) -> float | None:
    """Minor/major extent of a silhouette measured along its principal axes."""

    ys, xs = np.nonzero(mask)
    if len(xs) < 6:
        return None
    x = xs - xs.mean()
    y = ys - ys.mean()
    axis = principal_axis(mask)
    if axis is None:
        return None
    angle = axis[0]
    u = x * math.cos(angle) + y * math.sin(angle)
    v = -x * math.sin(angle) + y * math.cos(angle)
    major = u.max() - u.min() + 1
    minor = v.max() - v.min() + 1
    return float(minor / major)


def hub(mask: np.ndarray) -> tuple[float, float] | None:
    """Median pixel position: robust to thin barrels, so it tracks the mount."""

    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return (float(np.median(xs)) + 0.5, float(np.median(ys)) + 0.5)


def srgb_to_linear(channel: float) -> float:
    channel /= 255.0
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def linear_to_srgb(channel: float) -> int:
    value = channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055
    return int(round(max(0.0, min(1.0, value)) * 255))


def rgb_to_hsv(r: float, g: float, b: float) -> tuple[float, float, float]:
    maximum = max(r, g, b)
    minimum = min(r, g, b)
    delta = maximum - minimum
    if delta == 0:
        hue = 0.0
    elif maximum == r:
        hue = ((g - b) / delta) % 6
    elif maximum == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    hue /= 6
    saturation = 0.0 if maximum == 0 else delta / maximum
    return hue, saturation, maximum


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
    h6 = (h % 1.0) * 6
    c = v * s
    x = c * (1 - abs(h6 % 2 - 1))
    m = v - c
    sector = int(h6) % 6
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][sector]
    return r + m, g + m, b + m


def player_palette(base: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    """Apply OpenRA's PlayerColorRemap to indices 80..95 of an RGBA palette."""

    hue, saturation, value = rgb_to_hsv(*(srgb_to_linear(c) for c in color))
    palette = base.copy()
    for index in REMAP_INDICES:
        r, g, b = (srgb_to_linear(float(c)) for c in base[index, :3])
        brightness = max(r, g, b)
        nr, ng, nb = hsv_to_rgb(hue, saturation, brightness * value)
        palette[index, :3] = [linear_to_srgb(nr), linear_to_srgb(ng), linear_to_srgb(nb)]
    return palette


def load_pal(path: Path, transparent: Iterable[int] = (0,), shadow: Iterable[int] = ()) -> np.ndarray:
    data = path.read_bytes()[:768]
    palette = np.zeros((256, 4), dtype=np.uint8)
    for index in range(256):
        rgb = [(data[index * 3 + channel] << 2) & 0xFF for channel in range(3)]
        rgb = [value | (value >> 6) for value in rgb]
        palette[index] = [*rgb, 255]
    for index in transparent:
        palette[index] = [0, 0, 0, 0]
    for index in shadow:
        palette[index] = [0, 0, 0, 140]
    return palette


def frame_digest(frame: np.ndarray) -> str:
    return hashlib.sha1(frame.tobytes() + bytes(str(frame.shape), "ascii")).hexdigest()


def mask_digest(frame: np.ndarray) -> str:
    return hashlib.sha1(np.packbits(frame != 0).tobytes() + bytes(str(frame.shape), "ascii")).hexdigest()


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    """Silhouette overlap of two frames after centring their bounding boxes."""

    def crop(mask: np.ndarray) -> np.ndarray:
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            return np.zeros((1, 1), dtype=bool)
        return mask[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]

    ca = crop(a != 0)
    cb = crop(b != 0)
    height = max(ca.shape[0], cb.shape[0])
    width = max(ca.shape[1], cb.shape[1])

    def pad(mask: np.ndarray) -> np.ndarray:
        canvas = np.zeros((height, width), dtype=bool)
        top = (height - mask.shape[0]) // 2
        left = (width - mask.shape[1]) // 2
        canvas[top: top + mask.shape[0], left: left + mask.shape[1]] = mask
        return canvas

    pa, pb = pad(ca), pad(cb)
    union = np.logical_or(pa, pb).sum()
    return float(np.logical_and(pa, pb).sum() / union) if union else 1.0


# ---------------------------------------------------------------------------
# Engine access


SAVED_PATTERN = re.compile(r"Saved .*-\[0\.\.(-?\d+)\]\.png")


def parse_saved_count(stdout: str) -> int:
    """Frame count reported by ``OpenRA.Utility --png`` ("Saved x-[0..N].png")."""

    match = SAVED_PATTERN.search(stdout)
    if not match:
        raise RuntimeError(f"unexpected --png output: {stdout[-300:]}")
    return int(match.group(1)) + 1


def rules_key_candidates(name: str) -> list[str]:
    """Top-level rule keys are case-sensitive; references are often lower case."""

    head, dot, tail = name.partition(".")
    candidates = [name, name.upper()]
    if dot:
        candidates += [f"{head.upper()}.{tail.capitalize()}", f"{head.upper()}.{tail.lower()}", f"{head.upper()}.{tail.upper()}"]
    unique = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


class Engine:
    """Runs OpenRA.Utility in an isolated support directory and caches results."""

    def __init__(self, engine_root: Path, work: Path, content: Path | None, profile: str = "world-war-iii") -> None:
        self.root = engine_root.resolve()
        self.work = work.resolve()
        self.cache = self.work / "cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.support = self.work / "support"
        (self.support).mkdir(parents=True, exist_ok=True)
        (self.support / "settings.yaml").write_text(f"Experience@ra:\n\tProfile: {profile}\n", encoding="utf-8")
        target = self.support / "Content" / "ra" / "v2"
        if content and content.is_dir() and not target.is_dir():
            shutil.copytree(content, target)
        self.content = target if target.is_dir() else None
        self.profile = profile
        executable = "OpenRA.Utility.exe" if os.name == "nt" else "OpenRA.Utility"
        self.utility = self.root / "bin" / executable
        if not self.utility.is_file():
            raise SystemExit(f"OpenRA.Utility not found at {self.utility}; build the engine first")

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update({
            "ENGINE_DIR": str(self.root),
            "SUPPORT_DIR": str(self.support),
            "OPENRA_UTILITY_EXPERIENCE_PROFILE": self.profile,
            "DOTNET_ROLL_FORWARD": "Major",
        })
        return env

    def run(self, args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
        process = subprocess.run([str(self.utility), "ra", *args], cwd=cwd or self.root, env=self.env(),
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
        if check and process.returncode != 0:
            raise RuntimeError(f"OpenRA.Utility {' '.join(args)} failed: {process.stdout[-2000:]} {process.stderr[-2000:]}")
        return process

    def resolved(self, kind: str, key: str) -> list[YamlNode] | None:
        cache = self.cache / f"resolved-{kind}" / f"{key}.yaml"
        if cache.is_file():
            text = cache.read_text(encoding="utf-8")
        else:
            process = self.run([f"--resolved-{kind}", key], check=False)
            if process.returncode != 0 or process.stdout.startswith("Could not find"):
                return None
            text = process.stdout
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(text, encoding="utf-8")
        return parse_miniyaml(text)

    def locate(self, filename: str) -> tuple[Path, str]:
        """Return a readable copy of a sprite/palette file and its origin."""

        for folder in ("mods/ra/bits", "mods/ra/bits/desert", "mods/ra/bits/environment"):
            candidate = self.root / folder / filename
            if candidate.is_file():
                return candidate, "project"
        extracted = self.cache / "content" / filename
        if not extracted.is_file():
            extracted.parent.mkdir(parents=True, exist_ok=True)
            self.run(["--extract", filename], cwd=extracted.parent, check=False)
        if extracted.is_file():
            return extracted, "native"
        raise FileNotFoundError(filename)

    def frames(self, filename: str) -> tuple[list[np.ndarray], dict[str, Any]]:
        """Decode a sprite with the engine loader into indexed numpy frames."""

        path, origin = self.locate(filename)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        stem = Path(path.name).stem
        folder = self.cache / "frames" / f"{digest[:20]}-{stem}"
        marker = folder / "frame-count"
        if not marker.is_file():
            if folder.exists():
                shutil.rmtree(folder)
            folder.mkdir(parents=True)
            palette, _ = self.locate("temperat.pal")
            process = self.run(["--png", str(path), str(palette)], cwd=folder)
            count = parse_saved_count(process.stdout)
            marker.write_text(str(count), encoding="ascii")
        count = int(marker.read_text(encoding="ascii"))
        decoded: dict[int, np.ndarray] = {}
        for file in folder.glob(f"{stem}-*.png"):
            image = Image.open(file)
            if image.mode != "P":
                raise RuntimeError(f"{file} is not an indexed PNG")
            decoded[int(file.stem.rsplit("-", 1)[1])] = np.array(image, dtype=np.uint8)
        # The engine loader trims empty frames to 0x0 and --png skips them;
        # restore them as fully transparent canvases so indices stay aligned.
        shapes = sorted({frame.shape for frame in decoded.values()})
        canvas = shapes[-1] if shapes else (1, 1)
        frames = [decoded.get(index, np.zeros(canvas, dtype=np.uint8)) for index in range(count)]
        info = {"path": str(path), "origin": origin, "sha256": digest, "bytes": len(data),
                "zero_size_frames": count - len(decoded)}
        return frames, info


# ---------------------------------------------------------------------------
# Actor model


RENDER_SEQUENCE_DEFAULTS = {
    "WithFacingSpriteBody": {"Sequence": "idle"},
    "WithSpriteBody": {"Sequence": "idle"},
    "WithSpriteTurret": {"Sequence": "turret"},
    "WithMakeAnimation": {"Sequence": "make"},
    "WithInfantryBody": {"DefaultAttackSequence": "shoot", "StandSequences": "stand", "MoveSequence": "run"},
    "WithDeathAnimation": {"DeathSequence": "die"},
    "WithBuildingBib": {"Sequence": "bib"},
    "WithDamageOverlay": {"IdleSequence": "idle", "LoopSequence": "loop", "EndSequence": "end"},
    "Buildable": {"Icon": "icon"},
    "WithParachute": {"Sequence": "idle"},
}
SEQUENCE_KEY = re.compile(r"(Sequence|Sequences|Icon|Anim)$")


@dataclasses.dataclass
class ActorRecord:
    name: str
    faction: str
    domain: str
    parent: str | None
    rules: list[YamlNode]
    image: str
    traits: dict[str, YamlNode]
    references: dict[str, set[str]]  # image -> referenced sequence names
    turrets: dict[str, tuple[int, int, int]]
    quantized_facings: int | None
    has_shadow_trait: bool
    icon_palette: str | None
    tooltip: str | None
    stock: bool = False


def trait_type(key: str) -> str:
    return key.split("@", 1)[0].lstrip("-")


def parse_wvec(value: str | None) -> tuple[int, int, int]:
    parts = [int(part.strip()) for part in (value or "0,0,0").split(",")]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def actor_record(name: str, faction: str, domain: str, parent: str | None, rules: list[YamlNode]) -> ActorRecord:
    traits = {node.key: node for node in rules}
    render = next((node for key, node in traits.items() if trait_type(key) == "RenderSprites"), None)
    image = (render.value_of("Image") if render else None) or name.lower()
    references: dict[str, set[str]] = {}

    def add(target_image: str | None, sequence: str | None) -> None:
        if not sequence:
            return
        references.setdefault((target_image or image).lower(), set()).add(sequence)

    turrets: dict[str, tuple[int, int, int]] = {}
    armament_muzzles: list[str] = []
    for key, node in traits.items():
        if key.startswith("-"):
            continue
        kind = trait_type(key)
        own_image = node.value_of("Image")
        defaults = RENDER_SEQUENCE_DEFAULTS.get(kind, {})
        for field, default in defaults.items():
            value = node.value_of(field, default)
            for item in split_list(value):
                add(own_image if kind not in ("Buildable",) else None, item)
        for child in node.nodes:
            if SEQUENCE_KEY.search(child.key) and child.key not in defaults and child.value:
                if kind == "ThrowsParticle" and child.key == "Anim":
                    add(own_image, child.value)
                elif kind in ("WithDecoration", "WithIdleOverlay", "WithSpriteBody", "WithFacingSpriteBody",
                              "WithAttackOverlay", "WithDeliveryAnimation", "WithProductionOverlay",
                              "WithChargeOverlay", "WithDockedOverlay", "WithResupplyAnimation",
                              "WithAttackAnimation", "WithAimAnimation", "WithMoveAnimation",
                              "WithTurretAttackAnimation", "WithSpriteTurret", "WithInfantryBody",
                              "WithDeathAnimation", "WithMuzzleOverlay", "WithRangeCircle", "WithBuildingPlacedAnimation",
                              "WithMakeAnimation", "WithSpriteRotorOverlay", "WithGateSpriteBody", "WithWallSpriteBody",
                              "WithEmbeddedTurretSpriteBody", "WithDamageOverlay", "WithHarvestAnimation",
                              "WithDockingAnimation", "WithCrateBody", "WithSplitAttackPaletteInfantryBody",
                              "WithPermanentInjury", "WithTurretedSpriteBody", "Armament", "WithCarrierParentPipsDecoration",
                              "WithParachute", "WithShadow", "WithSpriteControlGroupDecoration"):
                    for item in split_list(child.value):
                        add(own_image, item)
            if kind == "WithInfantryBody" and child.key == "IdleSequences":
                for item in split_list(child.value):
                    add(None, item)
        if kind == "Armament":
            muzzle = node.value_of("MuzzleSequence")
            if muzzle:
                armament_muzzles.append(muzzle)
        if kind == "Turreted":
            turrets[node.value_of("Turret", "primary")] = parse_wvec(node.value_of("Offset"))
        if kind == "WithDeathAnimation":
            prefix = node.value_of("DeathSequence", "die")
            types = node.get("DeathTypes")
            if types:
                for child in types.nodes:
                    add(node.value_of("Image"), f"{prefix}{child.value}")
            fallback = node.value_of("FallbackSequence")
            if fallback:
                add(node.value_of("Image"), fallback)
            crushed = node.value_of("CrushedSequence")
            if crushed:
                add(node.value_of("Image"), crushed)
    has_muzzle_overlay = any(trait_type(k) == "WithMuzzleOverlay" for k in traits)
    if has_muzzle_overlay:
        for muzzle in armament_muzzles:
            add(None, muzzle)
    orientation = next((node for key, node in traits.items() if trait_type(key) in ("BodyOrientation", "ClassicFacingBodyOrientation")), None)
    quantized = orientation.value_of("QuantizedFacings") if orientation else None
    buildable = next((node for key, node in traits.items() if trait_type(key) == "Buildable"), None)
    tooltip = next((node for key, node in traits.items() if trait_type(key) == "Tooltip"), None)
    return ActorRecord(
        name=name,
        faction=faction,
        domain=domain,
        parent=parent,
        rules=rules,
        image=image.lower(),
        traits=traits,
        references=references,
        turrets=turrets,
        quantized_facings=int(quantized) if quantized else None,
        has_shadow_trait=any(trait_type(k) == "WithShadow" for k in traits),
        icon_palette=buildable.value_of("IconPalette", "chrome") if buildable else None,
        tooltip=tooltip.value_of("Name") if tooltip else None,
    )


DERIVED_KEYS = {
    "SpawnActorOnDeath": ("Actor",),
    "LeavesHusk": ("HuskActor",),
    "Transforms": ("IntoActor",),
    "CarrierParent": ("Actors",),
    "AirstrikePower": ("UnitType",),
    "ParatroopersPower": ("UnitType",),
}


def derived_actors(rules: list[YamlNode]) -> list[str]:
    result: list[str] = []
    for node in rules:
        kind = trait_type(node.key)
        for field in DERIVED_KEYS.get(kind, ()):
            for value in split_list(node.value_of(field)):
                if value.upper() not in (r.upper() for r in result):
                    result.append(value.upper() if "." not in value else value)
    return result


# ---------------------------------------------------------------------------
# Audit


@dataclasses.dataclass
class Finding:
    severity: str  # defect | warning | info
    code: str
    actor: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return dataclasses.asdict(self)


class Audit:
    def __init__(self, engine: Engine, factions: list[str], icon_provenance: str = "current") -> None:
        self.engine = engine
        self.icon_provenance = icon_provenance
        self.factions = factions
        self.catalog = self.load_catalog()
        self.actors: dict[str, ActorRecord] = {}
        self.natives: dict[str, ActorRecord] = {}
        self.sequences: dict[str, dict[str, SequenceSpec]] = {}
        self.files: dict[str, dict[str, Any]] = {}
        self.frame_cache: dict[str, list[np.ndarray]] = {}
        self.findings: list[Finding] = []
        self.results: dict[str, dict[str, Any]] = {}

    # -- inventory -------------------------------------------------------

    def load_catalog(self) -> dict[str, dict[str, Any]]:
        nodes = parse_miniyaml((self.engine.root / "mods/ra/experiences.yaml").read_text(encoding="utf-8-sig"))
        catalog = yaml_find(nodes, "ExperienceCatalog")
        components = catalog.get("Components") if catalog else None
        packs: dict[str, dict[str, Any]] = {}
        for faction, component_id in FACTION_PACKS.items():
            component = components.get(component_id) if components else None
            if component is None:
                raise SystemExit(f"Experience component {component_id} not found")
            faction_node = component.get("Faction")
            roster = faction_node.get("Roster") if faction_node else None
            sequence_files = split_list(component.value_of("Sequences"))
            for dependency in split_list(component.value_of("Dependencies")):
                dependency_node = components.get(dependency)
                if dependency_node is not None and (dependency_node.value_of("Kind") or "") == "Internal":
                    sequence_files += split_list(dependency_node.value_of("Sequences"))
            packs[faction] = {
                "component": component_id,
                "sequence_files": sequence_files,
                "title": component.value_of("Title"),
                "license": component.value_of("License"),
                "source": component.value_of("Source"),
                "preview": faction_node.value_of("Preview") if faction_node else None,
                "roster": {child.key: split_list(child.value) for child in roster.nodes} if roster else {},
            }
        return packs

    def stock_actor_names(self) -> set[str]:
        """Actor keys defined by the base manifest rules (native Red Alert content)."""

        manifest = parse_miniyaml((self.engine.root / "mods/ra/mod.yaml").read_text(encoding="utf-8-sig"))
        rules = yaml_find(manifest, "Rules")
        names: set[str] = set()
        for node in rules.nodes if rules else []:
            path = node.key.split("|", 1)[1] if "|" in node.key else node.key
            if "experiences/" in path:
                continue
            file = self.engine.root / "mods" / "ra" / path
            if not file.is_file():
                continue
            for top in parse_miniyaml(file.read_text(encoding="utf-8-sig")):
                if not top.key.startswith(("^", "-")):
                    names.add(top.key.upper())
        return names

    def resolve_rules(self, name: str) -> tuple[str, list[YamlNode]] | None:
        for candidate in rules_key_candidates(name):
            rules = self.engine.resolved("rules", candidate)
            if rules is not None:
                return candidate, rules
        return None

    def inventory(self, jobs: int) -> None:
        self.stock = self.stock_actor_names()
        queue: list[tuple[str, str, str, str | None]] = []
        for faction in self.factions:
            for domain, actors in self.catalog[faction]["roster"].items():
                for actor in actors:
                    queue.append((actor, faction, domain, None))
        seen: dict[str, str] = {}
        while queue:
            batch = []
            for item in queue:
                if item[0].upper() in seen:
                    existing = seen[item[0].upper()]
                    if existing in self.actors and item[1] not in self.actors[existing].faction.split(","):
                        self.actors[existing].faction += f",{item[1]}"
                    continue
                seen[item[0].upper()] = item[0]
                batch.append(item)
            queue = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
                resolved = list(pool.map(lambda item: self.resolve_rules(item[0]), batch))
            for (name, faction, domain, parent), found in zip(batch, resolved):
                if found is None:
                    self.findings.append(Finding("defect", "actor-missing", name, "resolved rules not found"))
                    continue
                key, rule = found
                seen[name.upper()] = key
                record = actor_record(key, faction, domain, parent, rule)
                record.stock = key.upper() in self.stock
                self.actors[key] = record
                if record.stock:
                    continue
                for derived in derived_actors(rule):
                    if derived.upper() not in seen and derived.upper() not in self.stock:
                        queue.append((derived, faction, domain, key))
        natives = sorted({ROLE_PAIRS[a] for a in self.actors if a in ROLE_PAIRS})
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            native_rules = list(pool.map(lambda n: self.engine.resolved("rules", n), natives))
        for name, rule in zip(natives, native_rules):
            if rule is not None:
                record = actor_record(name, "native", "reference", None, rule)
                record.stock = True
                self.natives[name] = record
        actor_images = {img for record in self.actors.values() for img in [record.image, *record.references]}
        for faction in self.factions:
            for reference in self.catalog[faction]["sequence_files"]:
                path = self.engine.root / "mods" / "ra" / (reference.split("|", 1)[1] if "|" in reference else reference)
                if not path.is_file():
                    continue
                for top in parse_miniyaml(path.read_text(encoding="utf-8-sig")):
                    image = top.key.lower()
                    if top.key.startswith(("^", "-")) or image in actor_images:
                        continue
                    name = f"effect:{image}"
                    if name in self.actors:
                        if faction not in self.actors[name].faction.split(","):
                            self.actors[name].faction += f",{faction}"
                        continue
                    record = ActorRecord(name=name, faction=faction, domain="Effects", parent=None, rules=[], image=image,
                                         traits={}, references={image: {n.key for n in top.nodes if n.key not in ("Defaults", "Inherits")}},
                                         turrets={}, quantized_facings=None, has_shadow_trait=False, icon_palette=None, tooltip=None)
                    self.actors[name] = record
        images = sorted({img for record in [*self.actors.values(), *self.natives.values()] for img in [record.image, *record.references]})
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            trees = list(pool.map(lambda image: self.engine.resolved("sequences", image), images))
        for image, tree in zip(images, trees):
            if tree is not None:
                self.sequences[image] = parse_sequences(image, tree)
        filenames = sorted({spec.filename_for(t) for seqs in self.sequences.values() for spec in seqs.values()
                            for t in TILESETS if spec.filename_for(t)})
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            decoded = list(pool.map(self._decode_safe, filenames))
        for filename, result in zip(filenames, decoded):
            if result is None:
                continue
            frames, info = result
            self.frame_cache[filename] = frames
            self.files[filename] = info

    def _decode_safe(self, filename: str):
        try:
            return self.engine.frames(filename)
        except (FileNotFoundError, RuntimeError) as error:
            self.findings.append(Finding("defect", "sprite-unreadable", filename, str(error)[:300]))
            return None

    # -- helpers -----------------------------------------------------------

    def sequence(self, image: str, name: str) -> SequenceSpec | None:
        return self.sequences.get(image, {}).get(name)

    def sequence_frames(self, spec: SequenceSpec, tileset: str = "TEMPERAT") -> list[list[np.ndarray]] | None:
        filename = spec.filename_for(tileset)
        if not filename or filename not in self.frame_cache:
            return None
        frames = self.frame_cache[filename]
        groups = spec.frame_indices(len(frames))
        result = []
        for group in groups:
            if any(index < 0 or index >= len(frames) for index in group):
                return None
            result.append([frames[index] for index in group])
        return result

    def add(self, severity: str, code: str, actor: str, detail: str) -> None:
        self.findings.append(Finding(severity, code, actor, detail))

    # -- checks ------------------------------------------------------------

    def file_stats(self, filename: str) -> dict[str, Any]:
        frames = self.frame_cache[filename]
        info = dict(self.files[filename])
        shapes = sorted({frame.shape for frame in frames})
        stacked = np.concatenate([frame.ravel() for frame in frames]) if frames else np.zeros(0, dtype=np.uint8)
        histogram = np.bincount(stacked, minlength=256)
        opaque = int(histogram.sum() - histogram[TRANSPARENT_INDEX])
        solid = opaque - int(histogram[PLAYER_SHADOW_INDEX])
        remap = int(histogram[80:96].sum())
        info.update({
            "frames": len(frames),
            "canvas": [int(shapes[0][1]), int(shapes[0][0])] if len(shapes) == 1 else [[int(s[1]), int(s[0])] for s in shapes],
            "uniform_canvas": len(shapes) == 1,
            "empty_frames": int(sum(1 for frame in frames if not frame.any())),
            "opaque_share": round(opaque / max(1, stacked.size), 4),
            "shadow_pixels": int(histogram[PLAYER_SHADOW_INDEX]),
            "remap_share": round(remap / max(1, solid), 4),
            "water_cycle_pixels": int(histogram[96:103].sum()),
            "reserved_index_pixels": int(histogram[1] + histogram[3]),
            "light_rotator_pixels": int(histogram[LIGHT_ROTATOR_INDEX]),
            "distinct_indices": int((histogram > 0).sum()),
            "edge_touching_frames": int(sum(1 for frame in frames if frame.any() and (
                frame[0].any() or frame[-1].any() or frame[:, 0].any() or frame[:, -1].any()))),
        })
        return info

    def audit_sequence(self, record: ActorRecord, spec: SequenceSpec) -> dict[str, Any]:
        add = (lambda *args: None) if record.stock else self.add
        filename = spec.filename_for("TEMPERAT")
        result: dict[str, Any] = {
            "file": filename,
            "facings": spec.facings,
            "interpolated_facings": spec.interpolated_facings,
            "classic": spec.use_classic_facings,
            "start": spec.start,
            "length": spec.length,
        }
        if filename not in self.frame_cache:
            result["error"] = "sprite not decoded"
            add("defect", "sequence-sprite-missing", record.name, f"{spec.image}.{spec.name}: {filename}")
            return result
        frame_count = len(self.frame_cache[filename])
        groups = spec.frame_indices(frame_count)
        used = sorted({index for group in groups for index in group})
        result["frame_range"] = [used[0], used[-1]] if used else None
        result["file_frames"] = frame_count
        if used and (used[0] < 0 or used[-1] >= frame_count):
            add("defect", "frame-range", record.name,
                     f"{spec.image}.{spec.name} uses frames {used[0]}..{used[-1]} but {filename} has {frame_count}")
            result["error"] = "frame range"
            return result
        grouped = self.sequence_frames(spec)
        if grouped is None:
            return result
        firsts = [group[0] for group in grouped]
        result["empty_facings"] = int(sum(1 for frame in firsts if not solid_mask(frame).any()))
        if result["empty_facings"] and spec.name not in ("shadow",):
            add("warning", "empty-facing", record.name, f"{spec.image}.{spec.name}: {result['empty_facings']} empty facing frame(s)")
        if spec.facings > 1:
            unique = len({frame_digest(frame) for frame in firsts})
            result["unique_facings"] = unique
            if unique < spec.facings:
                add("defect", "duplicate-facings", record.name,
                         f"{spec.image}.{spec.name}: only {unique} unique frames for {spec.facings} facings")
            angles = [spec.facing_angle(i) for i in range(spec.facings)]
            masks = [solid_mask(frame) for frame in firsts]
            height, width = firsts[0].shape
            pivot = (width / 2, height / 2)
            result["handedness"] = handedness_scores([principal_axis(mask) for mask in masks], angles)
            result["pivot"] = pivot_fit([centroid(mask) for mask in masks], angles)
            result["hub"] = pivot_fit([hub(mask) for mask in masks], angles)
            hub_fit = result["hub"]
            if hub_fit and spec.name.endswith("turret") and max(hub_fit["orbit"]) > 3.0:
                add("defect", "turret-orbit", record.name,
                    f"{spec.image}.{spec.name}: turret mount orbits {max(hub_fit['orbit']):.1f} px around the canvas pivot as it turns "
                    "(the mount offset is baked into the frames instead of Turreted.Offset)")
            elif hub_fit and hub_fit["rms_wobble"] > 1.25 and spec.name in ("idle", "turret"):
                add("warning", "pivot-wobble", record.name,
                    f"{spec.image}.{spec.name}: silhouette centre wobbles {hub_fit['rms_wobble']:.2f} px RMS across facings")
            if spec.facings >= 8:
                result["front_landmark"] = front_landmark_scores(masks, angles, pivot)
            hand = result["handedness"]
            where = f"{spec.image}.{spec.name}"
            if record.domain != "Infantry" and hand.get("samples", 0) >= max(4, spec.facings // 2) and hand["mirrored"] is not None:
                if hand["mirrored"] >= 0.5 and hand["mirrored"] - hand["native"] >= 0.4:
                    add("defect", "mirrored-facings", record.name,
                        f"{where}: silhouette axes follow a clockwise ring (native {hand['native']}, mirrored {hand['mirrored']})")
                elif hand["native"] <= -0.6:
                    add("warning", "axis-perpendicular", record.name,
                        f"{where}: long axis is perpendicular to every facing (native {hand['native']}); confirm the part is wider than long")
            front = result.get("front_landmark") or {}
            if "muzzle" in spec.name or spec.name.endswith("turret"):
                if front.get("samples", 0) >= spec.facings // 2 and front.get("best_hypothesis") not in (None, "native")                         and front["median_error_degrees"] - min(front["mirrored_median_error_degrees"], front["flipped_median_error_degrees"],
                                                                 front["reversed_median_error_degrees"]) >= 45:
                    add("defect", "mirrored-facings", record.name,
                        f"{where}: the far end (barrel/flash) follows the {front['best_hypothesis']} ring "
                        f"(native error {front['median_error_degrees']} deg)")
            if spec.facings >= 16 and not spec.use_classic_facings and spec.interpolated_facings is None and spec.facings == 32 \
                    and record.domain in ("Vehicles",) and spec.name in ("idle", "turret"):
                add("warning", "non-classic-ground-facings", record.name,
                         f"{spec.image}.{spec.name}: 32 facings without UseClassicFacings")
        edge = sum(1 for group in grouped for frame in group if frame.any() and (
            frame[0].any() or frame[-1].any() or frame[:, 0].any() or frame[:, -1].any()))
        result["edge_touching_frames"] = edge
        return result

    def audit_actor(self, record: ActorRecord) -> dict[str, Any]:
        output: dict[str, Any] = {
            "faction": record.faction,
            "domain": record.domain,
            "parent": record.parent,
            "image": record.image,
            "tooltip": record.tooltip,
            "turrets": {k: list(v) for k, v in record.turrets.items()},
            "quantized_facings": record.quantized_facings,
            "shadow_trait": record.has_shadow_trait,
            "sequences": {},
            "unreferenced_sequences": [],
            "missing_sequences": [],
        }
        image_sequences = self.sequences.get(record.image)
        if image_sequences is None:
            if not record.stock:
                self.add("defect", "image-missing", record.name, f"sequence image {record.image} not found")
            return output
        origins = set()
        for image, names in sorted(record.references.items()):
            available = self.sequences.get(image, {})
            for name in sorted(names):
                if name not in available:
                    # Infantry death/idle variants and optional overlays are
                    # legitimately absent on some actors; report for review.
                    output["missing_sequences"].append(f"{image}.{name}")
        for name, spec in sorted(image_sequences.items()):
            filename = spec.filename_for("TEMPERAT")
            if filename in self.files:
                origins.add(self.files[filename]["origin"])
            output["sequences"][name] = self.audit_sequence(record, spec)
        referenced = record.references.get(record.image, set())
        damage_prefixed = {f"damaged-{name}" for name in referenced} | {f"critical-{name}" for name in referenced}
        for name in sorted(image_sequences):
            if name in referenced or name in damage_prefixed:
                continue
            if name.startswith(("die", "prone-", "idle", "stand", "run", "shoot", "liedown", "standup", "parachute", "garrison-")):
                continue
            output["unreferenced_sequences"].append(name)
        output["art_origin"] = sorted(origins)
        self.audit_layers(record, output)
        return output

    def audit_layers(self, record: ActorRecord, output: dict[str, Any]) -> None:
        body = self.sequence(record.image, "idle")
        if body is None:
            return
        frames = self.sequence_frames(body)
        if frames is None:
            return
        firsts = [group[0] for group in frames]
        solids = [solid_mask(frame) for frame in firsts]
        areas = [int(mask.sum()) for mask in solids]
        boxes = []
        for mask in solids:
            ys, xs = np.nonzero(mask)
            if len(xs):
                boxes.append((int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)))
        stacked = np.concatenate([frame.ravel() for frame in firsts])
        solid_pixels = int(np.isin(stacked, [TRANSPARENT_INDEX, PLAYER_SHADOW_INDEX], invert=True).sum())
        remap_values = stacked[(stacked >= 80) & (stacked <= 95)]
        per_facing = []
        for frame, mask in zip(firsts, solids):
            pixels = frame[mask]
            per_facing.append(float(((pixels >= 80) & (pixels <= 95)).sum()) / max(1, len(pixels)))
        palette = self.unit_palette()
        solid_values = stacked[np.isin(stacked, [TRANSPARENT_INDEX, PLAYER_SHADOW_INDEX], invert=True)]
        rgb = palette[solid_values][:, :3].astype(np.float32)
        luminance = float((0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2]).mean()) if len(rgb) else 0.0
        holes = [enclosed_holes(frame) / max(1, int(mask.sum())) for frame, mask in zip(firsts, solids)]
        aspects = [value for value in (planform_aspect(mask) for mask in solids) if value is not None]
        output["body"] = {
            "canvas": [int(firsts[0].shape[1]), int(firsts[0].shape[0])],
            "enclosed_hole_share_median": round(float(np.median(holes)), 3) if holes else None,
            "enclosed_hole_share_max": round(float(np.max(holes)), 3) if holes else None,
            "planform_aspect_median": round(float(np.median(aspects)), 3) if aspects else None,
            "mean_visible_area": round(float(np.mean(areas)), 1),
            "max_visible_extent": [max((b[0] for b in boxes), default=0), max((b[1] for b in boxes), default=0)],
            "remap_share": round(int(((stacked >= 80) & (stacked <= 95)).sum()) / max(1, solid_pixels), 4),
            "shadow_share": round(int((stacked == PLAYER_SHADOW_INDEX).sum()) / max(1, int((stacked != 0).sum())), 4),
            "water_cycle_pixels": int(((stacked >= 96) & (stacked <= 102)).sum()),
            "light_rotator_pixels": int((stacked == LIGHT_ROTATOR_INDEX).sum()),
            "remap_ramp_mean": round(float((remap_values - 80).mean()), 2) if len(remap_values) else None,
            "remap_share_by_facing": [round(float(min(per_facing)), 3), round(float(max(per_facing)), 3)],
            "mean_luminance_blue_player": round(luminance, 1),
        }
        turret = self.sequence(record.image, "turret")
        if turret is not None and record.turrets:
            turret_frames = self.sequence_frames(turret)
            if turret_frames:
                offset = next(iter(record.turrets.values()))
                seat = []
                for facing, group in enumerate(frames):
                    angle = body.facing_angle(facing * body.facings // len(frames)) if body.facings else 0
                    dx, dy = turret_screen_offset(offset, angle)
                    seat.append([round(dx, 1), round(dy, 1)])
                output["turret_seat_offsets_px"] = seat
                turret_masks = [solid_mask(group[0]) for group in turret_frames]
                union = np.zeros_like(turret_masks[0])
                for mask in turret_masks:
                    union |= mask
                ys, xs = np.nonzero(union)
                if len(xs):
                    output["turret_union_extent"] = [int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]


    def unit_palette(self) -> np.ndarray:
        if not hasattr(self, "_unit_palette"):
            base = load_pal(self.engine.locate("temperat.pal")[0], transparent=(0,), shadow=(4,))
            self._unit_palette = player_palette(base, (59, 105, 229))
        return self._unit_palette

    def is_rotorcraft(self, record: ActorRecord) -> bool:
        return any(name in self.sequences.get(record.image, {}) for name in ("rotor", "slow-rotor")) or             any("ROTOR" in key.upper() for key in record.traits)

    def run_checks(self) -> None:
        for filename in sorted(self.frame_cache):
            stats = self.file_stats(filename)
            self.files[filename] = stats
        for name, record in sorted(self.actors.items()):
            self.results[name] = self.audit_actor(record)
        self.native_results = {name: self.audit_actor(record) for name, record in sorted(self.natives.items())}
        self.check_file_defects()
        self.check_remap_and_shadow()
        self.check_duplicates()
        self.check_icons()
        self.check_previews()
        self.check_scale()
        self.check_domain_completeness()

    def custom_files(self) -> set[str]:
        """Project-authored sprite files referenced by faction-specific actors."""

        referenced = set()
        for record in self.actors.values():
            if not record.stock:
                referenced |= self.files_for(record)
        return {f for f in referenced if self.files.get(f, {}).get("origin") == "project"}

    def files_for(self, record: ActorRecord) -> set[str]:
        result = set()
        for image in {record.image, *record.references}:
            for spec in self.sequences.get(image, {}).values():
                filename = spec.filename_for("TEMPERAT")
                if filename:
                    result.add(filename)
        return result

    def owner_of_file(self) -> dict[str, list[str]]:
        owners: dict[str, list[str]] = {}
        for name, record in self.actors.items():
            for filename in self.files_for(record):
                owners.setdefault(filename, []).append(name)
        return owners

    def check_file_defects(self) -> None:
        owners = self.owner_of_file()
        for filename in sorted(self.custom_files()):
            info = self.files[filename]
            actor = ",".join(sorted(owners.get(filename, ["?"])))
            if not info["uniform_canvas"]:
                self.add("defect", "canvas-not-uniform", actor, f"{filename}: frame canvases {info['canvas']}")
            if info["reserved_index_pixels"] and not filename.endswith(("icon.shp", "_icon.shp")):
                self.add("defect", "reserved-index", actor,
                         f"{filename}: {info['reserved_index_pixels']} px use index 1 (magenta) or 3 (shadow green)")
            if info["water_cycle_pixels"] and not filename.endswith(("icon.shp", "_icon.shp")):
                self.add("defect", "palette-cycling-index", actor,
                         f"{filename}: {info['water_cycle_pixels']} px use player-palette water-cycle indices 96-102")
            if info["light_rotator_pixels"]:
                self.add("warning", "light-rotator-index", actor,
                         f"{filename}: {info['light_rotator_pixels']} px use index 103 (blinks via LightPaletteRotator)")
            if info["empty_frames"] and info["empty_frames"] == info["frames"]:
                self.add("defect", "all-frames-empty", actor, filename)

    def check_remap_and_shadow(self) -> None:
        native_remaps = [r.get("body", {}).get("remap_share") for r in self.native_results.values() if r.get("body")]
        for name, result in self.results.items():
            record = self.actors[name]
            body = result.get("body")
            if not body or record.parent is not None or record.stock or record.domain == "Effects":
                continue
            share = body["remap_share"]
            ramp = body.get("remap_ramp_mean")
            if ramp is not None and share >= 0.08 and ramp >= 11.0:
                self.add("defect", "dark-remap-ramp", name,
                         f"player colour uses only the darkest remap shades (mean ramp position {ramp:.1f}/15; native units 4.5-9.8) "
                         f"so ownership reads as near-black (body luminance {body['mean_luminance_blue_player']})")
            low, high = body.get("remap_share_by_facing", [0, 0])
            if high >= 0.15 and low < high * 0.35:
                self.add("defect", "remap-flicker", name,
                         f"player-colour share swings from {low:.0%} to {high:.0%} between facings, so ownership colour appears and vanishes while turning")
            if share < 0.03:
                self.add("defect", "no-player-colour", name, f"only {share:.1%} of body pixels use remap indices 80-95")
            elif share < 0.08:
                self.add("warning", "weak-player-colour", name, f"{share:.1%} of body pixels use remap indices")
            elif share > 0.70:
                self.add("warning", "remap-dominates", name, f"{share:.1%} of body pixels are player colour; material/equipment colour may be erased")
            if (body.get("enclosed_hole_share_max") or 0) > 0.15:
                self.add("defect", "see-through-geometry", name,
                         f"up to {body['enclosed_hole_share_max']:.0%} of the silhouette is transparent pixels enclosed by artwork "
                         "(back-face-culled hull/deck polygons render as an open frame)")
            if record.domain == "Aircraft" and (body.get("planform_aspect_median") or 1) < 0.3 and not self.is_rotorcraft(record):
                self.add("defect", "missing-planform", name,
                         f"fixed-wing silhouette is a needle (median width/length {body['planform_aspect_median']:.2f}); "
                         "wing and tailplane polygons are not rendered")
            if record.domain in ("Vehicles", "Navy") and body["shadow_share"] == 0:
                self.add("warning", "no-baked-shadow", name, "body frames contain no shadow index (4) pixels")
            if record.domain == "Aircraft" and body["shadow_share"] > 0 and record.has_shadow_trait:
                self.add("warning", "double-shadow", name, "baked shadow pixels plus a WithShadow trait")
        result = {"native_body_remap_shares": native_remaps}
        self.summary_extra = result

    def check_duplicates(self) -> None:
        owners = self.owner_of_file()
        digests: dict[str, set[tuple[str, int]]] = {}
        masks: dict[str, set[tuple[str, int]]] = {}
        meaningful: dict[str, int] = {}
        for filename in self.custom_files():
            for index, frame in enumerate(self.frame_cache[filename]):
                mask = solid_mask(frame)
                pixels = int(mask.sum())
                # Skip tiny effect frames and fully opaque rectangles (icons),
                # whose silhouettes are identical by construction.
                if pixels < 60 or pixels >= mask.size * 0.95:
                    continue
                meaningful[filename] = meaningful.get(filename, 0) + 1
                digests.setdefault(frame_digest(frame), set()).add((filename, index))
                masks.setdefault(mask_digest(frame), set()).add((filename, index))

        def pairs(groups: dict[str, set[tuple[str, int]]]) -> dict[tuple[str, str], int]:
            result: dict[tuple[str, str], int] = {}
            for entries in groups.values():
                files = sorted({f for f, _ in entries})
                for i, a in enumerate(files):
                    for b in files[i + 1:]:
                        result[(a, b)] = result.get((a, b), 0) + 1
            return result

        exact_pairs = pairs(digests)
        mask_pairs = pairs(masks)
        self.duplicates = {"exact": [], "palette_only": [], "silhouette": []}
        for (a, b), count in sorted(exact_pairs.items()):
            actors_a, actors_b = owners.get(a, []), owners.get(b, [])
            share = count / max(1, min(meaningful.get(a, 1), meaningful.get(b, 1)))
            self.duplicates["exact"].append({"files": [a, b], "frames": count, "share": round(share, 3), "actors": [actors_a, actors_b]})
            if set(actors_a) != set(actors_b):
                severity = "defect" if share >= 0.25 else "info"
                self.add(severity, "shared-frames", ",".join(sorted(set(actors_a + actors_b))),
                         f"{a} and {b} share {count} identical frame(s) ({share:.0%} of the smaller file)")
        for (a, b), count in sorted(mask_pairs.items()):
            extra = count - exact_pairs.get((a, b), 0)
            if extra <= 0:
                continue
            actors_a, actors_b = owners.get(a, []), owners.get(b, [])
            share = extra / max(1, min(meaningful.get(a, 1), meaningful.get(b, 1)))
            self.duplicates["palette_only"].append({"files": [a, b], "frames": extra, "share": round(share, 3), "actors": [actors_a, actors_b]})
            if set(actors_a) != set(actors_b):
                severity = "defect" if share >= 0.25 else "info"
                self.add(severity, "palette-only-duplicate", ",".join(sorted(set(actors_a + actors_b))),
                         f"{a} and {b} share {extra} frame silhouette(s) with different colours ({share:.0%} of the smaller file)")
        # Silhouette similarity of body rings across actors (and against natives).
        bodies = {}
        for name, record in [*self.actors.items(), *(("native:" + n, r) for n, r in self.natives.items())]:
            if record.parent is not None or record.domain == "Effects":
                continue
            spec = self.sequence(record.image, "idle")
            if spec is None or spec.facings < 8:
                continue
            frames = self.sequence_frames(spec)
            if not frames:
                continue
            step = spec.facings // 8
            bodies[name] = [frames[i * step][0] for i in range(8)]
        names = sorted(bodies)
        self.duplicates["native_calibration"] = []
        parents = {name: record.parent for name, record in self.actors.items()}
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                score = float(np.mean([mask_iou(solid_mask(x), solid_mask(y)) for x, y in zip(bodies[a], bodies[b])]))
                if a.startswith("native:") and b.startswith("native:"):
                    self.duplicates["native_calibration"].append({"actors": [a, b], "mean_iou": round(score, 3)})
                    continue
                if parents.get(a) == b or parents.get(b) == a:
                    continue
                if score >= 0.88:
                    self.duplicates["silhouette"].append({"actors": [a, b], "mean_iou": round(score, 3)})
                    self.add("warning", "silhouette-near-duplicate", f"{a},{b}",
                             f"eight-facing silhouettes overlap {score:.0%}")

    def icon_for(self, record: ActorRecord) -> tuple[str, np.ndarray] | None:
        spec = self.sequence(record.image, "icon")
        if spec is None:
            return None
        frames = self.sequence_frames(spec)
        if not frames:
            return None
        return spec.filename_for("TEMPERAT"), frames[0][0]

    def check_icons(self) -> None:
        self.icons: dict[str, dict[str, Any]] = {}
        hashes: dict[str, list[str]] = {}
        for name, record in sorted(self.actors.items()):
            if record.parent is not None:
                continue
            if not any(trait_type(k) == "Buildable" for k in record.traits):
                continue
            if record.stock:
                icon = self.icon_for(record)
                if icon is not None:
                    self.icons[name] = {"file": icon[0], "origin": self.files.get(icon[0], {}).get("origin"), "stock_actor": True}
                continue
            icon = self.icon_for(record)
            if icon is None:
                self.add("defect", "icon-missing", name, f"no {record.image}.icon sequence")
                continue
            filename, frame = icon
            info = self.files.get(filename, {})
            height, width = frame.shape
            transparent = int((frame == TRANSPARENT_INDEX).sum())
            detail = {
                "file": filename,
                "origin": info.get("origin"),
                "size": [width, height],
                "transparent_pixels": transparent,
                "distinct_indices": int(len(np.unique(frame))),
                "remap_pixels": int(((frame >= 80) & (frame <= 95)).sum()),
                "palette": record.icon_palette,
            }
            hashes.setdefault(frame_digest(frame), []).append(name)
            if (width, height) != (64, 48):
                self.add("defect", "icon-size", name, f"{filename} is {width}x{height}, expected 64x48")
            if info.get("origin") != "project":
                self.add("warning", "icon-native", name, f"{filename} is a native Red Alert icon")
            if transparent > width * height * 0.05:
                self.add("warning", "icon-transparent", name, f"{filename}: {transparent} transparent px (native icons are opaque)")
            # Informational only: silhouette overlap cannot separate an enlarged
            # world frame from a painted cameo of the same vehicle reliably, so
            # icon provenance is also recorded from the generators themselves
            # (see ICON_PROVENANCE).
            detail["world_frame_similarity"] = self.icon_world_similarity(record, frame)
            provenance = (PRE_FIX_ICON_PROVENANCE.get(filename) if self.icon_provenance == "before" else None)                 or ICON_PROVENANCE.get(filename)
            detail["provenance"] = provenance
            if provenance and provenance.startswith("world-frame"):
                self.add("defect", "icon-scaled-world-frame", name, f"{filename}: {provenance}")
            if detail["distinct_indices"] < 45:
                self.add("warning", "icon-low-detail", name,
                         f"{filename} uses only {detail['distinct_indices']} palette entries (flat placeholder-style cameo)")
            self.icons[name] = detail
        for digest, names in hashes.items():
            if len(names) > 1:
                self.add("defect", "icon-duplicate", ",".join(names), "identical production icons")

    def world_silhouettes(self, record: ActorRecord) -> list[np.ndarray]:
        """Body (plus aligned turret) silhouettes for every world facing."""

        spec = self.sequence(record.image, "idle")
        if spec is None:
            return []
        frames = self.sequence_frames(spec)
        if not frames:
            return []
        turret = self.sequence(record.image, "turret")
        turret_frames = self.sequence_frames(turret) if turret is not None and record.turrets else None
        result = []
        for index, group in enumerate(frames):
            mask = solid_mask(group[0])
            if turret_frames and len(turret_frames) == len(frames) and turret_frames[index][0].shape == mask.shape:
                mask = mask | solid_mask(turret_frames[index][0])
            if mask.sum() >= 20:
                result.append(mask)
        return result

    @staticmethod
    def icon_subject_mask(icon: np.ndarray, palette: np.ndarray) -> np.ndarray:
        """Pixels of the art panel that differ from the per-row backdrop colour."""

        rgb = palette[icon[:34]][:, :, :3].astype(np.float32)
        backdrop = np.median(rgb, axis=1, keepdims=True)
        return np.abs(rgb - backdrop).sum(axis=2) > 36

    def icon_world_similarity(self, record: ActorRecord, icon: np.ndarray) -> float | None:
        """Best silhouette overlap between the icon subject and a scaled world frame.

        A cameo produced by cropping and enlarging an in-game frame keeps that
        frame's exact silhouette; an authored portrait (painted, or a dedicated
        render from a camera the world sprites never use) does not.
        """

        silhouettes = self.world_silhouettes(record)
        if not silhouettes:
            return None
        palette = load_pal(self.engine.locate("temperat.pal")[0])
        subject = self.icon_subject_mask(icon, palette)
        ys, xs = np.nonzero(subject)
        if len(xs) < 30:
            return None
        box = subject[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]
        best = 0.0
        for mask in silhouettes:
            my, mx = np.nonzero(mask)
            crop = mask[my.min(): my.max() + 1, mx.min(): mx.max() + 1]
            scaled = np.array(Image.fromarray((crop * 255).astype(np.uint8)).resize((box.shape[1], box.shape[0]), Image.NEAREST)) > 127
            union = np.logical_or(scaled, box).sum()
            if union:
                best = max(best, float(np.logical_and(scaled, box).sum() / union))
        return round(best, 3)

    def check_previews(self) -> None:
        self.previews: dict[str, dict[str, Any]] = {}
        digests: dict[str, list[str]] = {}
        for faction in self.factions:
            pack = self.catalog[faction]
            preview = pack["preview"]
            if not preview:
                self.add("defect", "preview-missing", faction, "no Faction.Preview declared")
                continue
            relative = preview.split("|", 1)[1] if "|" in preview else preview
            path = self.engine.root / "mods" / "ra" / relative
            if not path.is_file():
                self.add("defect", "preview-missing", faction, f"{preview} not found")
                continue
            data = path.read_bytes()
            image = Image.open(path)
            digest = hashlib.sha256(data).hexdigest()
            digests.setdefault(digest, []).append(faction)
            self.previews[faction] = {
                "path": str(path.relative_to(self.engine.root)).replace("\\", "/"),
                "sha256": digest,
                "size": list(image.size),
                "mode": image.mode,
                "license": pack["license"],
                "source": pack["source"],
            }
            if "original" not in (pack["license"] or "").lower():
                self.add("warning", "preview-license", faction, f"license text does not declare original art: {pack['license']}")
        for names in digests.values():
            if len(names) > 1:
                self.add("defect", "preview-duplicate", ",".join(names), "identical faction previews")

    def check_scale(self) -> None:
        self.scale: dict[str, dict[str, Any]] = {}
        for name, record in sorted(self.actors.items()):
            reference = ROLE_PAIRS.get(name)
            if record.parent is not None or record.stock or reference is None or reference not in self.native_results:
                continue
            ours = self.results[name].get("body")
            theirs = self.native_results[reference].get("body")
            if not ours or not theirs:
                continue
            ratio = ours["mean_visible_area"] / max(1.0, theirs["mean_visible_area"])
            length = max(ours["max_visible_extent"]) / max(1, max(theirs["max_visible_extent"]))
            self.scale[name] = {"reference": reference, "area_ratio": round(ratio, 2), "extent_ratio": round(length, 2)}
            if record.domain in ("Vehicles", "Aircraft", "Navy") and (length > 2.0 or length < 0.6):
                self.add("warning", "scale-outlier", name, f"visible extent {length:.2f}x the native {reference}")

    def check_domain_completeness(self) -> None:
        for name, record in sorted(self.actors.items()):
            if record.parent is not None:
                continue
            if record.stock:
                faction_images = next((node for key, node in record.traits.items() if trait_type(key) == "RenderSprites"), None)
                self.add("info", "stock-art", name,
                         f"shared stock actor rendered with native image {record.image}; no faction-specific art")
                continue
            sequences = self.sequences.get(record.image, {})
            traits = {trait_type(k) for k in record.traits}
            if record.domain in ("Vehicles", "Aircraft", "Navy"):
                derived = [a for a in self.actors.values() if a.parent == name]
                in_image = [key for key in sequences if key.startswith(("sink", "die", "dead", "destroyed"))]
                if not derived and not in_image:
                    self.add("warning", "no-death-art", name, "no husk/sinking actor with its own image")
            if record.domain in ("Buildings", "Defenses"):
                if "Building" in traits and "make" not in sequences and "WithMakeAnimation" in traits:
                    self.add("defect", "make-missing", name, "WithMakeAnimation without make sequence")
                if not any(key.startswith("damaged-") for key in sequences):
                    self.add("warning", "no-damaged-state", name, "no damaged-* sequence")

    # -- output ------------------------------------------------------------

    def report(self) -> dict[str, Any]:
        per_faction: dict[str, dict[str, Any]] = {}
        for faction in self.factions:
            table: dict[str, Any] = {}
            for domain, actors in self.catalog[faction]["roster"].items():
                entries = []
                for actor in actors:
                    findings = [f.as_dict() for f in self.findings if actor in f.actor.split(",")]
                    entries.append({
                        "actor": actor,
                        "art_origin": self.results.get(actor, {}).get("art_origin"),
                        "defects": sum(1 for f in findings if f["severity"] == "defect"),
                        "warnings": sum(1 for f in findings if f["severity"] == "warning"),
                    })
                table[domain] = entries
            per_faction[faction] = table
        return {
            "engine_root": str(self.engine.root),
            "profile": self.engine.profile,
            "factions": self.factions,
            "catalog": self.catalog,
            "per_faction": per_faction,
            "actors": self.results,
            "native_references": self.native_results,
            "files": self.files,
            "icons": getattr(self, "icons", {}),
            "previews": getattr(self, "previews", {}),
            "scale": getattr(self, "scale", {}),
            "duplicates": getattr(self, "duplicates", {}),
            "summary_extra": getattr(self, "summary_extra", {}),
            "findings": [f.as_dict() for f in self.findings],
            "counts": {
                severity: sum(1 for f in self.findings if f.severity == severity)
                for severity in ("defect", "warning", "info")
            },
        }


def markdown_summary(report: dict[str, Any]) -> str:
    lines = ["# Modern faction art audit", "", f"Profile: `{report['profile']}`", ""]
    lines.append(f"Findings: {report['counts']['defect']} defect(s), {report['counts']['warning']} warning(s), {report['counts']['info']} info.")
    lines.append("")
    for faction, table in report["per_faction"].items():
        lines.append(f"## {faction}")
        lines.append("")
        lines.append("| Domain | Actor | Art | Defects | Warnings |")
        lines.append("| --- | --- | --- | --- | --- |")
        for domain, entries in table.items():
            for entry in entries:
                origin = ",".join(entry["art_origin"] or [])
                lines.append(f"| {domain} | `{entry['actor']}` | {origin} | {entry['defects']} | {entry['warnings']} |")
        lines.append("")
    lines.append("## Findings")
    lines.append("")
    for finding in sorted(report["findings"], key=lambda f: ({"defect": 0, "warning": 1, "info": 2}[f["severity"]], f["code"], f["actor"])):
        lines.append(f"- **{finding['severity']}** `{finding['code']}` {finding['actor']}: {finding['detail']}")
    return "\n".join(lines) + "\n"


def default_content_dir() -> Path | None:
    appdata = os.environ.get("APPDATA")
    candidates = []
    if appdata:
        candidates.append(Path(appdata) / "OpenRA" / "Content" / "ra" / "v2")
    candidates.append(Path.home() / ".config" / "openra" / "Content" / "ra" / "v2")
    candidates.append(Path.home() / "Library" / "Application Support" / "OpenRA" / "Content" / "ra" / "v2")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--engine", type=Path, default=ROOT / "engine" / "openra", help="OpenRA engine checkout with a built bin/")
    parser.add_argument("--output", type=Path, required=True, help="artifact directory (not committed)")
    parser.add_argument("--content", type=Path, default=None,
                        help="Red Alert content directory copied read-only into the disposable support dir")
    parser.add_argument("--factions", nargs="+", default=list(FACTION_PACKS), choices=list(FACTION_PACKS))
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--sheets", action="store_true", help="render contact sheets")
    parser.add_argument("--fail-on-defects", action="store_true")
    parser.add_argument("--icon-provenance", choices=("current", "before"), default="current",
                        help="icon generator provenance to apply (use 'before' for a checkout older than the 2026-09 fixes)")
    args = parser.parse_args(argv)

    content = args.content or default_content_dir()
    engine = Engine(args.engine, args.output, content)
    audit = Audit(engine, args.factions, args.icon_provenance)
    audit.inventory(args.jobs)
    audit.run_checks()
    report = audit.report()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "audit-report.json").write_text(json.dumps(report, indent=2, default=list), encoding="utf-8")
    (args.output / "audit-summary.md").write_text(markdown_summary(report), encoding="utf-8")
    if args.sheets:
        from modern_faction_art_sheets import render_all

        render_all(audit, args.output / "sheets")
    print(f"audited {len(audit.actors)} actors, {len(audit.files)} sprite files: "
          f"{report['counts']['defect']} defect(s), {report['counts']['warning']} warning(s)")
    return 1 if args.fail_on_defects and report["counts"]["defect"] else 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
