"""Deterministic fixed-camera directional models for the China faction.

Ground vehicles render at the exact classic Red Alert yaw samples with hull
and turret as independent meshes. Planes and ships render authored 16-view
geometry; helicopters render 32 classic views with a separate rotor package.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from red_sea_directional_vehicle import Mesh, _angles, _render


GREEN = (91, 107, 66)
GREEN_LIGHT = (128, 139, 88)
GREEN_DARK = (49, 61, 42)
SLATE = (70, 79, 77)
SLATE_LIGHT = (111, 122, 117)
SLATE_DARK = (38, 45, 45)
TRACK = (35, 37, 33)
RUBBER = (29, 31, 30)
STEEL = (78, 82, 74)
GLASS = (30, 58, 63)
RED = (163, 44, 37)
LAMP = (233, 207, 120)
DECK = (82, 91, 88)
SEA_DARK = (47, 57, 60)


def _tracked_base(length: float, width: float, wheels: int, *, low: bool = False) -> Mesh:
    mesh = Mesh()
    height = 0.58 if low else 0.72
    for x0, x1 in ((-width / 2, -width / 2 + 0.36), (width / 2 - 0.36, width / 2)):
        mesh.box(x0, x1, -length / 2, length / 2, 0.08, height, TRACK)
    for index in range(wheels):
        y = -length * 0.39 + index * length * 0.78 / max(1, wheels - 1)
        mesh.cylinder_x((0, y, 0.34), width + 0.10, 0.27, RUBBER, segments=8)
        mesh.cylinder_x((0, y, 0.34), width + 0.15, 0.11, GREEN_DARK, segments=8)
    for y in tuple(-length / 2 + 0.12 + index * 0.26 for index in range(round(length / 0.26))):
        mesh.box(-width / 2 - 0.02, -width / 2 + 0.38, y, min(length / 2, y + 0.09), height - 0.05, height + 0.05, STEEL, outline=False)
        mesh.box(width / 2 - 0.38, width / 2 + 0.02, y, min(length / 2, y + 0.09), height - 0.05, height + 0.05, STEEL, outline=False)
    return mesh


def _qilin_hull() -> Mesh:
    mesh = _tracked_base(3.75, 2.62, 6)
    mesh.box(-1.00, 1.00, -1.72, 1.62, 0.52, 0.80, GREEN_DARK)
    mesh.tapered_box((-1.05, 1.05, -1.66, 1.55, 0.73), (-0.86, 0.86, -1.30, 1.34, 1.10), GREEN)
    mesh.box(-0.72, 0.72, 0.62, 1.44, 1.05, 1.15, SLATE_DARK)
    for x in (-0.66, -0.22, 0.22):
        mesh.box(x, x + 0.17, 0.74, 1.32, 1.14, 1.19, SLATE, outline=False)
    for x in (-0.70, 0.55):
        mesh.box(x, x + 0.15, -1.74, -1.60, 0.79, 0.91, LAMP, outline=False)
    mesh.box(-1.31, -1.08, -1.35, 1.28, 0.60, 0.92, GREEN)
    mesh.box(1.08, 1.31, -1.35, 1.28, 0.60, 0.92, GREEN)
    return mesh


def _qilin_turret() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, 0.05, 1.18), 0.12, 0.72, GREEN_DARK, segments=10)
    mesh.tapered_box((-0.86, 0.86, -0.88, 0.88, 1.17), (-0.64, 0.64, -0.76, 0.72, 1.60), GREEN)
    mesh.box(-0.70, 0.70, 0.54, 1.12, 1.28, 1.52, GREEN_DARK)
    mesh.cylinder_z((-0.31, 0.05, 1.67), 0.12, 0.22, GREEN_DARK, segments=8)
    mesh.box(0.18, 0.42, -0.38, -0.12, 1.58, 1.75, GLASS)
    mesh.box(-0.23, 0.23, -1.18, -0.78, 1.38, 1.63, GREEN_DARK)
    mesh.cylinder_y((0, -1.78, 1.53), 1.32, 0.085, SLATE_LIGHT, segments=10)
    mesh.cylinder_y((0, -2.50, 1.53), 0.18, 0.12, SLATE_DARK, segments=8)
    mesh.cylinder_y((0, -2.86, 1.53), 0.56, 0.065, STEEL, segments=8)
    for x in (-0.82, 0.72):
        for y in (-0.38, -0.12, 0.14):
            mesh.cylinder_y((x, y, 1.43), 0.16, 0.055, SLATE_DARK, segments=6)
    return mesh


def _lynx_hull() -> Mesh:
    mesh = _tracked_base(2.20, 1.62, 4, low=True)
    mesh.tapered_box((-0.63, 0.63, -0.96, 0.96, 0.48), (-0.50, 0.50, -0.72, 0.75, 0.85), GREEN)
    mesh.box(-0.44, 0.44, 0.50, 0.88, 0.81, 0.91, SLATE_DARK)
    mesh.box(-0.28, 0.28, -0.82, -0.70, 0.70, 0.81, GLASS)
    for x in (-0.46, 0.34):
        mesh.box(x, x + 0.11, -1.00, -0.90, 0.55, 0.66, RED, outline=False)
    return mesh


def _lynx_turret() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, -0.02, 0.90), 0.10, 0.34, GREEN_DARK, segments=8)
    mesh.box(-0.34, 0.34, -0.40, 0.40, 0.91, 1.16, GREEN)
    mesh.cylinder_y((0, -0.73, 1.08), 0.78, 0.055, STEEL, segments=8)
    mesh.box(-0.11, 0.11, 0.23, 0.44, 1.15, 1.48, SLATE_DARK)
    mesh.box(-0.07, 0.07, 0.18, 0.28, 1.34, 1.43, GLASS, outline=False)
    return mesh


def _mantis_hull() -> Mesh:
    mesh = _tracked_base(3.05, 2.18, 5)
    mesh.tapered_box((-0.86, 0.86, -1.34, 1.30, 0.62), (-0.68, 0.68, -1.10, 1.08, 1.04), GREEN)
    mesh.box(-0.52, 0.52, 0.55, 1.20, 1.00, 1.15, SLATE_DARK)
    mesh.box(-0.42, 0.42, -1.23, -1.10, 0.78, 0.96, GLASS)
    for x in (-0.69, 0.56):
        mesh.box(x, x + 0.13, -1.43, -1.31, 0.73, 0.88, LAMP, outline=False)
    return mesh


def _mantis_turret() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, 0.02, 1.18), 0.12, 0.48, GREEN_DARK, segments=10)
    mesh.box(-0.58, 0.58, -0.50, 0.54, 1.18, 1.48, GREEN)
    for x in (-0.72, 0.48):
        mesh.box(x, x + 0.24, -0.62, 0.34, 1.30, 1.63, SLATE_DARK)
        for y in (-0.48, -0.12):
            mesh.cylinder_y((x + 0.12, y, 1.48), 0.55, 0.08, STEEL, segments=8)
            mesh.cylinder_y((x + 0.12, y - 0.31, 1.48), 0.10, 0.10, RED, segments=8)
    mesh.cylinder_z((0, 0.32, 1.52), 0.08, 0.12, STEEL, segments=8)
    mesh.box(-0.34, 0.34, 0.25, 0.37, 1.60, 1.92, SLATE)
    mesh.box(-0.27, 0.27, 0.22, 0.40, 1.92, 2.03, GLASS)
    return mesh


def _zbd_hull() -> Mesh:
    mesh = _tracked_base(3.55, 2.42, 6)
    mesh.box(-0.96, 0.96, -1.58, 1.53, 0.50, 0.78, GREEN_DARK)
    mesh.tapered_box((-1.04, 1.04, -1.52, 1.46, 0.72), (-0.78, 0.78, -1.24, 1.22, 1.24), GREEN)
    # Hydrodynamic bow and rear troop ramp.
    mesh.polygon(((-1.04, -1.52, 0.72), (1.04, -1.52, 0.72), (0.76, -1.91, 0.56), (-0.76, -1.91, 0.56)), GREEN_LIGHT)
    mesh.box(-0.62, 0.62, 1.23, 1.50, 0.70, 1.10, GREEN_DARK)
    mesh.box(-0.68, 0.68, 1.47, 1.55, 0.78, 1.04, SLATE_DARK)
    for x in (-0.78, 0.62):
        mesh.box(x, x + 0.16, -1.75, -1.62, 0.70, 0.84, LAMP, outline=False)
    return mesh


def _zbd_turret() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, -0.05, 1.29), 0.10, 0.52, GREEN_DARK, segments=8)
    mesh.tapered_box((-0.60, 0.60, -0.60, 0.58, 1.27), (-0.43, 0.43, -0.51, 0.46, 1.65), GREEN)
    mesh.cylinder_y((0, -1.00, 1.51), 1.18, 0.065, STEEL, segments=8)
    for x in (-0.62, 0.52):
        mesh.cylinder_y((x, -0.36, 1.58), 0.72, 0.085, GREEN_DARK, segments=8)
        mesh.cylinder_y((x, -0.74, 1.58), 0.09, 0.10, RED, segments=8)
    mesh.box(0.14, 0.35, 0.10, 0.35, 1.62, 1.78, GLASS)
    return mesh


def _phl(*, loaded: bool) -> Mesh:
    mesh = Mesh()
    for y in (-1.35, -0.45, 0.45, 1.35):
        mesh.cylinder_x((0, y, 0.34), 2.28, 0.31, RUBBER, segments=10)
        mesh.cylinder_x((0, y, 0.34), 2.34, 0.13, GREEN_DARK, segments=8)
    mesh.box(-0.87, 0.87, -1.67, 1.68, 0.39, 0.62, GREEN_DARK)
    mesh.tapered_box((-0.85, 0.85, -1.61, -0.44, 0.56), (-0.70, 0.70, -1.41, -0.56, 1.24), GREEN)
    mesh.box(-0.54, 0.54, -1.47, -1.35, 0.84, 1.13, GLASS)
    mesh.box(-0.83, 0.83, -0.34, 1.56, 0.57, 0.78, GREEN)
    if loaded:
        mesh.slanted_box_y(-0.72, 0.72, -0.42, 1.45, 0.86, 1.34, 0.56, GREEN_DARK)
        for x in (-0.52, -0.17, 0.17, 0.52):
            for z in (1.04, 1.30, 1.56):
                mesh.cylinder_y((x, 0.50, z), 1.52, 0.105, SLATE_DARK, segments=8)
                mesh.cylinder_y((x, -0.28, z), 0.08, 0.12, RED, segments=8)
    else:
        mesh.slanted_box_y(-0.70, 0.70, -0.25, 1.44, 0.79, 1.15, 0.18, STEEL)
    return mesh


def _plane_mesh(*, drone: bool = False) -> Mesh:
    mesh = Mesh()
    if drone:
        mesh.polygon(((0, -2.05, 0.55), (2.22, 1.05, 0.48), (0.54, 0.72, 0.66), (0, 1.45, 0.74), (-0.54, 0.72, 0.66), (-2.22, 1.05, 0.48)), SLATE)
        mesh.tapered_box((-0.22, 0.22, -1.25, 1.25, 0.46), (-0.12, 0.12, -0.95, 0.98, 0.82), SLATE_LIGHT)
        mesh.box(-0.16, 0.16, 0.46, 0.72, 0.78, 0.94, GLASS)
        mesh.box(-0.06, 0.06, 1.32, 1.72, 0.61, 1.04, SLATE_DARK)
    else:
        mesh.tapered_box((-0.36, 0.36, -2.25, 1.76, 0.35), (-0.20, 0.20, -1.82, 1.38, 0.82), SLATE)
        mesh.polygon(((0, -0.62, 0.58), (2.15, 1.15, 0.40), (0.64, 0.86, 0.62), (0, 1.48, 0.66), (-0.64, 0.86, 0.62), (-2.15, 1.15, 0.40)), SLATE_DARK)
        mesh.tapered_box((-0.26, 0.26, -1.28, -0.34, 0.70), (-0.18, 0.18, -1.14, -0.46, 1.04), GLASS)
        for x in (-0.62, 0.62):
            mesh.polygon(((x - 0.08, 0.82, 0.60), (x + 0.08, 0.82, 0.60), (x * 1.18, 1.58, 1.42), (x * 0.92, 1.38, 1.42)), SLATE)
        for x in (-1.18, 1.18):
            mesh.cylinder_y((x, 0.36, 0.39), 1.08, 0.09, STEEL, segments=8)
            mesh.cylinder_y((x, -0.22, 0.39), 0.10, 0.11, RED, segments=8)
    return mesh


def _crane() -> Mesh:
    mesh = Mesh()
    mesh.tapered_box((-0.48, 0.48, -1.95, 1.72, 0.42), (-0.31, 0.31, -1.58, 1.39, 0.96), GREEN)
    mesh.tapered_box((-0.41, 0.41, -1.62, -0.45, 0.76), (-0.24, 0.24, -1.46, -0.58, 1.26), GLASS)
    mesh.box(-0.46, 0.46, -0.42, 0.82, 0.79, 1.14, GREEN_LIGHT)
    mesh.box(-0.22, 0.22, 1.48, 2.62, 0.58, 0.78, GREEN_DARK)
    mesh.polygon(((-0.12, 1.98, 0.72), (0.12, 1.98, 0.72), (0.10, 2.58, 1.62), (-0.10, 2.58, 1.62)), GREEN)
    for x in (-0.72, 0.72):
        mesh.box(x - 0.15, x + 0.15, -0.30, 0.82, 0.60, 0.78, GREEN_DARK)
        for y in (-0.18, 0.18, 0.54):
            mesh.cylinder_y((x, y, 0.68), 0.18, 0.07, SLATE_DARK, segments=8)
    mesh.cylinder_y((0, -1.92, 0.67), 0.72, 0.055, STEEL, segments=8)
    mesh.cylinder_z((0, 0.10, 1.25), 0.18, 0.18, STEEL, segments=8)
    return mesh


def _ship_hull(kind: str) -> Mesh:
    mesh = Mesh()
    assault = kind == "cnhaiwang"
    patrol = kind == "cnhaiying"
    landing = kind == "cnkunlun"
    submarine = kind == "cnjiaolong"
    if submarine:
        mesh.tapered_box((-0.66, 0.66, -2.70, 2.38, 0.08), (-0.38, 0.38, -2.38, 2.08, 0.76), SLATE_DARK)
        mesh.cylinder_y((0, -0.08, 0.43), 4.92, 0.52, SLATE, segments=12)
        mesh.tapered_box((-0.30, 0.30, -0.30, 0.70, 0.70), (-0.18, 0.18, -0.12, 0.48, 1.28), SLATE_DARK)
        mesh.box(-0.06, 0.06, -0.02, 0.08, 1.24, 1.76, STEEL)
        mesh.box(-1.52, 1.52, 0.48, 0.78, 0.30, 0.43, SLATE_DARK)
        mesh.polygon(((-0.08, 2.05, 0.38), (0.08, 2.05, 0.38), (0.06, 2.96, 1.06), (-0.06, 2.96, 1.06)), SLATE_DARK)
        return mesh
    length = 7.2 if landing else 6.8 if assault else 4.35 if patrol else 5.4
    width = 2.55 if landing else 2.35 if assault else 1.42 if patrol else 1.75
    bow = -length / 2
    stern = length / 2
    bottom = ((-width * 0.36, bow + 0.52, 0.02), (width * 0.36, bow + 0.52, 0.02), (width * 0.48, stern, 0.03), (-width * 0.48, stern, 0.03))
    deck = ((0, bow, 0.58), (width / 2, bow + 0.72, 0.54), (width / 2, stern, 0.48), (-width / 2, stern, 0.48), (-width / 2, bow + 0.72, 0.54))
    mesh.polygon(tuple(reversed(bottom)), SEA_DARK)
    mesh.polygon((bottom[0], bottom[1], deck[2], deck[4]), SEA_DARK)
    mesh.polygon((bottom[1], bottom[2], deck[3], deck[2]), SLATE_DARK)
    mesh.polygon((bottom[2], bottom[3], deck[4], deck[3]), SLATE_DARK)
    mesh.polygon((bottom[3], bottom[0], deck[4]), SEA_DARK)
    mesh.polygon(deck, DECK)
    if landing:
        mesh.box(-1.02, 1.02, -1.82, 2.85, 0.48, 0.68, SLATE)
        mesh.box(-0.92, -0.20, -0.34, 1.98, 0.66, 1.36, SLATE_DARK)
        mesh.box(-0.78, -0.34, -0.18, 1.62, 1.34, 1.88, SLATE)
        mesh.box(-0.64, -0.46, 0.10, 0.34, 1.86, 2.38, STEEL)
        # Recessed well deck and stern ramp establish the transport silhouette.
        mesh.box(0.10, 0.92, -1.22, 2.52, 0.68, 0.80, SEA_DARK)
        mesh.box(0.18, 0.84, 2.45, 3.26, 0.20, 0.58, SLATE_DARK)
        for y in (-0.82, -0.12, 0.58, 1.28):
            mesh.box(0.34, 0.72, y, y + 0.44, 0.82, 0.94, GREEN_DARK)
    elif assault:
        mesh.box(-0.94, 0.94, -1.48, 2.55, 0.48, 0.64, SLATE)
        mesh.box(-0.86, -0.18, -0.62, 1.52, 0.63, 1.32, SLATE_DARK)
        mesh.box(-0.73, -0.30, -0.46, 1.26, 1.31, 1.88, SLATE)
        mesh.box(-0.63, -0.40, -0.38, -0.08, 1.85, 2.25, SLATE_LIGHT)
        mesh.box(0.02, 0.13, -1.18, 2.18, 0.66, 0.72, LAMP, outline=False)
        for y in (-0.82, -0.10, 0.62, 1.34):
            mesh.box(0.38, 0.74, y, y + 0.48, 0.68, 0.83, SLATE_DARK)
    elif patrol:
        mesh.tapered_box((-0.46, 0.46, -1.18, 1.50, 0.48), (-0.30, 0.30, -0.90, 1.22, 1.05), SLATE)
        mesh.box(-0.25, 0.25, -0.86, -0.18, 0.92, 1.24, GLASS)
        mesh.box(-0.08, 0.08, 0.34, 0.48, 1.00, 1.72, STEEL)
        for x in (-0.46, 0.30):
            mesh.cylinder_y((x, 0.28, 0.75), 0.88, 0.07, STEEL, segments=8)
            mesh.cylinder_y((x, -0.20, 0.75), 0.08, 0.09, RED, segments=8)
    else:
        mesh.box(-0.58, 0.58, -0.24, 1.66, 0.50, 0.80, SLATE)
        mesh.tapered_box((-0.48, 0.48, 0.24, 1.42, 0.78), (-0.31, 0.31, 0.38, 1.20, 1.42), SLATE_LIGHT)
        mesh.box(-0.10, 0.10, 0.82, 1.06, 1.40, 2.15, STEEL)
        mesh.box(-0.44, 0.44, -1.84, -0.68, 0.53, 0.66, SLATE_DARK)
        for x in (-0.56, 0.48):
            for y in (-0.70, -0.28, 0.14):
                mesh.box(x, x + 0.08, y, y + 0.25, 0.79, 0.94, RED, outline=False)
    return mesh


def _ship_turret(kind: str) -> Mesh:
    mesh = Mesh()
    assault = kind == "cnhaiwang"
    patrol = kind == "cnhaiying"
    landing = kind == "cnkunlun"
    mesh.cylinder_z((0, 0, 0.68), 0.10, 0.32 if assault else 0.38, SLATE_DARK, segments=10)
    mesh.box(-0.32, 0.32, -0.34, 0.34, 0.68, 1.00, SLATE)
    if landing:
        for x in (-0.18, 0.18):
            mesh.cylinder_y((x, -0.44, 0.88), 0.48, 0.045, STEEL, segments=8)
    elif assault:
        for x in (-0.22, 0.22):
            mesh.cylinder_y((x, -0.44, 0.90), 0.54, 0.06, STEEL, segments=8)
    elif patrol:
        mesh.cylinder_y((0, -0.60, 0.88), 0.82, 0.055, STEEL, segments=8)
        mesh.box(-0.12, 0.12, 0.18, 0.36, 0.96, 1.24, GLASS)
    else:
        mesh.cylinder_y((0, -0.70, 0.88), 1.05, 0.065, STEEL, segments=8)
        mesh.box(-0.16, 0.16, 0.22, 0.42, 0.98, 1.36, GLASS)
    return mesh


def _defense_base(kind: str) -> Mesh:
    mesh = Mesh()
    mesh.box(-0.92, 0.92, -0.92, 0.92, 0.02, 0.32, GREEN_DARK)
    mesh.tapered_box((-0.78, 0.78, -0.78, 0.78, 0.28), (-0.58, 0.58, -0.58, 0.58, 0.70), GREEN)
    for x, y in ((-0.72, -0.72), (0.58, -0.72), (-0.72, 0.58), (0.58, 0.58)):
        mesh.box(x, x + 0.14, y, y + 0.14, 0.30, 0.46, RED, outline=False)
    if kind == "cnspectrum":
        mesh.box(-0.30, 0.30, -0.30, 0.30, 0.68, 1.42, SLATE)
        for x in (-0.46, 0.38):
            mesh.box(x, x + 0.08, 0.12, 0.20, 0.64, 1.52, STEEL)
    return mesh


def _defense_top(kind: str) -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, 0, 0.72), 0.10, 0.40, GREEN_DARK, segments=10)
    if kind == "cnbastion":
        mesh.box(-0.40, 0.40, -0.42, 0.42, 0.72, 1.08, GREEN)
        for x in (-0.13, 0.13):
            mesh.cylinder_y((x, -0.74, 0.94), 0.82, 0.055, STEEL, segments=8)
        mesh.box(-0.10, 0.10, 0.16, 0.36, 1.04, 1.34, GLASS)
    elif kind == "cnskyshield":
        for x in (-0.46, 0.24):
            mesh.box(x, x + 0.22, -0.42, 0.36, 0.78, 1.10, SLATE_DARK)
            for y in (-0.28, 0.08):
                mesh.cylinder_y((x + 0.11, y, 1.00), 0.48, 0.07, STEEL, segments=8)
                mesh.cylinder_y((x + 0.11, y - 0.27, 1.00), 0.08, 0.09, RED, segments=8)
        mesh.box(-0.30, 0.30, 0.24, 0.38, 1.10, 1.52, GLASS)
    else:
        mesh.cylinder_z((0, 0, 1.38), 0.08, 0.12, STEEL, segments=8)
        mesh.box(-0.58, 0.58, -0.06, 0.06, 1.44, 1.76, SLATE_LIGHT)
        mesh.box(-0.50, 0.50, -0.08, 0.08, 1.50, 1.70, GLASS)
    return mesh


def render_ground(name: str, frame_size: int) -> list[Image.Image]:
    angles = _angles(32, classic=True)
    if name == "cnqilin":
        body, turret, span = _qilin_hull(), _qilin_turret(), 6.2
        return [_render(body, a, frame_size, shadow=True, model_span=span) for a in angles] + [_render(turret, a, frame_size, shadow=False, model_span=span) for a in angles]
    if name == "cnlynx":
        body, turret, span = _lynx_hull(), _lynx_turret(), 3.7
        return [_render(body, a, frame_size, shadow=True, model_span=span) for a in angles] + [_render(turret, a, frame_size, shadow=False, model_span=span) for a in angles]
    if name == "cnmantis":
        body, turret, span = _mantis_hull(), _mantis_turret(), 5.0
        return [_render(body, a, frame_size, shadow=True, model_span=span) for a in angles] + [_render(turret, a, frame_size, shadow=False, model_span=span) for a in angles]
    if name == "cnzbd":
        body, turret, span = _zbd_hull(), _zbd_turret(), 5.6
        return [_render(body, a, frame_size, shadow=True, model_span=span) for a in angles] + [_render(turret, a, frame_size, shadow=False, model_span=span) for a in angles]
    if name == "cnphl":
        return [_render(_phl(loaded=True), a, frame_size, shadow=True, model_span=5.7) for a in angles] + [_render(_phl(loaded=False), a, frame_size, shadow=True, model_span=5.7) for a in angles]
    raise ValueError(name)


def render_air(name: str, frame_size: int) -> list[Image.Image]:
    classic = name == "cncrane"
    facings = 32 if classic else 16
    angles = _angles(facings, classic=classic)
    if name == "cnskyspear":
        mesh, span = _plane_mesh(drone=False), 6.5
    elif name == "cncloud":
        mesh, span = _plane_mesh(drone=True), 5.5
    elif name == "cncrane":
        mesh, span = _crane(), 6.7
    else:
        raise ValueError(name)
    return [_render(mesh, a, frame_size, shadow=False, model_span=span, center_y_factor=0.59) for a in angles]


def render_ship(name: str, body_size: int, turret_size: int) -> tuple[list[Image.Image], list[Image.Image]]:
    body_angles = _angles(16, classic=False)
    turret_angles = _angles(32, classic=False)
    spans = {"cnhaiwang": 8.0, "cnluyang": 6.6, "cnhaiying": 5.3, "cnkunlun": 8.6, "cnjiaolong": 7.0}
    span = spans[name]
    body = [_render(_ship_hull(name), a, body_size, shadow=False, model_span=span, center_y_factor=0.57) for a in body_angles]
    turret = [] if name == "cnjiaolong" else [_render(_ship_turret(name), a, turret_size, shadow=False, model_span=span, center_y_factor=0.57) for a in turret_angles]
    return body, turret


def render_defense(name: str, frame_size: int) -> tuple[Image.Image, list[Image.Image]]:
    span = 4.0 if name != "cnspectrum" else 4.5
    base = _render(_defense_base(name), 315, frame_size, shadow=True, model_span=span, center_y_factor=0.61)
    facings = 16 if name == "cnspectrum" else 32
    top = [_render(_defense_top(name), a, frame_size, shadow=False, model_span=span, center_y_factor=0.61)
           for a in _angles(facings, classic=name != "cnspectrum")]
    return base, top


def render_rotor(frame_size: int = 56) -> list[Image.Image]:
    supersample = 4
    images: list[Image.Image] = []
    angles = tuple(i * 22.5 for i in range(4)) + tuple(i * 11.25 for i in range(8))
    for index, angle in enumerate(angles):
        canvas = Image.new("RGBA", (frame_size * supersample, frame_size * supersample), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        cx = cy = frame_size * supersample / 2
        radius = frame_size * supersample * (0.42 if index < 4 else 0.40)
        for blade in range(5):
            radians = math.radians(angle + blade * 72)
            dx, dy = math.cos(radians) * radius, math.sin(radians) * radius * 0.42
            draw.line((cx, cy, cx + dx, cy + dy), fill=(78, 84, 77, 195), width=3 * supersample)
        draw.ellipse((cx - 3 * supersample, cy - 2 * supersample, cx + 3 * supersample, cy + 2 * supersample), fill=(45, 50, 47, 255))
        if index < 4:
            canvas = canvas.filter(ImageFilter.GaussianBlur(0.45 * supersample))
        images.append(canvas.resize((frame_size, frame_size), Image.Resampling.LANCZOS))
    return images
