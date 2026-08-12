"""Deterministic, authored-facing art for the playable Iran faction.

Nothing in this module rotates a finished sprite.  Vehicles and aircraft are
rendered from low-poly geometry for every required heading, while infantry are
redrawn from a jointed figure for every facing and animation pose.  This keeps
the source reviewable and makes the native OpenRA facing contracts testable.
"""

from __future__ import annotations

import math
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter

from red_sea_directional_vehicle import Mesh, _angles, _render
from red_sea_infantry import InfantryStyle, _frame


GREEN = (73, 91, 57)
GREEN_LIGHT = (111, 125, 77)
GREEN_DARK = (42, 54, 39)
SAND = (172, 145, 91)
SAND_LIGHT = (202, 174, 112)
SAND_DARK = (110, 91, 59)
RUBBER = (31, 34, 31)
METAL = (58, 62, 57)
GLASS = (31, 55, 59)
RED = (165, 42, 41)
WHITE = (218, 220, 207)
WATER = (74, 129, 148)

# Exact chroma markers used by build-iran-sprites.py. They are deliberately
# outside the faction art palette and are replaced with RA remap indices before
# the SHP packages are written. Four luminance levels preserve directional
# shading and make every Iran unit readable in any chosen player color.
TEAM_LIGHT = (255, 0, 255)
TEAM_MID = (255, 0, 223)
TEAM_DARK = (223, 0, 255)
TEAM_DEEP = (191, 0, 255)
TEAM_MARKERS = frozenset((TEAM_LIGHT, TEAM_MID, TEAM_DARK, TEAM_DEEP))


def _wheels(mesh: Mesh, *, length: float, width: float, count: int, radius: float = 0.34) -> None:
    for index in range(count):
        y = -length / 2 + 0.44 + index * (length - 0.88) / max(1, count - 1)
        mesh.cylinder_x((0, y, radius), width + 0.18, radius, RUBBER)
        mesh.cylinder_x((0, y, radius), width + 0.23, radius * 0.45, SAND_DARK)


def _karrar_hull() -> Mesh:
    mesh = Mesh()
    mesh.box(-1.28, -0.92, -1.95, 1.82, 0.10, 0.69, RUBBER)
    mesh.box(0.92, 1.28, -1.95, 1.82, 0.10, 0.69, RUBBER)
    for y in (-1.55, -0.84, -0.13, 0.58, 1.29):
        mesh.cylinder_x((0, y, 0.37), 2.62, 0.29, RUBBER)
        mesh.cylinder_x((0, y, 0.37), 2.68, 0.13, SAND_DARK)
    mesh.tapered_box((-1.04, 1.04, -1.76, 1.55, 0.53), (-0.84, 0.84, -1.30, 1.36, 1.07), TEAM_MID)
    mesh.polygon(((-0.82, -1.30, 1.07), (0.82, -1.30, 1.07), (0.62, -1.73, 0.70), (-0.62, -1.73, 0.70)), TEAM_LIGHT)
    for x in (-0.58, -0.22, 0.14, 0.50):
        mesh.box(x, x + 0.15, 0.73, 1.34, 1.05, 1.15, METAL, outline=False)
    mesh.box(-0.75, -0.55, -1.61, -1.45, 0.74, 0.91, WHITE, outline=False)
    mesh.box(0.55, 0.75, -1.61, -1.45, 0.74, 0.91, WHITE, outline=False)
    return mesh


def _karrar_turret() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, -0.02, 1.13), 0.12, 0.73, TEAM_DEEP)
    mesh.tapered_box((-0.78, 0.78, -0.69, 0.66, 1.14), (-0.58, 0.58, -0.84, 0.48, 1.62), TEAM_MID)
    mesh.box(-0.26, 0.26, -1.58, -0.68, 1.37, 1.51, TEAM_DARK)
    mesh.cylinder_y((0, -1.92, 1.44), 2.72, 0.095, METAL, segments=10)
    mesh.box(-0.48, -0.18, -0.30, 0.08, 1.60, 1.76, TEAM_LIGHT)
    mesh.box(0.22, 0.47, -0.18, 0.10, 1.61, 1.87, GLASS)
    mesh.cylinder_z((0.38, 0.13, 1.76), 0.33, 0.13, METAL)
    return mesh


