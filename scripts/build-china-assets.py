"""Generate deterministic China faction sprite sources for OpenRA.Utility.

All moving sprites are built from articulated geometry. Infantry uses an
authored eight-facing skeleton for every locomotion/combat family; ground
vehicles use independent classic-facing body and turret meshes; planes use 16
authored projections; helicopters use 32 classic projections and a separate
rotor; ships use 16 bodies, 32 directional turrets, wakes, and sinking frames.
"""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from china_directional_assets import render_air, render_ground, render_rotor, render_ship


ROOT = Path(__file__).resolve().parents[1]
FRAME_ROOT = ROOT / "generated" / "china-faction-sprites"
ATLAS = ROOT / "assets" / "china-faction" / "icon-sources" / "china-unit-cameo-atlas-v1.png"

INFANTRY = ("cnrifle", "cnnetwork", "cnportable", "redspear")
GROUND = {
    "cnqilin": 44,
    "cnlynx": 32,
    "cnzbd": 42,
    "cnphl": 44,
}
AIR = {
    "cnskyspear": 56,
    "cncloud": 48,
    "cncrane": 56,
}
SHIPS = {
    "cnluyang": (64, 64),
    "cnhaiwang": (72, 72),
}
ICONS = {
    "cnrifleicon": (0, "RIFLEMAN"),
    "cnnetworkicon": (1, "NETWORK"),
    "cnportableicon": (2, "MISSILE TEAM"),
    "redspearicon": (3, "RED SPEAR"),
    "cnqilinicon": (4, "QILIN"),
    "cnlynxicon": (5, "LYNX UGV"),
    "cnzbdicon": (6, "SEA DRAGON"),
    "cnphlicon": (7, "LONGBOW"),
    "cnskyspearicon": (8, "SKY SPEAR"),
    "cncloudicon": (9, "CLOUD UAV"),
    "cncraneicon": (10, "CRANE"),
    "cnluyangicon": (11, "LUYANG"),
    "cnhaiwangicon": (12, "HAIWANG"),
}


def quantize(image: Image.Image, palette: Image.Image, *, opaque: bool = False) -> Image.Image:
    paletted = image.convert("RGB").quantize(palette=palette.copy(), dither=Image.Dither.NONE)
    data = bytearray(paletted.tobytes())
    if opaque:
        for index, value in enumerate(data):
            if value == 0:
                data[index] = 16
    else:
        alpha = image.getchannel("A").tobytes()
        for index, value in enumerate(alpha):
            if value < 96:
                data[index] = 0
        paletted.info["transparency"] = 0
    paletted.frombytes(bytes(data))
    return paletted


