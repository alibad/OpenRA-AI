"""Build every original Iran faction SHP source and visual audit sheet."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from iran_directional_assets import (
    TEAM_DARK,
    TEAM_DEEP,
    TEAM_LIGHT,
    TEAM_MID,
    render_directional_asset,
    render_effect,
    render_infantry,
    render_rotor,
)


REMAP_MARKERS = {
    TEAM_LIGHT: 82,
    TEAM_MID: 85,
    TEAM_DARK: 89,
    TEAM_DEEP: 93,
}


def remap_marker_index(rgb: bytes) -> int | None:
    red, green, blue = rgb
    # LANCZOS downsampling softens marker edges. Recognize the isolated magenta
    # chroma family, then preserve the closest authored luminance step.
    if red < 135 or blue < 135 or green > 72 or green * 3 > min(red, blue):
        return None
    color = (red, green, blue)
    marker = min(REMAP_MARKERS, key=lambda candidate: sum((a - b) ** 2 for a, b in zip(color, candidate)))
    return REMAP_MARKERS[marker]


ROOT = Path(__file__).resolve().parents[1]
FRAME_ROOT = ROOT / "generated" / "iran-sprites"
FONT = ROOT / "engine" / "openra" / "mods" / "common" / "FreeSansBold.ttf"

DIRECTIONAL = {
    "irkarr": (40, 32), "irraad": (40, 32), "irfajr": (40, 32), "ircoast": (40, 32),
    "irazar": (56, 16), "irtoufan": (56, 32), "irmohajer": (44, 16), "irloiter": (40, 16),
    "irpey": (44, 16), "irghadir": (44, 16),
}

INFANTRY = {
    "irbas": "basij", "iratgm": "atgm", "irdc": "controller", "shadowone": "shadow",
}

WRECKS = {
    "irkarrhusk": ("irkarr", 40, 32, 2),
    "irraadhusk": ("irraad", 40, 32, 2),
    "irfajrhusk": ("irfajr", 40, 32, 2),
    "ircoasthusk": ("ircoast", 40, 32, 2),
    "irazarhusk": ("irazar", 56, 16, 1),
    "irtoufanhusk": ("irtoufan", 56, 32, 1),
    "irmohajerhusk": ("irmohajer", 44, 16, 1),
}

SINKS = {
    "irpeysink": ("irpey", 44, 16),
    "irghadirsink": ("irghadir", 44, 16),
}

EFFECTS = {
    "irmuzzle": ("muzzle", 48),
    "irimpact": ("impact", 64),
    "irsabotage": ("sabotage", 64),
    "ircloak": ("cloak", 48),
    "irwake": ("wake", 48),
    "irmissile": ("missile", 24),
}

ICONS = {
    "irbasicon": ("irbas", "BASIJ"),
    "iratgmicon": ("iratgm", "ATGM TEAM"),
    "irdcicon": ("irdc", "DRONE CTRL"),
    "shadowoneicon": ("shadowone", "SHADOW ONE"),
    "irkarricon": ("irkarr", "KARRAR"),
    "irraadicon": ("irraad", "RAAD AA"),
    "irfajricon": ("irfajr", "FAJR"),
    "ircoasticon": ("ircoast", "COASTAL"),
    "irazaricon": ("irazar", "AZAR"),
    "irtoufanicon": ("irtoufan", "TOUFAN"),
    "irmohajericon": ("irmohajer", "MOHAJER"),
    "irloitericon": ("irloiter", "SIMORGH"),
    "irpeyicon": ("irpey", "PEYKAAP"),
    "irghadiricon": ("irghadir", "GHADIR"),
}


def quantize(image: Image.Image, palette: Image.Image, *, opaque: bool = False) -> Image.Image:
    indexed = image.convert("RGB").quantize(palette=palette.copy(), dither=Image.Dither.NONE)
    data = bytearray(indexed.tobytes())
    source = image.convert("RGB").tobytes()
    if opaque:
        for index, value in enumerate(data):
            rgb = source[index * 3:index * 3 + 3]
            remap = remap_marker_index(rgb)
            if remap is not None:
                data[index] = remap
            elif value == 0:
                data[index] = 16
    else:
        alpha = image.getchannel("A").tobytes()
        for index, value in enumerate(alpha):
            if value < 96:
                data[index] = 0
            else:
                rgb = source[index * 3:index * 3 + 3]
                remap = remap_marker_index(rgb)
                if remap is not None:
                    data[index] = remap
    indexed.frombytes(bytes(data))
    if not opaque:
        indexed.info["transparency"] = 0
    return indexed


def save_frames(name: str, frames: list[Image.Image], palette: Image.Image) -> None:
    output = FRAME_ROOT / name
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob(f"{name}-[0-9][0-9][0-9][0-9].png"):
        stale.unlink()
    for index, frame in enumerate(frames):
        quantize(frame, palette).save(output / f"{name}-{index:04d}.png", transparency=0)


def sheet(name: str, frames: list[Image.Image], *, columns: int = 8, limit: int | None = None) -> None:
    review = frames[:limit] if limit else frames
    size = review[0].size[0]
    output = Image.new("RGBA", (columns * size, math.ceil(len(review) / columns) * size), (34, 39, 35, 255))
    for index, frame in enumerate(review):
        output.alpha_composite(frame, ((index % columns) * size, (index // columns) * size))
    output.save(FRAME_ROOT / f"{name}-contact-sheet.png")


def wreck(frame: Image.Image, index: int) -> Image.Image:
    result = ImageEnhance.Color(frame.convert("RGBA")).enhance(0.18)
    result = ImageEnhance.Brightness(result).enhance(0.54)
    overlay = Image.new("RGBA", result.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    c = result.width / 2
    draw.ellipse((c - 8 + index % 3, c - 7, c + 8 + index % 3, c + 8), fill=(22, 11, 7, 150))
    overlay.putalpha(ImageChops.multiply(overlay.getchannel("A"), result.getchannel("A")))
    return Image.alpha_composite(result, overlay)


def sinking_frames(model: str, frame_size: int, facings: int) -> list[Image.Image]:
    live = render_directional_asset(model, frame_size, facings)[:facings]
    result: list[Image.Image] = []
    for facing, hull in enumerate(live):
        for phase in range(8):
            p = phase / 7
            canvas = Image.new("RGBA", hull.size, (0, 0, 0, 0))
            faded = hull.copy()
            faded.putalpha(faded.getchannel("A").point(lambda a, p=p: round(a * (1 - p * .88))))
            canvas.alpha_composite(faded, (0, round(phase * 1.55)))
            draw = ImageDraw.Draw(canvas)
            y = frame_size * .62 + phase
            radius = 7 + phase * 2.1
            draw.ellipse((frame_size / 2 - radius, y - radius * .28, frame_size / 2 + radius, y + radius * .28), outline=(92, 164, 178, 225 - phase * 25), width=1)
            for bubble in range(3):
                x = frame_size / 2 + (bubble - 1) * 5 + math.sin(facing + phase + bubble) * 2
                by = y - phase * 1.8 - bubble * 3
                draw.ellipse((x - 1, by - 1, x + 1, by + 1), outline=(190, 222, 224, 210 - phase * 20))
            result.append(canvas)
    return result


def icon_source(asset: str) -> Image.Image:
    size, facings = DIRECTIONAL[asset]
    frames = render_directional_asset(asset, size, facings)
    # A three-quarter heading fills the cameo and exposes the model's length,
    # turret, wings, or sail. Frame zero made every unit a tiny vertical glyph.
    facing = 28 if facings == 32 else 14
    source = frames[facing]
    if asset in {"irkarr", "irraad", "irfajr", "ircoast"}:
        source = Image.alpha_composite(source, frames[32 + facing])
    elif asset == "irpey":
        source = Image.alpha_composite(source, frames[16 + 28])
    bbox = source.getchannel("A").getbbox()
    return source.crop(bbox) if bbox else source


def _icon_background(label: str, accent: tuple[int, int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    background = Image.new("RGBA", (64, 48), (28, 48, 37, 255))
    draw = ImageDraw.Draw(background)
    for y in range(34):
        p = y / 33
        draw.line(
            (0, y, 63, y),
            fill=(round(11 + accent[0] * .19 * p), round(19 + accent[1] * .22 * p), round(18 + accent[2] * .19 * p), 255),
        )
    draw.polygon(((0, 29), (22, 18), (63, 24), (63, 34), (0, 34)), fill=(9, 16, 15, 125))
    draw.line((0, 33, 63, 33), fill=(*accent, 225), width=1)
    draw.rectangle((0, 0, 63, 47), outline=(5, 8, 7, 255))
    draw.rectangle((0, 34, 63, 47), fill=(8, 15, 12, 225))
    font_size = 9
    while font_size > 6:
        font = ImageFont.truetype(FONT, font_size)
        box = draw.textbbox((0, 0), label, font=font, stroke_width=1)
        if box[2] - box[0] <= 61:
            break
        font_size -= 1
    width = draw.textbbox((0, 0), label, font=font, stroke_width=1)[2]
    draw.text(((64 - width) // 2, 37), label, font=font, fill=(241, 241, 225, 255), stroke_width=1, stroke_fill=(0, 0, 0, 255))
    return background, draw


def _infantry_icon(asset: str, label: str) -> Image.Image:
    role = INFANTRY[asset]
    accents = {
        "basij": (184, 142, 72),
        "atgm": (204, 116, 58),
        "controller": (55, 181, 167),
        "shadow": (45, 203, 164),
    }
    background, draw = _icon_background(label, accents[role])
    outline = (13, 17, 16, 255)
    skin = (151, 101, 70, 255)

    # Portrait-scale shoulders and torso occupy the full art panel. Team-marker
    # colors survive quantization as player remap indices.
    draw.polygon(((7, 33), (13, 22), (24, 17), (43, 17), (56, 24), (62, 33)), fill=(*TEAM_DEEP, 255), outline=outline)
    draw.polygon(((15, 33), (18, 20), (31, 16), (47, 21), (52, 33)), fill=(*TEAM_MID, 255), outline=outline)
    draw.polygon(((21, 33), (23, 21), (43, 21), (47, 33)), fill=(*TEAM_LIGHT, 255), outline=outline)
    draw.ellipse((26, 5, 41, 20), fill=skin, outline=outline, width=1)

    if role == "basij":
        draw.pieslice((24, 2, 43, 16), 180, 360, fill=TEAM_DARK, outline=outline)
        draw.rectangle((23, 10, 43, 13), fill=TEAM_DEEP, outline=outline)
        draw.line((4, 31, 59, 9), fill=outline, width=5)
        draw.line((4, 31, 59, 9), fill=(69, 59, 42, 255), width=3)
        draw.rectangle((35, 18, 42, 24), fill=TEAM_DARK, outline=outline)
    elif role == "atgm":
        draw.pieslice((24, 2, 43, 16), 180, 360, fill=TEAM_DARK, outline=outline)
        draw.line((2, 9, 61, 17), fill=outline, width=9)
        draw.line((2, 9, 61, 17), fill=(72, 77, 59, 255), width=6)
        draw.ellipse((1, 6, 10, 15), fill=TEAM_DEEP, outline=outline)
        draw.rectangle((38, 8, 48, 16), fill=TEAM_LIGHT, outline=outline)
        draw.line((43, 16, 51, 31), fill=outline, width=2)
    elif role == "controller":
        draw.pieslice((24, 2, 43, 16), 180, 360, fill=TEAM_DARK, outline=outline)
        draw.arc((22, 4, 45, 23), 185, 355, fill=(25, 30, 29, 255), width=2)
        draw.line((43, 9, 49, 2), fill=(36, 42, 40, 255), width=1)
        draw.ellipse((48, 1, 50, 3), fill=(75, 235, 207, 255))
        draw.rounded_rectangle((37, 20, 58, 32), radius=2, fill=(21, 34, 34, 255), outline=outline)
        draw.rectangle((40, 22, 55, 28), fill=(64, 211, 193, 255))
        draw.line((42, 25, 53, 25), fill=(205, 255, 236, 255), width=1)
    else:
        # Shadow One keeps a broad asymmetric cloak, luminous visor, and long
        # suppressed weapon. The owner can identify this even under cloak alpha.
        draw.polygon(((9, 33), (13, 11), (27, 3), (45, 10), (58, 33)), fill=(37, 46, 43, 255), outline=outline)
        draw.polygon(((22, 5), (31, 1), (43, 6), (42, 18), (25, 18)), fill=TEAM_DEEP, outline=outline)
        draw.line((26, 11, 40, 11), fill=(92, 242, 205, 255), width=2)
        draw.polygon(((11, 33), (18, 16), (32, 19), (29, 33)), fill=TEAM_MID, outline=outline)
        draw.line((4, 29, 60, 15), fill=outline, width=5)
        draw.line((4, 29, 60, 15), fill=(30, 35, 33, 255), width=3)
        draw.rectangle((55, 12, 63, 17), fill=(18, 22, 21, 255), outline=outline)

    return background


def _directional_icon(asset: str, label: str) -> Image.Image:
    """Draw a role-first production portrait instead of shrinking the world sprite.

    Native OpenRA cameos are illustrations, not minimap views. These authored
    three-quarter silhouettes keep the vehicle family readable at 64x48 while
    reserving player-remap colors for clear ownership.
    """
    accents = {
        "irkarr": (190, 130, 64), "irraad": (70, 164, 173),
        "irfajr": (199, 101, 60), "ircoast": (215, 121, 54),
        "irazar": (67, 150, 185), "irtoufan": (68, 167, 143),
        "irmohajer": (70, 169, 172), "irloiter": (194, 93, 62),
        "irpey": (55, 161, 181), "irghadir": (62, 146, 169),
    }
    background, draw = _icon_background(label, accents[asset])
    outline = (5, 8, 7, 255)
    metal = (52, 62, 52, 255)
    metal_light = (91, 102, 79, 255)
    glass = (61, 196, 190, 255)
    hot = (229, 187, 85, 255)

    # A consistent cast shadow seats every machine in the panel.
    draw.ellipse((5, 25, 59, 33), fill=(3, 6, 5, 175))

    if asset == "irkarr":
        # Low, broad MBT with separate hull, turret, cupola, and long gun.
        draw.polygon(((7, 24), (14, 17), (47, 17), (59, 24), (53, 31), (13, 31)), fill=(28, 33, 29, 255), outline=outline)
        draw.line((14, 27, 52, 27), fill=metal_light, width=2)
        draw.polygon(((13, 22), (22, 15), (49, 17), (55, 23), (48, 26), (17, 26)), fill=(*TEAM_MID, 255), outline=outline)
        draw.polygon(((22, 16), (29, 10), (45, 11), (51, 17), (42, 20), (25, 19)), fill=(*TEAM_DEEP, 255), outline=outline)
        draw.line((40, 13, 62, 5), fill=outline, width=4)
        draw.line((40, 13, 62, 5), fill=metal_light, width=2)
        draw.rectangle((31, 7, 38, 12), fill=TEAM_LIGHT, outline=outline)
    elif asset == "irraad":
        # Tracked anti-air chassis with two unmistakable elevated missile pods.
        draw.polygon(((7, 25), (15, 19), (48, 20), (58, 26), (52, 31), (13, 31)), fill=(27, 34, 30, 255), outline=outline)
        draw.polygon(((13, 22), (22, 16), (48, 18), (54, 23), (47, 27), (16, 27)), fill=(*TEAM_MID, 255), outline=outline)
        for x in (24, 38):
            draw.polygon(((x, 18), (x + 3, 3), (x + 12, 5), (x + 10, 20)), fill=(*TEAM_DEEP, 255), outline=outline)
            draw.ellipse((x + 4, 3, x + 10, 7), fill=hot, outline=outline)
            draw.line((x + 5, 9, x + 10, 10), fill=TEAM_LIGHT, width=2)
        draw.rectangle((11, 15, 20, 22), fill=glass, outline=outline)
    elif asset == "irfajr":
        # Wheeled artillery truck carrying a bank of six rocket tubes.
        draw.polygon(((6, 24), (13, 19), (49, 20), (59, 26), (52, 30), (12, 30)), fill=(*TEAM_MID, 255), outline=outline)
        for x in (14, 27, 45, 55):
            draw.ellipse((x - 4, 26, x + 3, 33), fill=(18, 21, 19, 255), outline=outline)
        draw.polygon(((11, 20), (14, 12), (25, 11), (30, 20)), fill=(*TEAM_LIGHT, 255), outline=outline)
        draw.rectangle((15, 14, 23, 18), fill=glass, outline=outline)
        for y in (5, 9, 13):
            draw.line((28, y + 10, 58, y), fill=outline, width=5)
            draw.line((28, y + 10, 58, y), fill=(83, 86, 67, 255), width=3)
        draw.line((54, 4, 61, 2), fill=hot, width=2)
    elif asset == "ircoast":
        # Static coastal launcher with a single oversized sea-skimming missile.
        draw.polygon(((5, 27), (17, 20), (49, 20), (61, 27), (53, 32), (13, 32)), fill=(*TEAM_DEEP, 255), outline=outline)
        draw.rectangle((18, 17, 43, 25), fill=(*TEAM_MID, 255), outline=outline)
        draw.line((13, 23, 52, 5), fill=outline, width=9)
        draw.line((13, 23, 52, 5), fill=(85, 91, 73, 255), width=6)
        draw.polygon(((52, 2), (63, 3), (56, 10)), fill=hot, outline=outline)
        draw.polygon(((30, 13), (36, 5), (39, 14)), fill=TEAM_LIGHT, outline=outline)
        draw.rectangle((8, 20, 16, 26), fill=glass, outline=outline)
    elif asset == "irazar":
        # Fast interceptor: swept delta planform, twin tails, bright canopy.
        draw.polygon(((3, 27), (25, 17), (33, 3), (39, 17), (61, 27), (40, 24), (34, 32), (28, 24)), fill=(*TEAM_MID, 255), outline=outline)
        draw.polygon(((29, 20), (34, 5), (38, 20), (34, 27)), fill=(*TEAM_DEEP, 255), outline=outline)
        draw.polygon(((30, 15), (34, 8), (38, 15)), fill=glass, outline=outline)
        draw.polygon(((25, 20), (21, 9), (28, 17)), fill=TEAM_LIGHT, outline=outline)
        draw.polygon(((42, 20), (48, 9), (47, 22)), fill=TEAM_LIGHT, outline=outline)
    elif asset == "irtoufan":
        # Side-profile gunship with visible cockpit, stub wings, and rotor mast.
        draw.ellipse((10, 13, 48, 29), fill=(*TEAM_MID, 255), outline=outline)
        draw.polygon(((39, 17), (62, 10), (61, 15), (45, 23)), fill=(*TEAM_DEEP, 255), outline=outline)
        draw.polygon(((12, 15), (21, 11), (25, 22), (14, 23)), fill=glass, outline=outline)
        draw.polygon(((24, 23), (11, 31), (38, 27), (51, 31), (43, 22)), fill=TEAM_LIGHT, outline=outline)
        draw.line((30, 13, 30, 7), fill=outline, width=3)
        draw.line((5, 6, 56, 6), fill=outline, width=2)
        draw.line((17, 7, 48, 5), fill=TEAM_LIGHT, width=1)
        draw.line((20, 29, 16, 33), fill=outline, width=2)
        draw.line((40, 28, 46, 33), fill=outline, width=2)
    elif asset == "irmohajer":
        # Long-endurance UAV with high-aspect wing and pusher propeller.
        draw.polygon(((2, 20), (27, 15), (33, 5), (38, 15), (62, 20), (39, 22), (34, 31), (29, 22)), fill=(*TEAM_MID, 255), outline=outline)
        draw.polygon(((29, 18), (34, 7), (38, 18), (34, 27)), fill=(*TEAM_DEEP, 255), outline=outline)
        draw.ellipse((31, 13, 38, 19), fill=glass, outline=outline)
        draw.line((34, 28, 34, 33), fill=hot, width=2)
    elif asset == "irloiter":
        # Compact loitering munition with delta wing and forward sensor nose.
        draw.polygon(((5, 27), (29, 15), (33, 3), (39, 15), (59, 27), (38, 23), (34, 32), (29, 23)), fill=(*TEAM_DEEP, 255), outline=outline)
        draw.polygon(((12, 26), (31, 17), (55, 27), (35, 23)), fill=(*TEAM_MID, 255), outline=outline)
        draw.ellipse((30, 2, 37, 9), fill=hot, outline=outline)
        draw.line((34, 8, 34, 29), fill=TEAM_LIGHT, width=2)
    elif asset == "irpey":
        # Fast attack craft, raked bow, raised cabin, gun, and wake.
        draw.line((3, 30, 56, 30), fill=(66, 178, 194, 210), width=2)
        draw.polygon(((4, 24), (50, 17), (62, 22), (51, 30), (16, 31)), fill=(*TEAM_MID, 255), outline=outline)
        draw.polygon(((16, 20), (25, 12), (43, 13), (49, 19)), fill=(*TEAM_LIGHT, 255), outline=outline)
        draw.rectangle((27, 13, 40, 17), fill=glass, outline=outline)
        draw.ellipse((43, 11, 51, 18), fill=TEAM_DEEP, outline=outline)
        draw.line((48, 13, 61, 7), fill=outline, width=3)
        draw.line((48, 13, 61, 7), fill=metal_light, width=1)
    else:
        # Midget submarine: smooth pressure hull, sail, planes, and periscope.
        draw.ellipse((4, 17, 60, 31), fill=(*TEAM_MID, 255), outline=outline)
        draw.polygon(((18, 22), (34, 7), (44, 9), (49, 22)), fill=(*TEAM_DEEP, 255), outline=outline)
        draw.rectangle((33, 8, 45, 19), fill=TEAM_LIGHT, outline=outline)
        draw.line((38, 8, 38, 3), fill=outline, width=2)
        draw.line((38, 3, 44, 3), fill=metal_light, width=1)
        draw.polygon(((10, 21), (1, 15), (17, 19)), fill=metal_light, outline=outline)
        draw.polygon(((50, 22), (62, 15), (58, 24)), fill=metal_light, outline=outline)

    return background


def build_icon(asset: str, label: str) -> Image.Image:
    if asset in INFANTRY:
        return _infantry_icon(asset, label)

    return _directional_icon(asset, label)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--palette", required=True, type=Path)
    args = parser.parse_args()
    palette = Image.open(args.palette)
    if palette.mode != "P":
        raise ValueError("reference palette must be indexed")
    FRAME_ROOT.mkdir(parents=True, exist_ok=True)

    cache: dict[str, list[Image.Image]] = {}
    for name, role in INFANTRY.items():
        frames = render_infantry(role)
        cache[name] = frames
        save_frames(name, frames, palette)
        # First 264 frames expose every required movement/combat pose.
        sheet(name, frames, columns=16, limit=264)
        print(f"{name}: {len(frames)} authored infantry frames")

    for name, (size, facings) in DIRECTIONAL.items():
        frames = render_directional_asset(name, size, facings)
        cache[name] = frames
        save_frames(name, frames, palette)
        sheet(name, frames)
        print(f"{name}: {len(frames)} true directional frames")

    for name, (model, size, facings, layers) in WRECKS.items():
        live = cache.get(model) or render_directional_asset(model, size, facings)
        frames = [wreck(frame, index) for index, frame in enumerate(live[:facings * layers])]
        save_frames(name, frames, palette)
        sheet(name, frames)
        print(f"{name}: {len(frames)} matching wreck frames")

    for name, (model, size, facings) in SINKS.items():
        frames = sinking_frames(model, size, facings)
        save_frames(name, frames, palette)
        sheet(name, frames, columns=16)
        print(f"{name}: {len(frames)} directional sinking frames")

    rotor = render_rotor()
    save_frames("irtoufanrotor", rotor, palette)
    sheet("irtoufanrotor", rotor, columns=4)

    for name, (kind, size) in EFFECTS.items():
        frames = render_effect(kind, size)
        save_frames(name, frames, palette)
        sheet(name, frames)
        print(f"{name}: {len(frames)} original effect/projectile frames")

    for name, (asset, label) in ICONS.items():
        cameo = build_icon(asset, label)
        output = FRAME_ROOT / name
        output.mkdir(parents=True, exist_ok=True)
        quantize(cameo, palette, opaque=True).save(output / f"{name}-0000.png")
        cameo.save(FRAME_ROOT / f"{name}-review.png")
        print(f"{name}: original 64x48 cameo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