def _truck_hull() -> Mesh:
    mesh = Mesh()
    _wheels(mesh, length=4.05, width=1.72, count=4, radius=0.34)
    mesh.box(-0.89, 0.89, -1.88, 1.82, 0.42, 0.68, TEAM_DARK)
    mesh.tapered_box((-0.84, 0.84, -1.89, -0.77, 0.66), (-0.75, 0.75, -1.78, -0.82, 1.45), TEAM_MID)
    mesh.box(-0.63, 0.63, -1.84, -1.70, 1.03, 1.33, GLASS, outline=False)
    mesh.box(-0.87, 0.87, -0.73, 1.61, 0.69, 0.82, TEAM_DEEP)
    mesh.box(-0.76, -0.56, -1.98, -1.86, 0.73, 0.88, WHITE, outline=False)
    mesh.box(0.56, 0.76, -1.98, -1.86, 0.73, 0.88, WHITE, outline=False)
    return mesh


def _raad_turret() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, 0.28, 0.91), 0.14, 0.62, TEAM_DEEP)
    mesh.box(-0.62, 0.62, -0.26, 0.87, 0.92, 1.29, TEAM_MID)
    for x in (-0.43, 0.08):
        mesh.slanted_box_y(x, x + 0.34, -0.79, 0.73, 1.22, 1.55, 0.22, TEAM_LIGHT)
    mesh.box(-0.14, 0.14, 0.53, 0.86, 1.31, 1.86, METAL)
    mesh.box(-0.33, 0.33, 0.69, 0.83, 1.68, 1.92, GLASS)
    return mesh


def _fajr_turret(*, loaded: bool) -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, 0.27, 0.89), 0.12, 0.60, TEAM_DEEP)
    mesh.box(-0.72, 0.72, -0.05, 0.78, 0.93, 1.17, TEAM_MID)
    if loaded:
        for x in (-0.50, -0.17, 0.16):
            mesh.slanted_box_y(x, x + 0.25, -1.10, 0.62, 1.22, 1.52, 0.25, TEAM_LIGHT)
            mesh.box(x + 0.03, x + 0.22, -1.24, -1.07, 1.44, 1.64, RED, outline=False)
    else:
        for x in (-0.50, -0.17, 0.16):
            mesh.slanted_box_y(x, x + 0.25, -0.55, 0.62, 1.27, 1.48, 0.17, METAL)
    return mesh


def _coast_turret() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, 0.34, 0.91), 0.12, 0.59, TEAM_DEEP)
    mesh.box(-0.73, 0.73, 0.04, 0.86, 0.94, 1.19, TEAM_MID)
    for x in (-0.51, 0.13):
        mesh.slanted_box_y(x, x + 0.38, -1.16, 0.67, 1.20, 1.42, 0.33, TEAM_LIGHT)
        mesh.box(x + 0.04, x + 0.34, -1.34, -1.13, 1.39, 1.70, TEAM_DARK)
    mesh.box(-0.16, 0.16, 0.63, 0.85, 1.38, 1.93, METAL)
    mesh.box(-0.37, 0.37, 0.71, 0.83, 1.77, 1.98, GLASS)
    return mesh


def _azar_airframe() -> Mesh:
    mesh = Mesh()
    mesh.polygon(((0, -3.00, 0.18), (0.30, -1.20, 0.26), (0.38, 1.91, 0.15), (0, 2.40, 0.08), (-0.38, 1.91, 0.15), (-0.30, -1.20, 0.26)), TEAM_LIGHT)
    mesh.polygon(((-0.25, -0.89, 0.19), (-2.15, 0.83, 0.04), (-0.79, 1.28, 0.11), (0, 0.74, 0.29), (0.79, 1.28, 0.11), (2.15, 0.83, 0.04), (0.25, -0.89, 0.19)), TEAM_MID)
    mesh.polygon(((0, 1.04, 0.15), (-1.03, 2.02, 0.06), (-0.36, 2.15, 0.09), (0, 1.78, 0.22), (0.36, 2.15, 0.09), (1.03, 2.02, 0.06)), TEAM_DARK)
    mesh.polygon(((-0.14, -0.62, 0.27), (0.14, -0.62, 0.27), (0.26, 0.24, 0.47), (-0.26, 0.24, 0.47)), GLASS)
    mesh.polygon(((0, 1.25, 0.24), (0.08, 1.91, 1.06), (-0.08, 1.91, 1.06)), GREEN_DARK)
    mesh.box(-0.15, 0.15, 1.86, 2.24, 0.04, 0.22, METAL)
    return mesh