def output_frames(name: str, images: list[Image.Image], palette: Image.Image) -> None:
    output = FRAME_ROOT / name
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob(f"{name}-[0-9][0-9][0-9][0-9].png"):
        stale.unlink()
    for index, image in enumerate(images):
        quantize(image, palette).save(output / f"{name}-{index:04d}.png", transparency=0)
    columns = 8
    sheet = Image.new("RGBA", (columns * images[0].width, math.ceil(len(images) / columns) * images[0].height), (25, 34, 35, 255))
    for index, image in enumerate(images):
        sheet.alpha_composite(image, ((index % columns) * image.width, (index // columns) * image.height))
    sheet.save(FRAME_ROOT / f"{name}-contact-sheet.png")
    print(f"{name}: {len(images)} authored frames at {images[0].width}x{images[0].height}")


def project(point: tuple[float, float, float], angle: float, scale: float, center: tuple[float, float]) -> tuple[float, float]:
    x, y, z = point
    radians = math.radians(angle)
    rx = x * math.cos(radians) - y * math.sin(radians)
    ry = x * math.sin(radians) + y * math.cos(radians)
    return center[0] + rx * scale, center[1] + (ry * 0.48 - z * 0.90) * scale


def infantry_frame(role: str, facing: int, family: str, phase: float, frame_size: int = 24) -> Image.Image:
    ss = 5
    size = frame_size * ss
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    angle = facing * 45
    center = (size / 2, size * 0.76)
    scale = size * 0.17
    prone = family in {"prone", "prone-shoot", "liedown"}
    death = family.startswith("die")
    transition = phase if family == "liedown" else 0
    height = 0.42 if prone else 1.0
    if family == "liedown":
        height = 1.0 - 0.58 * transition
    if family == "standup":
        height = 0.42 + 0.58 * phase
    if death:
        height = max(0.10, 1.0 - phase * (0.78 + 0.12 * int(family[-1])))

    uniform = (84, 102, 65)
    uniform_light = (119, 132, 84)
    uniform_dark = (47, 58, 42)
    skin = (180, 135, 96)
    equipment = (41, 48, 42)
    accent = (158, 42, 37)
    if role == "redspear":
        uniform, uniform_light, uniform_dark = (49, 54, 55), (84, 89, 88), (25, 29, 30)

    light = 0.78 + 0.20 * math.cos(math.radians(angle - 315))
    def shade(color: tuple[int, int, int], amount: float = 1.0) -> tuple[int, int, int, int]:
        return tuple(max(0, min(255, round(channel * light * amount))) for channel in color) + (255,)

    gait = math.sin(phase * math.tau)
    stride = 0.48 * gait if family in {"run", "prone"} else 0.0
    recoil = max(0.0, math.sin(phase * math.pi)) if family in {"shoot", "prone-shoot"} else 0.0
    if death:
        stride = phase * (0.35 if int(family[-1]) % 2 else -0.35)

    hip = (0, 0, 0.78 * height)
    shoulder = (0, -0.02, 1.42 * height)
    head = (0, -0.04, 1.73 * height)
    left_foot = (-0.18, -0.12 + stride, 0.05)
    right_foot = (0.18, -0.12 - stride, 0.05)
    left_hand = (-0.26, -0.40 - recoil * 0.12, 1.20 * height)
    right_hand = (0.22, -0.58 - recoil * 0.15, 1.17 * height)
    if prone:
        hip = (0, 0.26, 0.24)
        shoulder = (0, -0.26, 0.38)
        head = (0, -0.48, 0.48)
        left_foot = (-0.18, 0.75 + stride * 0.25, 0.08)
        right_foot = (0.18, 0.70 - stride * 0.25, 0.08)
        left_hand = (-0.20, -0.64, 0.26)
        right_hand = (0.18, -0.76 - recoil * 0.12, 0.25)
    if death:
        direction = 1 if int(family[-1]) % 2 else -1
        shoulder = (direction * phase * 0.72, 0.18 * phase, 1.42 * height)
        head = (direction * phase * 0.92, -0.02, 1.73 * height)
        left_hand = (direction * phase * 0.82 - 0.24, -0.20, 1.05 * height)
        right_hand = (direction * phase * 0.80 + 0.24, -0.26, 1.02 * height)

    # Fixed contact shadow and articulated limbs.
    shadow_center = project((0, 0.22, 0), angle, scale, center)
    draw.ellipse((shadow_center[0] - 13, shadow_center[1] - 4, shadow_center[0] + 13, shadow_center[1] + 4), fill=(0, 0, 0, 90))
    p_hip, p_shoulder, p_head = (project(p, angle, scale, center) for p in (hip, shoulder, head))
    p_lfoot, p_rfoot, p_lhand, p_rhand = (project(p, angle, scale, center) for p in (left_foot, right_foot, left_hand, right_hand))
    limb_width = 5 * ss // 2
    draw.line((p_hip, p_lfoot), fill=shade(uniform_dark), width=limb_width)
    draw.line((p_hip, p_rfoot), fill=shade(uniform), width=limb_width)
    draw.line((p_shoulder, p_lhand), fill=shade(uniform), width=limb_width)
    draw.line((p_shoulder, p_rhand), fill=shade(uniform_light), width=limb_width)
    body_width = 0.31 if role != "redspear" else 0.36
    body = [
        project((-body_width, -0.02, hip[2]), angle, scale, center),
        project((body_width, -0.02, hip[2]), angle, scale, center),
        project((body_width * 0.82, -0.02, shoulder[2]), angle, scale, center),
        project((-body_width * 0.82, -0.02, shoulder[2]), angle, scale, center),
    ]
    draw.polygon(body, fill=shade(uniform), outline=shade(uniform_dark, 0.65))

    # Role silhouettes: network pack, shoulder launcher, or Red Spear command cape.
    if role == "cnnetwork":
        pack = project((0, 0.20, 1.12 * height), angle, scale, center)
        draw.rectangle((pack[0] - 6, pack[1] - 7, pack[0] + 6, pack[1] + 7), fill=shade(equipment), outline=shade(uniform_light))
        antenna = project((0.16, 0.20, 1.78 * height), angle, scale, center)
        draw.line((pack, antenna), fill=shade((145, 180, 168)), width=2)
        draw.ellipse((antenna[0] - 2, antenna[1] - 2, antenna[0] + 2, antenna[1] + 2), fill=shade(accent))
    elif role == "cnportable":
        rear = project((0.22, 0.22, 1.28 * height), angle, scale, center)
        nose = project((0.18, -1.02 - recoil * 0.12, 1.38 * height), angle, scale, center)
        draw.line((rear, nose), fill=shade(equipment), width=7)
        draw.ellipse((nose[0] - 3, nose[1] - 3, nose[0] + 3, nose[1] + 3), fill=shade(accent))
    elif role == "redspear":
        cape = [
            project((-0.30, 0.10, 1.34 * height), angle, scale, center),
            project((0.30, 0.10, 1.34 * height), angle, scale, center),
            project((0.48, 0.58, 0.28), angle, scale, center),
            project((-0.48, 0.58, 0.28), angle, scale, center),
        ]
        draw.polygon(cape, fill=shade((86, 25, 27), 0.86), outline=shade(uniform_dark))

    # Weapon points along the authored facing and foreshortens naturally.
    weapon_rear = project((-0.18, -0.10, max(0.24, 1.22 * height)), angle, scale, center)
    weapon_nose = project((-0.15, -0.95 - recoil * 0.10, max(0.25, 1.28 * height)), angle, scale, center)
    if role != "cnportable":
        draw.line((weapon_rear, weapon_nose), fill=shade(equipment), width=5)
        draw.line((weapon_nose, project((-0.15, -1.14 - recoil * 0.10, max(0.25, 1.28 * height)), angle, scale, center)), fill=shade(STEEL := (90, 94, 84)), width=3)

    helmet_radius = 8
    draw.ellipse((p_head[0] - helmet_radius, p_head[1] - helmet_radius * 0.75, p_head[0] + helmet_radius, p_head[1] + helmet_radius * 0.75), fill=shade(uniform_dark if role == "redspear" else uniform_light), outline=shade(equipment))
    face = project((0, -0.13, head[2]), angle, scale, center)
    draw.ellipse((face[0] - 3, face[1] - 2, face[0] + 3, face[1] + 2), fill=shade(skin))
    if role == "redspear":
        draw.line((p_head[0] - 5, p_head[1], p_head[0] + 5, p_head[1]), fill=shade(accent), width=2)

    return canvas.resize((frame_size, frame_size), Image.Resampling.LANCZOS)


def infantry_package(role: str) -> list[Image.Image]:
    images: list[Image.Image] = []
    # Facing-major storage matches OpenRA's Length x Facings contract.
    for family, phases in (("stand", 1), ("stand2", 1), ("run", 6), ("shoot", 8)):
        for facing in range(8):
            for phase in range(phases):
                images.append(infantry_frame(role, facing, family, phase / max(1, phases - 1)))
    for family, phases in (("liedown", 2), ("prone", 4), ("standup", 2), ("prone-shoot", 8)):
        for facing in range(8):
            for phase in range(phases):
                images.append(infantry_frame(role, facing, family, phase / max(1, phases - 1)))
    for phase in range(16):
        images.append(infantry_frame(role, 0, "stand2", phase / 15))
    for phase in range(16):
        images.append(infantry_frame(role, 4, "stand2", phase / 15))
    for family, phases in (("die1", 8), ("die2", 8), ("die3", 8), ("die4", 12), ("die5", 18)):
        for phase in range(phases):
            images.append(infantry_frame(role, (int(family[-1]) * 3) % 8, family, phase / max(1, phases - 1)))
    # Native E1 reserves frames 342..376. Fill them with authored utility poses
    # instead of transparent placeholders so malformed sequence edits stay visible.
    for phase in range(35):
        images.append(infantry_frame(role, phase % 8, "stand2", (phase % 7) / 6))
    images.append(infantry_frame(role, 0, "stand", 0))  # parachute passenger pose
    if len(images) != 378:
        raise AssertionError(f"{role}: expected 378 frames, got {len(images)}")
    return images


def wreck(images: list[Image.Image], facings: int, *, turret: bool) -> list[Image.Image]:
    count = facings * (2 if turret else 1)
    result: list[Image.Image] = []
    for index, source in enumerate(images[:count]):
        damaged = ImageEnhance.Color(source.convert("RGBA")).enhance(0.18)
        damaged = ImageEnhance.Brightness(damaged).enhance(0.55)
        burn = Image.new("RGBA", damaged.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(burn)
        cx, cy = damaged.width * 0.52 + (index % 4) - 2, damaged.height * 0.54
        draw.ellipse((cx - damaged.width * 0.18, cy - damaged.height * 0.13, cx + damaged.width * 0.18, cy + damaged.height * 0.13), fill=(14, 10, 8, 155))
        burn.putalpha(ImageChops.multiply(burn.getchannel("A"), damaged.getchannel("A")))
        result.append(Image.alpha_composite(damaged, burn))
    return result


def sinking(body: list[Image.Image]) -> list[Image.Image]:
    result: list[Image.Image] = []
    for facing, source in enumerate(body):
        for phase in range(4):
            dark = ImageEnhance.Brightness(ImageEnhance.Color(source).enhance(0.55)).enhance(1 - phase * 0.14)
            frame = Image.new("RGBA", source.size, (0, 0, 0, 0))
            offset = phase * 3
            frame.alpha_composite(dark, (0, offset))
            # Clip the lower hull progressively to read as sinking, not fading.
            clip_y = source.height - phase * 3
            if clip_y < source.height:
                alpha = frame.getchannel("A")
                ImageDraw.Draw(alpha).rectangle((0, clip_y, source.width, source.height), fill=0)
                frame.putalpha(alpha)
            result.append(frame)
    return result


def projectile_frames(kind: str, size: int = 32) -> list[Image.Image]:
    images: list[Image.Image] = []
    for facing in range(16):
        angle = math.radians(facing * 22.5 - 90)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        cx, cy = size / 2, size / 2
        length = 12 if kind == "missile" else 15
        dx, dy = math.cos(angle), math.sin(angle)
        px, py = -dy, dx
        width = 2.3 if kind == "missile" else 5.0
        color = (110, 119, 102, 255) if kind == "missile" else (66, 77, 76, 255)
        draw.polygon(((cx + dx * length / 2, cy + dy * length / 2), (cx - dx * length / 2 + px * width, cy - dy * length / 2 + py * width), (cx - dx * length / 2 - px * width, cy - dy * length / 2 - py * width)), fill=color, outline=(30, 34, 33, 255))
        draw.line((cx - dx * length / 2, cy - dy * length / 2, cx - dx * (length / 2 + 5), cy - dy * (length / 2 + 5)), fill=(240, 133, 39, 210), width=2)
        images.append(canvas)
    return images


def effect_frames(kind: str, frames: int, size: int = 64) -> list[Image.Image]:
    result: list[Image.Image] = []
    for phase in range(frames):
        progress = phase / max(1, frames - 1)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        cx, cy = size / 2, size / 2
        if kind == "network":
            radius = 5 + progress * 24
            alpha = round(220 * (1 - progress))
            draw.ellipse((cx - radius, cy - radius * 0.48, cx + radius, cy + radius * 0.48), outline=(71, 215, 240, alpha), width=2)
            draw.ellipse((cx - radius * 0.40, cy - radius * 0.40, cx + radius * 0.40, cy + radius * 0.40), fill=(74, 204, 226, max(15, alpha // 4)))
        else:
            radius = 3 + math.sin(progress * math.pi * 0.88) * (18 if kind == "precision" else 22)
            alpha = round(255 * (1 - progress * 0.84))
            draw.ellipse((cx - radius, cy - radius * 0.70, cx + radius, cy + radius * 0.70), fill=(69, 66, 57, max(10, alpha // 2)))
            fire = radius * max(0.20, 0.76 - progress * 0.42)
            draw.ellipse((cx - fire, cy - fire, cx + fire, cy + fire), fill=(243, 92 + phase * 6, 28, alpha))
            draw.ellipse((cx - fire * 0.38, cy - fire * 0.38, cx + fire * 0.38, cy + fire * 0.38), fill=(255, 231, 135, alpha))
        result.append(canvas.filter(ImageFilter.GaussianBlur(0.45)))
    return result


def muzzle_frames(size: int, heavy: bool) -> list[Image.Image]:
    result: list[Image.Image] = []
    for facing in range(8):
        angle = math.radians(facing * 45 - 90)
        for phase in range(6):
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(canvas)
            cx, cy = size / 2, size / 2
            dx, dy = math.cos(angle), math.sin(angle)
            px, py = -dy, dx
            length = (13 if heavy else 9) - phase
            width = max(1.2, (4.5 if heavy else 3.1) - phase * 0.42)
            draw.polygon(((cx + dx * length, cy + dy * length), (cx + px * width, cy + py * width), (cx - px * width, cy - py * width)), fill=(255, 151, 38, max(25, 255 - phase * 40)))
            draw.line((cx, cy, cx + dx * length * 0.65, cy + dy * length * 0.65), fill=(255, 245, 184, max(20, 250 - phase * 42)), width=2)
            result.append(canvas)
    return result


def rotor_and_misc(palette: Image.Image) -> None:
    output_frames("cncranerotor", render_rotor(56), palette)
    output_frames("china-heavy-muzzle", muzzle_frames(48, True), palette)
    output_frames("china-light-muzzle", muzzle_frames(40, False), palette)
    output_frames("china-missile", projectile_frames("missile"), palette)
    output_frames("china-drone-projectile", projectile_frames("drone"), palette)
    output_frames("china-network-pulse", effect_frames("network", 8, 48), palette)
    output_frames("china-network-impact", effect_frames("network", 10), palette)
    output_frames("china-precision-impact", effect_frames("precision", 10), palette)
    output_frames("china-naval-impact", effect_frames("naval", 10), palette)
    wakes: list[Image.Image] = []
    for phase in range(8):
        canvas = Image.new("RGBA", (48, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        alpha = 170 - phase * 18
        spread = 5 + phase * 2
        draw.arc((3, 8 - phase // 2, 45, 25 + phase // 2), 15 + spread, 165 - spread, fill=(184, 214, 221, alpha), width=2)
        draw.arc((3, 8 - phase // 2, 45, 25 + phase // 2), 195 + spread, 345 - spread, fill=(184, 214, 221, alpha), width=2)
        wakes.append(canvas)
    output_frames("china-wake", wakes, palette)


def icon_frames(palette: Image.Image) -> None:
    atlas = Image.open(ATLAS).convert("RGB")
    font_path = ROOT / "engine" / "openra" / "mods" / "common" / "FreeSansBold.ttf"
    for name, (cell, label) in ICONS.items():
        row, column = divmod(cell, 4)
        left, right = round(column * atlas.width / 4), round((column + 1) * atlas.width / 4)
        top, bottom = round(row * atlas.height / 4), round((row + 1) * atlas.height / 4)
        source = atlas.crop((left + 5, top + 5, right - 5, bottom - 5))
        target_ratio = 4 / 3
        if source.width / source.height > target_ratio:
            width = round(source.height * target_ratio)
            x = (source.width - width) // 2
            source = source.crop((x, 0, x + width, source.height))
        else:
            height = round(source.width / target_ratio)
            y = (source.height - height) // 2
            source = source.crop((0, y, source.width, y + height))
        cameo = ImageEnhance.Sharpness(source.resize((64, 48), Image.Resampling.LANCZOS)).enhance(1.35).convert("RGBA")
        shade = Image.new("RGBA", cameo.size, (0, 0, 0, 0))
        ImageDraw.Draw(shade).rectangle((0, 35, 63, 47), fill=(0, 0, 0, 175))
        cameo.alpha_composite(shade)
        font_size = 9
        while font_size > 6:
            font = ImageFont.truetype(font_path, font_size)
            bounds = ImageDraw.Draw(cameo).textbbox((0, 0), label, font=font, stroke_width=1)
            if bounds[2] - bounds[0] <= 60:
                break
            font_size -= 1
        draw = ImageDraw.Draw(cameo)
        bounds = draw.textbbox((0, 0), label, font=font, stroke_width=1)
        draw.text(((64 - (bounds[2] - bounds[0])) // 2, 37), label, font=font, fill=(244, 245, 235, 255), stroke_width=1, stroke_fill=(8, 10, 10, 255))
        output = FRAME_ROOT / name
        output.mkdir(parents=True, exist_ok=True)
        quantize(cameo, palette, opaque=True).save(output / f"{name}-0000.png")
        cameo.save(FRAME_ROOT / f"{name}-review.png")
        print(f"{name}: original 64x48 production cameo")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--palette", required=True, type=Path)
    args = parser.parse_args()
    palette = Image.open(args.palette)
    if palette.mode != "P":
        raise ValueError("reference palette must be indexed")
    FRAME_ROOT.mkdir(parents=True, exist_ok=True)
    for role in INFANTRY:
        output_frames(role, infantry_package(role), palette)
    for name, size in GROUND.items():
        live = render_ground(name, size)
        output_frames(name, live, palette)
        output_frames(f"{name}husk", wreck(live, 32, turret=name != "cnphl"), palette)
    for name, size in AIR.items():
        live = render_air(name, size)
        output_frames(name, live, palette)
        output_frames(f"{name}husk", wreck(live, 32 if name == "cncrane" else 16, turret=False), palette)
    for name, (body_size, turret_size) in SHIPS.items():
        body, turret = render_ship(name, body_size, turret_size)
        output_frames(name, body, palette)
        output_frames(f"{name}turret", turret, palette)
        output_frames(f"{name}sink", sinking(body), palette)
    rotor_and_misc(palette)
    icon_frames(palette)
    hashes = {}
    for role in INFANTRY:
        paths = sorted((FRAME_ROOT / role).glob(f"{role}-*.png"))
        hashes[role] = len({hashlib.sha256(path.read_bytes()).hexdigest() for path in paths[:8]})
    if any(count != 8 for count in hashes.values()):
        raise ValueError(f"infantry standing facings are not unique: {hashes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
