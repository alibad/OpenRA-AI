"""Deterministic full-state infantry renderer for the Red Sea roster.

The generated packages deliberately follow the classic RA E1 frame contract:
8 facings for standing, running, firing, prone movement, and prone firing, plus
transitions, idles, and five distinct deaths.  Characters are drawn from a
small articulated model instead of rotating one flattened bitmap, which keeps
weapons, backpacks, limbs, and shadows coherent through every facing.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from PIL import Image, ImageDraw


FRAME_SIZE = (50, 39)
SCALE = 4
FACINGS = 8


@dataclass(frozen=True)
class InfantryStyle:
    role: str
    cloth: tuple[int, int, int]
    cloth_dark: tuple[int, int, int]
    armor: tuple[int, int, int]
    skin: tuple[int, int, int]
    gear: tuple[int, int, int]
    accent: tuple[int, int, int]
    bulky: float = 1.0
    hood: bool = False
    scarf: bool = False


STYLES: dict[str, InfantryStyle] = {
    "sang": InfantryStyle("rifle", (166, 142, 91), (82, 76, 53), (105, 100, 63), (126, 83, 55), (45, 45, 36), (203, 179, 105), 1.16),
    "sajtac": InfantryStyle("jtac", (176, 151, 100), (83, 75, 52), (101, 96, 62), (132, 88, 58), (43, 48, 39), (64, 121, 112), 1.02),
    "saat": InfantryStyle("atgm", (153, 130, 82), (73, 68, 48), (92, 90, 58), (123, 82, 55), (47, 48, 35), (176, 143, 52), 1.18),
    "falcon1": InfantryStyle("commando", (58, 56, 49), (28, 30, 29), (70, 66, 52), (118, 78, 53), (24, 28, 27), (81, 132, 116), 1.04, scarf=True),
    "ymr": InfantryStyle("rifle", (116, 100, 73), (62, 55, 43), (92, 80, 57), (122, 79, 51), (55, 47, 34), (161, 124, 66), 0.92, scarf=True),
    "yrpg": InfantryStyle("rpg", (113, 98, 67), (57, 53, 39), (85, 75, 51), (121, 78, 50), (45, 43, 31), (150, 105, 51), 1.02, scarf=True),
    "yspot": InfantryStyle("spotter", (91, 86, 66), (49, 50, 42), (79, 77, 57), (125, 82, 52), (39, 43, 37), (66, 135, 126), 1.00, scarf=True),
    "wadighost": InfantryStyle("ghost", (58, 54, 47), (26, 28, 27), (65, 58, 49), (111, 73, 49), (27, 29, 27), (177, 102, 45), 0.96, hood=True, scarf=True),
}


def _c(color: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
    return (*color, alpha)


def _s(value: float) -> int:
    return round(value * SCALE)


def _xy(point: tuple[float, float]) -> tuple[int, int]:
    return _s(point[0]), _s(point[1])


def _ellipse(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], fill: tuple[int, ...], outline: tuple[int, ...] | None = None) -> None:
    draw.ellipse(tuple(_s(v) for v in box), fill=fill, outline=outline, width=SCALE if outline else 1)


def _polygon(draw: ImageDraw.ImageDraw, points: Iterable[tuple[float, float]], fill: tuple[int, ...], outline: tuple[int, ...] | None = None) -> None:
    draw.polygon([_xy(p) for p in points], fill=fill, outline=outline)


def _line(draw: ImageDraw.ImageDraw, points: Iterable[tuple[float, float]], fill: tuple[int, ...], width: float = 1.0) -> None:
    draw.line([_xy(p) for p in points], fill=fill, width=max(1, _s(width)), joint="curve")


def _facing_vector(facing: int) -> tuple[float, float, float, float]:
    """Return forward and right vectors in native ClassicFacing handedness."""

    theta = math.tau * facing / FACINGS
    fx = -math.sin(theta)
    fy = -math.cos(theta) * 0.46
    rx = math.cos(theta)
    ry = -math.sin(theta) * 0.46
    return fx, fy, rx, ry


def _team_colors(palette: Image.Image) -> tuple[tuple[int, int, int], ...]:
    values = palette.getpalette()
    if values is None:
        raise ValueError("infantry renderer requires a paletted reference image")
    return tuple(tuple(values[index * 3:index * 3 + 3]) for index in (82, 85, 88, 91))


def _weapon_kind(style: InfantryStyle) -> str:
    if style.role in {"atgm", "rpg"}:
        return style.role
    if style.role in {"jtac", "spotter"}:
        return "carbine"
    if style.role in {"commando", "ghost"}:
        return "suppressed"
    return "rifle"


def _draw_weapon(
    draw: ImageDraw.ImageDraw,
    style: InfantryStyle,
    center: tuple[float, float],
    facing: int,
    *,
    firing: bool,
    recoil: float,
    prone: bool,
) -> None:
    fx, fy, rx, ry = _facing_vector(facing)
    kind = _weapon_kind(style)
    length = {"rifle": 6.2, "carbine": 5.0, "suppressed": 7.0, "rpg": 7.4, "atgm": 9.0}[kind]
    back = 2.0 if kind in {"rpg", "atgm"} else 1.5
    cx, cy = center
    if prone:
        cy += 0.8
    start = (cx - fx * back + rx * 0.25, cy - fy * back + ry * 0.25)
    end = (cx + fx * (length - recoil), cy + fy * (length - recoil))
    outline = _c((20, 22, 20))
    body = _c((61, 58, 43) if kind in {"rpg", "atgm"} else (35, 37, 34))
    _line(draw, (start, end), outline, 2.0 if kind in {"rpg", "atgm"} else 1.55)
    _line(draw, (start, end), body, 1.15 if kind in {"rpg", "atgm"} else 0.75)

    if kind == "atgm":
        _ellipse(draw, (end[0] - 1.4, end[1] - 1.4, end[0] + 1.4, end[1] + 1.4), _c((54, 55, 39)), outline)
        sight = (cx + fx * 1.2 + rx * 0.9, cy + fy * 1.2 + ry * 0.9 - 1.2)
        _ellipse(draw, (sight[0] - .7, sight[1] - .7, sight[0] + .7, sight[1] + .7), _c(style.accent), outline)
    elif kind == "rpg":
        tip = (end[0] + fx * 1.0, end[1] + fy * 1.0)
        _polygon(draw, ((end[0] - rx, end[1] - ry), tip, (end[0] + rx, end[1] + ry)), _c((110, 105, 69)), outline)
    elif kind == "suppressed":
        suppressor = (end[0] + fx * 1.8, end[1] + fy * 1.8)
        _line(draw, (end, suppressor), _c((18, 20, 19)), 1.15)
        end = suppressor
    else:
        stock = (start[0] - fx * 1.2, start[1] - fy * 1.2)
        _line(draw, (start, stock), _c((76, 55, 37)), 1.05)

    if firing:
        flash = (end[0] + fx * 1.1, end[1] + fy * 1.1)
        size = 2.1 if kind in {"atgm", "rpg"} else 1.35
        _polygon(
            draw,
            ((flash[0] + fx * size * 1.8, flash[1] + fy * size * 1.8),
             (flash[0] + rx * size, flash[1] + ry * size),
             (flash[0] - rx * size, flash[1] - ry * size)),
            _c((255, 211, 92), 245),
        )
        if kind in {"atgm", "rpg"}:
            exhaust = (start[0] - fx * 1.8, start[1] - fy * 1.8)
            _ellipse(draw, (exhaust[0] - 1.8, exhaust[1] - 1.0, exhaust[0] + 1.8, exhaust[1] + 1.0), _c((187, 181, 155), 170))


def _draw_equipment(draw: ImageDraw.ImageDraw, style: InfantryStyle, facing: int, torso: tuple[float, float], team: tuple[tuple[int, int, int], ...]) -> None:
    fx, fy, rx, ry = _facing_vector(facing)
    tx, ty = torso
    behind = (tx - fx * 1.8, ty - fy * 1.8)
    outline = _c((27, 28, 24))

    if style.role in {"jtac", "spotter", "atgm"}:
        _polygon(draw, ((behind[0] - 2.0, behind[1] - 3.0), (behind[0] + 2.0, behind[1] - 2.6),
                        (behind[0] + 1.8, behind[1] + 2.4), (behind[0] - 1.8, behind[1] + 2.4)), _c(style.gear), outline)
        antenna_top = (behind[0] - rx * .7, behind[1] - 6.0)
        _line(draw, ((behind[0] - rx * .7, behind[1] - 2.5), antenna_top), _c((32, 34, 31)), .55)
        _ellipse(draw, (antenna_top[0] - .35, antenna_top[1] - .35, antenna_top[0] + .35, antenna_top[1] + .35), _c(style.accent))

    if style.role == "spotter":
        hand = (tx + fx * 1.4 + rx * 2.0, ty + fy * 1.4 + ry * 2.0)
        _polygon(draw, ((hand[0] - 1.7, hand[1] - 1.3), (hand[0] + 1.7, hand[1] - 1.3),
                        (hand[0] + 1.5, hand[1] + 1.2), (hand[0] - 1.5, hand[1] + 1.2)), _c((33, 39, 38)), outline)
        _line(draw, ((hand[0] - .9, hand[1]), (hand[0] + .9, hand[1])), _c(style.accent), .6)
    elif style.role == "jtac":
        optic = (tx + fx * 2.0 + rx * 1.8, ty + fy * 2.0 + ry * 1.8 - 2.0)
        _line(draw, ((optic[0] - rx * 1.0, optic[1] - ry), (optic[0] + rx * 1.0, optic[1] + ry)), _c((25, 29, 28)), 1.35)
        _ellipse(draw, (optic[0] - .55, optic[1] - .55, optic[0] + .55, optic[1] + .55), _c(style.accent), outline)
    elif style.role in {"commando", "ghost"}:
        charge = (tx - fx * .3 - rx * 2.0, ty - fy * .3 - ry * 2.0 + 2.2)
        _polygon(draw, ((charge[0] - 1.1, charge[1] - 1.2), (charge[0] + 1.1, charge[1] - 1.2),
                        (charge[0] + 1.1, charge[1] + 1.2), (charge[0] - 1.1, charge[1] + 1.2)), _c(style.accent), outline)

    # A compact player-remap panel keeps teams readable without swallowing the
    # faction-specific uniform palette.
    panel = (tx + rx * 2.0, ty + ry * 2.0 - 1.0)
    _line(draw, ((panel[0] - rx * 1.1, panel[1] - ry * 1.1), (panel[0] + rx * 1.1, panel[1] + ry * 1.1)), _c(team[1]), 1.15)


def _draw_upright(
    draw: ImageDraw.ImageDraw,
    style: InfantryStyle,
    team: tuple[tuple[int, int, int], ...],
    facing: int,
    *,
    run_phase: int | None = None,
    shoot_phase: int | None = None,
    idle_phase: int | None = None,
) -> None:
    fx, fy, rx, ry = _facing_vector(facing)
    stride = 0.0 if run_phase is None else math.sin(math.tau * run_phase / 6)
    sway = 0.0 if run_phase is None else math.cos(math.tau * run_phase / 6) * .55
    bob = 0.0 if run_phase is None else -0.65 * abs(math.sin(math.tau * run_phase / 6))
    if idle_phase is not None:
        bob += math.sin(math.tau * idle_phase / 16) * .18

    cx, ground = 25.0 + rx * sway, 25.0 + ry * sway
    aim_shift = (0.0, .25, .62, .85, .52, .28, .12, 0.0)[shoot_phase] if shoot_phase is not None else 0.0
    hips = (cx + fx * stride * .35, ground - 7.0 + bob)
    torso = (cx + fx * (stride * .18 + aim_shift), ground - 12.0 + bob - aim_shift * .28)
    head = (torso[0], torso[1] - 5.0)
    outline = _c((27, 27, 23))

    _ellipse(draw, (cx - 4.6, ground - .8, cx + 5.2, ground + 1.2), _c((20, 18, 15), 92))

    leg_spread = 2.0 + abs(stride) * 1.7
    left_foot = (hips[0] + rx * leg_spread + fx * stride * 2.0, ground + ry * leg_spread + fy * stride * 2.0)
    right_foot = (hips[0] - rx * leg_spread - fx * stride * 2.0, ground - ry * leg_spread - fy * stride * 2.0)
    _line(draw, (hips, left_foot), outline, 2.8 * style.bulky)
    _line(draw, (hips, left_foot), _c(style.cloth_dark), 1.65 * style.bulky)
    _line(draw, (hips, right_foot), outline, 2.8 * style.bulky)
    _line(draw, (hips, right_foot), _c(style.cloth), 1.65 * style.bulky)
    _ellipse(draw, (left_foot[0] - 1.7, left_foot[1] - .7, left_foot[0] + 1.8, left_foot[1] + .7), _c(style.gear), outline)
    _ellipse(draw, (right_foot[0] - 1.7, right_foot[1] - .7, right_foot[0] + 1.8, right_foot[1] + .7), _c(style.gear), outline)

    width = 3.5 * style.bulky
    _polygon(draw, ((torso[0] - width, torso[1] - 3.0), (torso[0] + width, torso[1] - 3.0),
                    (hips[0] + width * .78, hips[1] + .7), (hips[0] - width * .78, hips[1] + .7)), _c(style.cloth), outline)
    _polygon(draw, ((torso[0] - width * .82, torso[1] - 2.2), (torso[0] + width * .82, torso[1] - 2.2),
                    (torso[0] + width * .68, torso[1] + 2.1), (torso[0] - width * .68, torso[1] + 2.1)), _c(style.armor), outline)

    _draw_equipment(draw, style, facing, torso, team)

    helmet = style.cloth_dark if style.hood else style.armor
    _ellipse(draw, (head[0] - 2.5 * style.bulky, head[1] - 2.6, head[0] + 2.5 * style.bulky, head[1] + 2.2), _c(style.skin), outline)
    if style.hood:
        _polygon(draw, ((head[0] - 3.0, head[1] + .6), (head[0] - 2.0, head[1] - 3.0),
                        (head[0] + 2.0, head[1] - 3.0), (head[0] + 3.0, head[1] + .6),
                        (head[0], head[1] + 2.4)), _c(helmet), outline)
    else:
        _ellipse(draw, (head[0] - 2.8 * style.bulky, head[1] - 3.0, head[0] + 2.8 * style.bulky, head[1] + .1), _c(helmet), outline)
    if style.scarf:
        _line(draw, ((head[0] - 2.1, head[1] + 1.0), (head[0] + 2.1, head[1] + 1.0)), _c(style.cloth_dark), 1.05)
    face_point = (head[0] + fx * 2.4, head[1] + fy * 2.0 + .4)
    _ellipse(draw, (face_point[0] - .55, face_point[1] - .45, face_point[0] + .55, face_point[1] + .45), _c((22, 22, 20)))

    recoil = 0.0
    firing = False
    if shoot_phase is not None:
        firing = shoot_phase in (2, 3)
        recoil = 1.0 if shoot_phase == 3 else .55 if shoot_phase in (2, 4) else 0.0
    weapon_center = (torso[0] + fx * .7, torso[1] + fy * .7)
    _draw_weapon(draw, style, weapon_center, facing, firing=firing, recoil=recoil, prone=False)

    arm_swing = stride * 1.3 if run_phase is not None else 0.0
    left_hand = (weapon_center[0] + fx * 1.4 + rx * 1.0, weapon_center[1] + fy * 1.4 + ry * 1.0)
    right_hand = (weapon_center[0] - fx * .5 - rx * .8, weapon_center[1] - fy * .5 - ry * .8)
    shoulder_l = (torso[0] + rx * 2.8, torso[1] - 1.4 + ry * 2.8)
    shoulder_r = (torso[0] - rx * 2.8, torso[1] - 1.4 - ry * 2.8)
    _line(draw, (shoulder_l, (left_hand[0] + fx * arm_swing, left_hand[1] + fy * arm_swing)), outline, 2.0)
    _line(draw, (shoulder_l, (left_hand[0] + fx * arm_swing, left_hand[1] + fy * arm_swing)), _c(style.cloth), 1.0)
    _line(draw, (shoulder_r, (right_hand[0] - fx * arm_swing, right_hand[1] - fy * arm_swing)), outline, 2.0)
    _line(draw, (shoulder_r, (right_hand[0] - fx * arm_swing, right_hand[1] - fy * arm_swing)), _c(style.cloth_dark), 1.0)


def _draw_prone(draw: ImageDraw.ImageDraw, style: InfantryStyle, team: tuple[tuple[int, int, int], ...], facing: int, phase: int, firing: bool = False) -> None:
    fx, fy, rx, ry = _facing_vector(facing)
    cx, cy = 25.0, 24.0
    crawl = math.sin(math.tau * phase / 4) * .8
    outline = _c((25, 25, 22))
    _ellipse(draw, (cx - 5.4, cy - .7, cx + 5.7, cy + 1.0), _c((18, 17, 14), 88))

    rear = (cx - fx * 3.8, cy - fy * 3.8)
    front = (cx + fx * 2.5, cy + fy * 2.5 - 1.6)
    _line(draw, ((rear[0] - rx * 2.2, rear[1] - ry * 2.2), (rear[0] + fx * crawl + rx * 1.0, rear[1] + fy * crawl + ry)), outline, 2.8)
    _line(draw, ((rear[0] + rx * 2.2, rear[1] + ry * 2.2), (rear[0] - fx * crawl - rx * 1.0, rear[1] - fy * crawl - ry)), _c(style.cloth_dark), 1.8)
    _line(draw, (rear, front), outline, 5.0 * style.bulky)
    _line(draw, (rear, front), _c(style.cloth), 3.1 * style.bulky)
    _line(draw, ((cx - fx, cy - fy - 1.1), (front[0] + fx * 1.4, front[1] + fy * 1.4)), _c(style.armor), 2.4 * style.bulky)
    head = (front[0] + fx * 1.1, front[1] + fy * 1.1 - 1.1)
    _ellipse(draw, (head[0] - 2.0, head[1] - 1.9, head[0] + 2.0, head[1] + 1.6), _c(style.skin), outline)
    _ellipse(draw, (head[0] - 2.2, head[1] - 2.2, head[0] + 2.2, head[1] - .1), _c(style.cloth_dark if style.hood else style.armor), outline)
    _line(draw, ((cx - rx * 1.7, cy - ry * 1.7 - 2.0), (cx + rx * 1.7, cy + ry * 1.7 - 2.0)), _c(team[1]), 1.1)
    _draw_weapon(draw, style, (front[0] + fx * .5, front[1] + fy * .5 - 1.0), facing, firing=firing, recoil=.8 if firing else 0.0, prone=True)


def _draw_transition(draw: ImageDraw.ImageDraw, style: InfantryStyle, team: tuple[tuple[int, int, int], ...], facing: int, progress: float) -> None:
    # A crouched articulated midpoint is visibly different from both endpoints.
    fx, fy, rx, ry = _facing_vector(facing)
    cx = 25.0 + fx * progress * 1.5
    ground = 25.0
    height = 12.0 - 6.2 * progress
    hips = (cx - fx * progress * 2.0, ground - 3.4)
    torso = (cx, ground - height + 3.0)
    head = (torso[0] + fx * progress * 1.4, torso[1] - 4.0 + progress * 1.2)
    outline = _c((26, 26, 23))
    _ellipse(draw, (cx - 5, ground - .7, cx + 5, ground + 1.0), _c((18, 17, 14), 85))
    _line(draw, ((hips[0] - rx * 2.2, hips[1] - ry * 2.2), (cx - rx * 3.0 - fx * progress * 2.2, ground)), outline, 2.5)
    _line(draw, ((hips[0] + rx * 2.2, hips[1] + ry * 2.2), (cx + rx * 3.0, ground)), _c(style.cloth_dark), 1.7)
    _line(draw, (hips, torso), outline, 5.0 * style.bulky)
    _line(draw, (hips, torso), _c(style.cloth), 3.0 * style.bulky)
    _line(draw, ((torso[0] - rx * 2.1, torso[1] - ry * 2.1), (torso[0] + rx * 2.1, torso[1] + ry * 2.1)), _c(team[1]), 1.2)
    _ellipse(draw, (head[0] - 2.2, head[1] - 2.2, head[0] + 2.2, head[1] + 1.8), _c(style.skin), outline)
    _ellipse(draw, (head[0] - 2.5, head[1] - 2.6, head[0] + 2.5, head[1] - .1), _c(style.cloth_dark if style.hood else style.armor), outline)
    _draw_weapon(draw, style, (torso[0] + fx, torso[1] + fy), facing, firing=False, recoil=0, prone=progress > .5)


def _draw_death(draw: ImageDraw.ImageDraw, style: InfantryStyle, team: tuple[tuple[int, int, int], ...], variant: int, phase: int, length: int) -> None:
    t = min(1.0, phase / max(1, length - 1))
    facing = (variant * 2 + 1) % 8
    fx, fy, rx, ry = _facing_vector(facing)
    cx, ground = 25.0, 25.0
    outline = _c((25, 24, 21))
    fall_side = -1 if variant % 2 else 1
    upper = (cx + rx * fall_side * 5.5 * t + fx * (variant - 2) * .7 * t, ground - 12.0 * (1 - t) - 1.0)
    hips = (cx, ground - 6.0 + 4.5 * t)
    _ellipse(draw, (cx - 5.5, ground - .8, cx + 6.0, ground + 1.2), _c((19, 17, 14), 90))
    _line(draw, (hips, upper), outline, 5.2 * style.bulky)
    _line(draw, (hips, upper), _c(style.cloth if variant != 4 else style.cloth_dark), 3.1 * style.bulky)
    head = (upper[0] + rx * fall_side * 2.8, upper[1] - 3.0 * (1 - t))
    _ellipse(draw, (head[0] - 2.2, head[1] - 2.0, head[0] + 2.2, head[1] + 1.8), _c(style.skin), outline)
    _line(draw, (hips, (cx - rx * 4.0, ground - t)), _c(style.cloth_dark), 2.2)
    _line(draw, (hips, (cx + rx * 4.0, ground)), _c(style.cloth), 2.2)
    _line(draw, (upper, (upper[0] - rx * 4.0, upper[1] + 2.0)), _c(style.cloth_dark), 1.9)
    _line(draw, (upper, (upper[0] + rx * 4.0, upper[1] + 2.0)), _c(style.cloth), 1.9)
    if phase < max(2, length // 2):
        _draw_weapon(draw, style, (upper[0] + fx, upper[1] + fy), facing, firing=False, recoil=0, prone=t > .7)
    if variant == 4 and phase >= length // 3:
        # Fire death stays abstract at this scale and avoids graphic detail.
        flame = (cx + math.sin(phase) * 1.3, ground - 4.0 - (phase % 5))
        _polygon(draw, ((flame[0], flame[1] - 3.0), (flame[0] - 1.8, flame[1] + 1.2), (flame[0] + 1.8, flame[1] + 1.2)), _c((224, 121, 43), 220))


def _frame(style: InfantryStyle, team: tuple[tuple[int, int, int], ...], action: str, facing: int = 0, phase: int = 0, length: int = 1, variant: int = 0) -> Image.Image:
    image = Image.new("RGBA", (FRAME_SIZE[0] * SCALE, FRAME_SIZE[1] * SCALE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if action == "stand":
        _draw_upright(draw, style, team, facing, idle_phase=phase)
    elif action == "run":
        _draw_upright(draw, style, team, facing, run_phase=phase)
    elif action == "shoot":
        _draw_upright(draw, style, team, facing, shoot_phase=phase)
    elif action == "prone":
        _draw_prone(draw, style, team, facing, phase)
    elif action == "prone-shoot":
        _draw_prone(draw, style, team, facing, phase, firing=phase in (2, 3))
    elif action == "transition":
        _draw_transition(draw, style, team, facing, phase / max(1, length - 1))
    elif action == "idle":
        _draw_upright(draw, style, team, 0, idle_phase=phase)
        if variant == 1 and phase in range(length // 3, 2 * length // 3):
            # Small hand/device motion distinguishes the second idle.
            _ellipse(draw, (_s(28) / SCALE, _s(8) / SCALE, _s(30) / SCALE, _s(10) / SCALE), _c(style.accent))
    elif action == "die":
        _draw_death(draw, style, team, variant, phase, length)
    else:
        raise KeyError(action)

    return image.resize(FRAME_SIZE, Image.Resampling.LANCZOS)


def render_infantry_asset(name: str, palette: Image.Image) -> list[Image.Image]:
    style = STYLES[name]
    team = _team_colors(palette)
    frames: list[Image.Image] = []

    # Exact E1-compatible layout through frame 341.
    frames.extend(_frame(style, team, "stand", facing, 0) for facing in range(8))
    frames.extend(_frame(style, team, "stand", facing, 7) for facing in range(8))
    for facing in range(8):
        frames.extend(_frame(style, team, "run", facing, phase, 6) for phase in range(6))
    for facing in range(8):
        frames.extend(_frame(style, team, "shoot", facing, phase, 8) for phase in range(8))
    for facing in range(8):
        frames.extend(_frame(style, team, "transition", facing, phase, 2) for phase in range(2))
    for facing in range(8):
        frames.extend(_frame(style, team, "prone", facing, phase, 4) for phase in range(4))
    for facing in range(8):
        frames.extend(_frame(style, team, "transition", facing, 1 - phase, 2) for phase in range(2))
    for facing in range(8):
        frames.extend(_frame(style, team, "prone-shoot", facing, phase, 8) for phase in range(8))
    frames.extend(_frame(style, team, "idle", 0, phase, 16, 0) for phase in range(16))
    frames.extend(_frame(style, team, "idle", 0, phase, 16, 1) for phase in range(16))
    for variant, length in enumerate((8, 8, 8, 12, 18)):
        frames.extend(_frame(style, team, "die", 0, phase, length, variant) for phase in range(length))

    if len(frames) != 342:
        raise AssertionError(f"{name}: expected 342 infantry frames, got {len(frames)}")
    return frames