def _toufan_airframe() -> Mesh:
    mesh = Mesh()
    mesh.tapered_box((-0.63, 0.63, -1.50, 1.25, 0.24), (-0.39, 0.39, -1.60, 1.07, 0.93), TEAM_MID)
    mesh.polygon(((-0.37, -1.58, 0.46), (0.37, -1.58, 0.46), (0.27, -0.71, 0.88), (-0.27, -0.71, 0.88)), GLASS)
    mesh.slanted_box_y(-0.11, 0.11, 0.74, 3.05, 0.50, 0.83, 0.18, TEAM_DARK)
    mesh.polygon(((0, 2.42, 0.73), (-0.83, 2.99, 0.65), (0, 2.85, 0.82), (0.83, 2.99, 0.65)), TEAM_MID)
    mesh.polygon(((0, 2.40, 0.69), (0, 3.03, 1.50), (0, 3.03, 0.62)), TEAM_DARK)
    mesh.box(-1.31, -0.56, -0.18, 0.49, 0.31, 0.48, TEAM_LIGHT)
    mesh.box(0.56, 1.31, -0.18, 0.49, 0.31, 0.48, TEAM_LIGHT)
    for x in (-1.13, 0.87):
        mesh.cylinder_y((x, -0.22, 0.38), 0.65, 0.10, METAL)
    mesh.cylinder_z((0, -0.04, 1.03), 0.20, 0.15, METAL)
    return mesh


def _mohajer_airframe() -> Mesh:
    mesh = Mesh()
    mesh.tapered_box((-0.24, 0.24, -2.06, 1.62, 0.12), (-0.16, 0.16, -1.77, 1.46, 0.38), TEAM_MID)
    mesh.polygon(((-0.16, -0.58, 0.20), (-2.20, 0.32, 0.05), (-0.55, 0.69, 0.14), (0, 0.45, 0.31), (0.55, 0.69, 0.14), (2.20, 0.32, 0.05), (0.16, -0.58, 0.20)), TEAM_LIGHT)
    mesh.polygon(((0, 1.10, 0.19), (-0.86, 1.71, 0.08), (-0.28, 1.75, 0.13), (0.28, 1.75, 0.13), (0.86, 1.71, 0.08)), TEAM_DARK)
    mesh.cylinder_y((0, 1.72, 0.24), 0.33, 0.18, METAL)
    mesh.box(-0.18, 0.18, -1.94, -1.68, 0.25, 0.44, GLASS)
    return mesh


def _loiter_airframe() -> Mesh:
    mesh = Mesh()
    mesh.tapered_box((-0.16, 0.16, -1.77, 1.20, 0.11), (-0.09, 0.09, -1.58, 1.08, 0.28), TEAM_DARK)
    mesh.polygon(((0, -0.48, 0.18), (-1.52, 0.53, 0.04), (-0.28, 0.72, 0.13), (0.28, 0.72, 0.13), (1.52, 0.53, 0.04)), TEAM_LIGHT)
    mesh.polygon(((0, 0.84, 0.15), (-0.62, 1.35, 0.06), (0, 1.18, 0.19), (0.62, 1.35, 0.06)), TEAM_MID)
    mesh.box(-0.13, 0.13, -1.73, -1.49, 0.15, 0.35, RED, outline=False)
    return mesh


