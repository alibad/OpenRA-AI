"""Build every original Iran faction SHP source and visual audit sheet."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from iran_directional_assets import (
    render_directional_asset,
    render_effect,
    render_infantry,
    render_rotor,
)


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
    if opaque:
        for index, value in enumerate(data):
            if value == 0:
                data[index] = 16
    else:
        alpha = image.getchannel("A").tobytes()
        for index, value in enumerate(alpha):
            if value < 96:
                data[index] = 0
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
    if asset in INFANTRY:
        frames = render_infantry(INFANTRY[asset], 32)
        source = frames[0]
    else:
        size, facings = DIRECTIONAL[asset]
        frames = render_directional_asset(asset, size, facings)
        # Compose hull/turret layers for layered assets.
        source = frames[0]
        if asset in {"irkarr", "irraad", "irfajr", "ircoast"}:
            source = Image.alpha_composite(source, frames[32])
        elif asset == "irpey":
            source = Image.alpha_composite(source, frames[16])
    bbox = source.getchannel("A").getbbox()
    return source.crop(bbox) if bbox else source


def build_icon(asset: str, label: str) -> Image.Image:
    source = icon_source(asset)
    background = Image.new("RGBA", (64, 48), (28, 48, 37, 255))
    draw = ImageDraw.Draw(background)
    for y in range(34):
        shade = 36 + y
        draw.line((0, y, 63, y), fill=(shade // 2, shade, shade * 2 // 3, 255))
    scale = min(52 / source.width, 34 / source.height)
    art = source.resize((max(1, round(source.width * scale)), max(1, round(source.height * scale))), Image.Resampling.NEAREST)
    background.alpha_composite(art, ((64 - art.width) // 2, max(0, 31 - art.height)))
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
    return background


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