def _peykaap_hull() -> Mesh:
    mesh = Mesh()
    mesh.polygon(((0, -2.67, 0.18), (0.77, -1.69, 0.12), (0.91, 1.72, 0.15), (0.57, 2.20, 0.20), (-0.57, 2.20, 0.20), (-0.91, 1.72, 0.15), (-0.77, -1.69, 0.12)), TEAM_DEEP)
    mesh.polygon(((0, -2.50, 0.20), (0.72, -1.57, 0.22), (0.72, 1.72, 0.28), (-0.72, 1.72, 0.28), (-0.72, -1.57, 0.22)), TEAM_LIGHT)
    mesh.tapered_box((-0.50, 0.50, -0.55, 0.75, 0.27), (-0.39, 0.39, -0.44, 0.63, 0.90), TEAM_MID)
    mesh.box(-0.29, 0.29, -0.49, -0.38, 0.57, 0.79, GLASS, outline=False)
    mesh.box(-0.38, 0.38, 1.18, 1.50, 0.28, 0.47, METAL)
    return mesh


def _peykaap_turret() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, -1.16, 0.31), 0.09, 0.28, TEAM_DEEP)
    mesh.box(-0.26, 0.26, -1.42, -0.91, 0.33, 0.60, TEAM_MID)
    mesh.cylinder_y((0, -1.70, 0.49), 0.83, 0.055, METAL, segments=8)
    for x in (-0.53, 0.25):
        mesh.slanted_box_y(x, x + 0.28, 0.42, 1.38, 0.42, 0.55, 0.20, TEAM_LIGHT)
    return mesh


def _ghadir_hull() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_y((0, 0, 0.34), 4.56, 0.55, TEAM_DARK, segments=12)
    mesh.polygon(((0, -2.65, 0.34), (-0.43, -2.25, 0.13), (0.43, -2.25, 0.13)), TEAM_DARK)
    mesh.polygon(((0, 2.55, 0.34), (-0.38, 2.22, 0.16), (0.38, 2.22, 0.16)), TEAM_DARK)
    mesh.box(-0.15, 0.15, -0.18, 0.51, 0.78, 1.17, TEAM_MID)
    mesh.box(-0.05, 0.05, -0.21, -0.03, 1.12, 1.48, METAL)
    mesh.polygon(((-0.12, 1.75, 0.36), (-0.98, 2.30, 0.26), (0, 2.07, 0.45), (0.98, 2.30, 0.26), (0.12, 1.75, 0.36)), TEAM_LIGHT)
    return mesh


def _classic_pair(hull: Mesh, turret: Mesh, frame_size: int, span: float) -> tuple[list[Image.Image], list[Image.Image]]:
    angles = _angles(32, classic=True)
    return (
        [_render(hull, angle, frame_size, shadow=True, model_span=span, flat_colors=TEAM_MARKERS) for angle in angles],
        [_render(turret, angle, frame_size, shadow=False, model_span=span, flat_colors=TEAM_MARKERS) for angle in angles],
    )


def render_karrar(frame_size: int = 40, facings: int = 32) -> tuple[list[Image.Image], list[Image.Image]]:
    assert facings == 32
    return _classic_pair(_karrar_hull(), _karrar_turret(), frame_size, 6.05)


def render_raad(frame_size: int = 40, facings: int = 32) -> tuple[list[Image.Image], list[Image.Image]]:
    assert facings == 32
    return _classic_pair(_truck_hull(), _raad_turret(), frame_size, 5.85)


def render_fajr(frame_size: int = 40, facings: int = 32) -> tuple[list[Image.Image], list[Image.Image], list[Image.Image]]:
    assert facings == 32
    angles = _angles(32, classic=True)
    return (
        [_render(_truck_hull(), angle, frame_size, shadow=True, model_span=5.85, flat_colors=TEAM_MARKERS) for angle in angles],
        [_render(_fajr_turret(loaded=True), angle, frame_size, shadow=False, model_span=5.85, flat_colors=TEAM_MARKERS) for angle in angles],
        [_render(_fajr_turret(loaded=False), angle, frame_size, shadow=False, model_span=5.85, flat_colors=TEAM_MARKERS) for angle in angles],
    )


def render_coast(frame_size: int = 40, facings: int = 32) -> tuple[list[Image.Image], list[Image.Image]]:
    assert facings == 32
    return _classic_pair(_truck_hull(), _coast_turret(), frame_size, 5.85)


def _air_frames(mesh: Mesh, frame_size: int, facings: int, span: float, *, pitch: float = 0) -> list[Image.Image]:
    return [_render(mesh, angle, frame_size, shadow=False, model_span=span, center_y_factor=0.59, pitch=pitch, flat_colors=TEAM_MARKERS) for angle in _angles(facings, classic=facings == 32)]


def render_azar(frame_size: int = 56, facings: int = 16) -> list[Image.Image]:
    assert facings == 16
    return _air_frames(_azar_airframe(), frame_size, facings, 7.2)


def render_toufan(frame_size: int = 56, facings: int = 32) -> list[Image.Image]:
    assert facings == 32
    return _air_frames(_toufan_airframe(), frame_size, facings, 6.7)


def render_mohajer(frame_size: int = 44, facings: int = 16) -> list[Image.Image]:
    assert facings == 16
    return _air_frames(_mohajer_airframe(), frame_size, facings, 5.5)


def render_loiter(frame_size: int = 40, facings: int = 16) -> list[Image.Image]:
    assert facings == 16
    return _air_frames(_loiter_airframe(), frame_size, facings, 4.5) + _air_frames(_loiter_airframe(), frame_size, facings, 4.5, pitch=27)


def render_peykaap(frame_size: int = 44, facings: int = 16) -> tuple[list[Image.Image], list[Image.Image]]:
    assert facings == 16
    hull = [_render(_peykaap_hull(), angle, frame_size, shadow=False, model_span=6.1, center_y_factor=0.62, flat_colors=TEAM_MARKERS) for angle in _angles(16, classic=False)]
    turret = [_render(_peykaap_turret(), angle, frame_size, shadow=False, model_span=6.1, center_y_factor=0.62, flat_colors=TEAM_MARKERS) for angle in _angles(32, classic=True)]
    return hull, turret


def render_ghadir(frame_size: int = 44, facings: int = 16) -> list[Image.Image]:
    assert facings == 16
    return [_render(_ghadir_hull(), angle, frame_size, shadow=False, model_span=6.0, center_y_factor=0.62, flat_colors=TEAM_MARKERS) for angle in _angles(16, classic=False)]


DIRECTIONAL_RENDERERS: dict[str, Callable[..., object]] = {
    "irkarr": render_karrar,
    "irraad": render_raad,
    "irfajr": render_fajr,
    "ircoast": render_coast,
    "irazar": render_azar,
    "irtoufan": render_toufan,
    "irmohajer": render_mohajer,
    "irloiter": render_loiter,
    "irpey": render_peykaap,
    "irghadir": render_ghadir,
}


def render_directional_asset(name: str, frame_size: int, facings: int) -> list[Image.Image]:
    try:
        result = DIRECTIONAL_RENDERERS[name](frame_size, facings)
    except KeyError as error:
        raise ValueError(f"unknown Iran directional model: {name}") from error
    if isinstance(result, tuple):
        return [frame for layer in result for frame in layer]
    return result  # type: ignore[return-value]


def render_rotor(frame_size: int = 48) -> list[Image.Image]:
    images: list[Image.Image] = []
    supersample = 4
    for index, angle in enumerate(tuple(i * 22.5 for i in range(4)) + tuple(i * 11.25 for i in range(8))):
        image = Image.new("RGBA", (frame_size * supersample, frame_size * supersample), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        center = frame_size * supersample / 2
        radius = frame_size * supersample * (0.44 if index < 4 else 0.41)
        for blade in range(4):
            radians = math.radians(angle + 90 * blade)
            dx, dy = math.cos(radians) * radius, math.sin(radians) * radius * 0.43
            draw.line((center - dx, center - dy, center + dx, center + dy), fill=(42, 50, 43, 180), width=3 * supersample)
        draw.ellipse((center - 3 * supersample, center - 3 * supersample, center + 3 * supersample, center + 3 * supersample), fill=(95, 99, 78, 255))
        if index < 4:
            image = image.filter(ImageFilter.GaussianBlur(0.45 * supersample))
        images.append(image.resize((frame_size, frame_size), Image.Resampling.LANCZOS))
    return images


def _point(center: tuple[float, float], facing: int, forward: float, side: float) -> tuple[float, float]:
    angle = math.radians(facing * 45 - 90)
    fx, fy = math.cos(angle), math.sin(angle) * 0.55
    sx, sy = -math.sin(angle), math.cos(angle) * 0.55
    return center[0] + fx * forward + sx * side, center[1] + fy * forward + sy * side


def _infantry_pose(action: str, phase: int, length: int) -> dict[str, float]:
    cycle = math.tau * phase / max(1, length)
    pose = {"bob": 0.0, "lean": 0.0, "arm": 0.0, "leg": 0.0, "crouch": 0.0, "fall": 0.0}
    if action in {"run", "prone-run"}:
        pose.update(bob=math.sin(cycle * 2) * 0.7, lean=1.0, arm=math.sin(cycle) * 2.2, leg=math.sin(cycle) * 2.4)
    elif action in {"shoot", "prone-shoot"}:
        pose.update(lean=0.7, arm=-0.6 if phase in {1, 2} else 0.0)
    elif action == "liedown":
        pose["crouch"] = phase / max(1, length - 1)
    elif action == "standup":
        pose["crouch"] = 1 - phase / max(1, length - 1)
    elif action.startswith("die"):
        pose["fall"] = phase / max(1, length - 1)
    elif action.startswith("idle"):
        pose["arm"] = math.sin(cycle) * 0.9
    return pose


IRAN_INFANTRY_STYLES = {
    "basij": InfantryStyle("rifle", TEAM_MID, TEAM_DEEP, TEAM_LIGHT, (137, 91, 61), GREEN_DARK, SAND_LIGHT, 1.04),
    "atgm": InfantryStyle("atgm", TEAM_MID, TEAM_DEEP, TEAM_DARK, (137, 91, 61), METAL, SAND_LIGHT, 1.16),
    "controller": InfantryStyle("controller", TEAM_LIGHT, TEAM_DEEP, TEAM_MID, (137, 91, 61), GLASS, (74, 194, 166), 1.02),
    "shadow": InfantryStyle("shadow", TEAM_DEEP, (31, 38, 36), (76, 84, 79), (127, 84, 58), (21, 26, 25), (79, 224, 184), 1.13, hood=True),
}


def render_infantry(role: str, frame_size: int | None = None) -> list[Image.Image]:
    """Return the complete facing-major E1/E3/E7-compatible Iran sheet.

    Every pose is rebuilt from the articulated figure. Upright poses keep a
    vertical spine at all headings while legs, weapon, backpack, cloak, and
    facing cues are independently projected. No finished bitmap is rotated.
    """

    del frame_size  # Native Red Sea infantry canvases are a stable 50x39.
    style = IRAN_INFANTRY_STYLES[role]
    team = (TEAM_LIGHT, TEAM_MID, TEAM_DARK, TEAM_DEEP)
    frames: list[Image.Image] = []

    frames.extend(_frame(style, team, "stand", facing, 0) for facing in range(8))
    frames.extend(_frame(style, team, "stand", facing, 7) for facing in range(8))
    for facing in range(8):
        frames.extend(_frame(style, team, "run", facing, phase, 6) for phase in range(6))
    for facing in range(8):
        frames.extend(_frame(style, team, "shoot", facing, phase, 8) for phase in range(8))
    frames.extend(_frame(style, team, "prone", facing, 0, 4) for facing in range(8))
    for facing in range(8):
        frames.extend(_frame(style, team, "prone", facing, phase, 4) for phase in range(4))
    for facing in range(8):
        frames.extend(_frame(style, team, "transition", facing, phase, 2) for phase in range(2))
    for facing in range(8):
        frames.extend(_frame(style, team, "transition", facing, 1 - phase, 2) for phase in range(2))
    for facing in range(8):
        frames.extend(_frame(style, team, "prone-shoot", facing, phase, 8) for phase in range(8))
    frames.extend(_frame(style, team, "idle", 0, phase, 8, 0) for phase in range(8))
    frames.extend(_frame(style, team, "idle", 0, phase, 8, 1) for phase in range(8))
    for variant, length in enumerate((8, 8, 8, 12, 18)):
        for facing in range(8):
            frames.extend(_frame(style, team, "directional-die", facing, phase, length, variant) for phase in range(length))
    frames.append(_frame(style, team, "stand", 0, 0))

    if len(frames) != 713:
        raise AssertionError(f"{role}: expected 713 Iran infantry frames, got {len(frames)}")
    return frames


def render_effect(kind: str, frame_size: int = 48) -> list[Image.Image]:
    counts = {"impact": 10, "sabotage": 12, "cloak": 8, "wake": 6, "sink": 8, "muzzle": 48, "missile": 32}
    count = counts[kind]
    images: list[Image.Image] = []
    facings = 8 if kind == "muzzle" else 32 if kind == "missile" else 1
    phases = count // facings
    for facing in range(facings):
        for phase in range(phases):
            image = Image.new("RGBA", (frame_size * 4, frame_size * 4), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            c = frame_size * 2
            p = phase / max(1, phases - 1)
            angle = math.radians(facing * 360 / facings - 90)
            if kind == "muzzle":
                length = (9 - phase) * 4
                dx, dy = math.cos(angle) * length, math.sin(angle) * length
                draw.polygon(((c - dy * .3, c + dx * .3), (c + dx, c + dy), (c + dy * .3, c - dx * .3)), fill=(255, 157, 39, 255 - phase * 35))
            elif kind == "missile":
                dx, dy = math.cos(angle) * 22, math.sin(angle) * 22
                px, py = -math.sin(angle) * 5, math.cos(angle) * 5
                draw.polygon(((c + dx, c + dy), (c - dx + px, c - dy + py), (c - dx - px, c - dy - py)), fill=(*GREEN_LIGHT, 255))
                draw.ellipse((c - dx - 5, c - dy - 5, c - dx + 5, c - dy + 5), fill=(255, 126, 35, 220))
            elif kind == "impact":
                radius = (5 + 45 * math.sin(p * math.pi))
                draw.ellipse((c - radius, c - radius, c + radius, c + radius), fill=(235, 82 + phase * 8, 26, max(20, 255 - phase * 23)))
                draw.ellipse((c - radius * .4, c - radius * .4, c + radius * .4, c + radius * .4), fill=(255, 229, 130, max(20, 250 - phase * 22)))
            elif kind == "sabotage":
                radius = 8 + phase * 5
                for spoke in range(8):
                    a = math.radians(spoke * 45 + phase * 13)
                    draw.line((c, c, c + math.cos(a) * radius, c + math.sin(a) * radius), fill=(91, 229, 178, max(10, 255 - phase * 19)), width=5)
            elif kind == "cloak":
                radius = 16 + phase * 4
                draw.arc((c - radius, c - radius * .7, c + radius, c + radius * .7), phase * 23, phase * 23 + 250, fill=(72, 210, 171, max(20, 210 - phase * 20)), width=6)
            elif kind == "wake":
                radius = 9 + phase * 7
                draw.arc((c - radius, c - radius * .45, c + radius, c + radius * .45), 15, 165, fill=(*WATER, max(20, 210 - phase * 31)), width=5)
            elif kind == "sink":
                radius = 15 + phase * 5
                draw.ellipse((c - radius, c - radius * .35, c + radius, c + radius * .35), outline=(*WATER, max(20, 220 - phase * 26)), width=5)
                for bubble in range(3):
                    x = c + (bubble - 1) * 17 + math.sin(phase + bubble) * 5
                    y = c - phase * 8 - bubble * 6
                    draw.ellipse((x - 4, y - 4, x + 4, y + 4), outline=(190, 224, 228, max(20, 225 - phase * 25)), width=3)
            images.append(image.filter(ImageFilter.GaussianBlur(1.1)).resize((frame_size, frame_size), Image.Resampling.LANCZOS))
    return images
