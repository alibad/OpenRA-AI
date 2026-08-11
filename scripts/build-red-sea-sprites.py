"""Build deterministic OpenRA SHP frame sources from Red Sea concept art.

The checked-in concept sources use a flat magenta key.  This script isolates
their components, rotates the north-facing masters into ClassicFacing order,
adds a restrained contact shadow, downsamples with crisp pixel-art filtering,
and writes indexed PNG frames for OpenRA.Utility's ``--shp`` command. Every
custom unit uses a true fixed-camera isometric model for all authored
directions; no moving unit rotates a single flat bitmap.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from red_sea_directional_vehicle import render_directional_asset


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "assets" / "red-sea-2026" / "sprite-sources"
ICON_SOURCE_ROOT = ROOT / "assets" / "red-sea-2026" / "icon-sources"
FRAME_ROOT = ROOT / "generated" / "red-sea-sprites"


ASSETS = {
    # Canvas and subject sizes are calibrated against the inherited RA actors:
    # 2TNK 36px, FTRK 36px, JEEP 24px, V2RL 40px, and YAK 40px.  The generated
    # concept art is intentionally high resolution, but the in-game silhouettes
    # must remain within the same visual scale as the original vehicle roster.
    #
    # The M1 chassis source was drawn with its engine deck at the top, so its
    # nose points south while the turret points north.  Correct that 180-degree
    # mismatch before producing the facing ring.
    "m1a2s": {
        "size": 40,
        "directional_model": "m1a2s",
        "facings": 32,
    },
    "sads": {
        "size": 40,
        "directional_model": "sads",
        "facings": 32,
    },
    "tech": {
        "size": 28,
        "directional_model": "tech",
        "facings": 32,
    },
    "ymlr": {
        "size": 40,
        "directional_model": "ymlr",
        "facings": 32,
    },
    "samad": {
        "size": 40,
        "directional_model": "samad",
        "facings": 16,
    },
}


ICONS = {
    "m1a2sicon": {"source": "m1a2s-icon-source-v2.png", "label": "M1A2S"},
    "sadsicon": {"source": "sads-icon-source-v2.png", "label": "AIR DEFENSE"},
    "techicon": {"source": "tech-icon-source-v2.png", "label": "TECHNICAL"},
    "ymlricon": {"source": "ymlr-icon-source-v2.png", "label": "MISSILE"},
    "samadicon": {"source": "samad-icon-source-v2.png", "label": "SAMAD"},
}


EFFECTS = {
    "redsea-m1-impact": {
        "source": "m1-impact-source-v2.png",
        "size": 64,
        "scales": (0.26, 0.48, 0.72, 0.92, 1.00, 1.06, 1.12, 1.18, 1.24),
        "opacities": (255, 255, 255, 255, 235, 205, 165, 105, 50),
        "facings": 1,
    },
    "redsea-m1-muzzle": {
        "source": "m1-muzzle-source-v2.png",
        "size": 48,
        "scales": (0.52, 0.82, 1.00, 0.88, 0.70, 0.50),
        "opacities": (255, 255, 245, 195, 125, 55),
        "facings": 8,
    },
    "redsea-drone-impact": {
        "source": "drone-impact-source-v1.png",
        "size": 64,
        "scales": (0.16, 0.30, 0.49, 0.70, 0.88, 1.00, 1.08, 1.14, 1.18, 1.21, 1.24),
        "opacities": (255, 255, 255, 255, 255, 245, 220, 185, 140, 90, 42),
        "facings": 1,
    },
}


WRECKS = {
    "m1a2shusk": {"model": "m1a2s", "size": 40, "facings": 32, "turret": True},
    "sadshusk": {"model": "sads", "size": 40, "facings": 32, "turret": True},
    "techhusk": {"model": "tech", "size": 28, "facings": 32, "turret": True},
    "ymlrhusk": {"model": "ymlr", "size": 40, "facings": 32, "turret": False},
}


def chroma_alpha(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    red, green, blue, _ = rgba.split()
    # Key by magenta hue instead of exact RGB distance: generated backgrounds
    # can vary from bright pink to darker magenta even when prompted as flat.
    # The source art deliberately contains no magenta, so this produces a much
    # cleaner matte without eroding sand, olive, black, or gray components.
    magenta_dominance = ImageChops.subtract(ImageChops.darker(red, blue), green)
    red_blue_balance = ImageChops.invert(ImageChops.difference(red, blue))
    key_strength = ImageChops.darker(magenta_dominance, red_blue_balance)
    alpha = key_strength.point(
        lambda value: 0 if value >= 80 else 255 if value <= 28 else round((80 - value) * 255 / 52)
    )
    rgba.putalpha(alpha)
    return rgba


def isolate_parts(image: Image.Image, amount: int) -> list[Image.Image]:
    width = image.width // amount
    parts: list[Image.Image] = []
    for index in range(amount):
        left = index * width
        right = image.width if index == amount - 1 else (index + 1) * width
        part = image.crop((left, 0, right, image.height))
        bbox = part.getchannel("A").getbbox()
        if bbox is None:
            raise ValueError(f"part {index} contains no opaque pixels")
        parts.append(part.crop(bbox))

    return parts


def master_component(part: Image.Image, frame_size: int, scale: float) -> Image.Image:
    target = max(8, round(frame_size * scale))
    ratio = min(target / part.width, target / part.height)
    resized = part.resize(
        (max(1, round(part.width * ratio)), max(1, round(part.height * ratio))),
        Image.Resampling.LANCZOS,
    )
    resized = ImageEnhance.Contrast(resized).enhance(1.08)
    resized = ImageEnhance.Sharpness(resized).enhance(1.35)
    return resized


def frame(
    component: Image.Image,
    frame_size: int,
    angle: float,
    shadow: bool = True,
    projection_y: float = 1.0,
) -> Image.Image:
    rotated = component.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
    # Red Alert ground sprites are projected onto an isometric screen plane.
    # Rotating a square top-down master without this projection makes north/
    # south facings look much taller than native vehicles and creates the
    # impression that the sprite changes scale as it turns.
    if projection_y != 1.0:
        rotated = rotated.resize(
            (rotated.width, max(1, round(rotated.height * projection_y))),
            Image.Resampling.LANCZOS,
        )
    canvas = Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0))

    if shadow:
        shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(shadow_layer)
        box_width = max(8, int(rotated.width * 0.70))
        box_height = max(4, int(rotated.height * 0.26))
        x = (frame_size - box_width) // 2 + 2
        y = (frame_size - box_height) // 2 + max(3, rotated.height // 5)
        draw.ellipse((x, y, x + box_width, y + box_height), fill=(0, 0, 0, 105))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(1.1))
        canvas.alpha_composite(shadow_layer)

    x = (frame_size - rotated.width) // 2
    y = (frame_size - rotated.height) // 2
    canvas.alpha_composite(rotated, (x, y))
    return canvas


def quantize_to_reference(image: Image.Image, palette_image: Image.Image) -> Image.Image:
    # Reserve index 0 for transparency.  The source palette is the native RA
    # palette exported by OpenRA.Utility, preserving its expected color space.
    reference = palette_image.copy()
    paletted = image.convert("RGB").quantize(palette=reference, dither=Image.Dither.NONE)
    alpha = image.getchannel("A")
    data = bytearray(paletted.tobytes())
    alpha_data = alpha.tobytes()
    for index, value in enumerate(alpha_data):
        if value < 96:
            data[index] = 0
    paletted.frombytes(bytes(data))
    paletted.info["transparency"] = 0
    return paletted


def quantize_icon_to_reference(image: Image.Image, palette_image: Image.Image) -> Image.Image:
    """Quantize an opaque sidebar cameo without creating transparent holes."""

    paletted = image.convert("RGB").quantize(palette=palette_image.copy(), dither=Image.Dither.NONE)
    data = bytearray(paletted.tobytes())
    # Index zero is transparent in the in-game palette. Native RA cameos never
    # use it, even in their darkest pixels, so map accidental matches to the
    # opaque near-black at palette index 16 used by the extracted packages.
    for index, value in enumerate(data):
        if value == 0:
            data[index] = 16
    paletted.frombytes(bytes(data))
    return paletted


def clear_output_frames(output: Path, name: str) -> None:
    """Remove only stale generated PNG frames for one exact asset prefix."""

    for path in output.glob(f"{name}-[0-9][0-9][0-9][0-9].png"):
        path.unlink()


def save_frames(name: str, definition: dict[str, object], palette: Image.Image) -> None:
    if definition.get("directional_model"):
        save_directional_model(name, definition, palette)
        return

    source = chroma_alpha(Image.open(SOURCE_ROOT / str(definition["source"])))
    parts = isolate_parts(source, int(definition["parts"]))
    frame_size = int(definition["size"])
    scales = tuple(float(value) for value in definition["scales"])
    base_angles = tuple(float(value) for value in definition["base_angles"])
    projection_y = float(definition.get("projection_y", 1.0))
    masters = [master_component(part, frame_size, scales[index]) for index, part in enumerate(parts)]
    output = FRAME_ROOT / name
    output.mkdir(parents=True, exist_ok=True)
    clear_output_frames(output, name)

    images: list[Image.Image] = []
    for part_index, master in enumerate(masters):
        for facing in range(32 if name != "samad" else 16):
            angle = base_angles[part_index] + 360 * facing / (32 if name != "samad" else 16)
            images.append(frame(master, frame_size, angle, projection_y=projection_y))

    for index, result in enumerate(images):
        quantized = quantize_to_reference(result, palette)
        quantized.save(output / f"{name}-{index:04d}.png", transparency=0)

    facing_count = 16 if name == "samad" else 32
    review_indexes = list(range(0, facing_count, max(1, facing_count // 8)))
    if len(masters) > 1:
        review_indexes.extend(facing_count + index for index in tuple(review_indexes))
    columns = 8
    rows = math.ceil(len(review_indexes) / columns)
    contact_sheet = Image.new("RGBA", (columns * frame_size, rows * frame_size), (42, 36, 28, 255))
    for slot, image_index in enumerate(review_indexes):
        contact_sheet.alpha_composite(images[image_index], ((slot % columns) * frame_size, (slot // columns) * frame_size))
    contact_sheet.save(FRAME_ROOT / f"{name}-contact-sheet.png")

    print(f"{name}: {len(images)} frames at {frame_size}x{frame_size}")


def save_directional_model(name: str, definition: dict[str, object], palette: Image.Image) -> None:
    frame_size = int(definition["size"])
    facings = int(definition["facings"])
    model_name = str(definition["directional_model"])
    images = render_directional_asset(model_name, frame_size, facings)

    output = FRAME_ROOT / name
    output.mkdir(parents=True, exist_ok=True)
    clear_output_frames(output, name)
    for index, result in enumerate(images):
        quantized = quantize_to_reference(result, palette)
        quantized.save(output / f"{name}-{index:04d}.png", transparency=0)

    # Show every authored direction, not an eight-frame sample.  This sheet is
    # the review contract that catches duplicated, shrinking, or flat facings.
    columns = 8
    rows = math.ceil(len(images) / columns)
    contact_sheet = Image.new("RGBA", (columns * frame_size, rows * frame_size), (42, 36, 28, 255))
    for index, result in enumerate(images):
        contact_sheet.alpha_composite(result, ((index % columns) * frame_size, (index // columns) * frame_size))
    contact_sheet.save(FRAME_ROOT / f"{name}-contact-sheet.png")

    print(f"{name}: {len(images)} frames at {frame_size}x{frame_size} (true directional model)")


def wreck_frame(image: Image.Image, facing: int, *, turret: bool) -> Image.Image:
    """Turn one live directional render into a deterministic scorched wreck."""

    damaged = ImageEnhance.Color(image.convert("RGBA")).enhance(0.22)
    damaged = ImageEnhance.Brightness(damaged).enhance(0.58 if not turret else 0.52)
    damaged = ImageEnhance.Contrast(damaged).enhance(1.15)

    # The scorch follows the sprite footprint and is clipped by its alpha, so
    # no colored pixels leak into the transparent SHP background.
    burn = Image.new("RGBA", damaged.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(burn)
    width, height = damaged.size
    offset = (facing % 5) - 2
    if turret:
        draw.ellipse(
            (width * 0.32 + offset, height * 0.31, width * 0.70 + offset, height * 0.69),
            fill=(18, 12, 8, 145),
        )
    else:
        draw.ellipse(
            (width * 0.26 + offset, height * 0.38, width * 0.75 + offset, height * 0.74),
            fill=(18, 12, 8, 135),
        )
        draw.point((round(width * 0.47), round(height * 0.52)), fill=(217, 91, 30, 220))
        draw.point((round(width * 0.53), round(height * 0.55)), fill=(242, 151, 48, 205))

    burn.putalpha(ImageChops.multiply(burn.getchannel("A"), damaged.getchannel("A")))
    return Image.alpha_composite(damaged, burn)


def save_wreck_frames(name: str, definition: dict[str, object], palette: Image.Image) -> None:
    frame_size = int(definition["size"])
    facings = int(definition["facings"])
    include_turret = bool(definition["turret"])
    live = render_directional_asset(str(definition["model"]), frame_size, facings)
    bodies = [wreck_frame(frame, index, turret=False) for index, frame in enumerate(live[:facings])]
    turrets = (
        [wreck_frame(frame, index, turret=True) for index, frame in enumerate(live[facings:facings * 2])]
        if include_turret
        else []
    )
    images = bodies + turrets

    output = FRAME_ROOT / name
    output.mkdir(parents=True, exist_ok=True)
    clear_output_frames(output, name)
    for index, result in enumerate(images):
        quantize_to_reference(result, palette).save(output / f"{name}-{index:04d}.png", transparency=0)

    columns = 8
    rows = math.ceil(len(images) / columns)
    contact_sheet = Image.new("RGBA", (columns * frame_size, rows * frame_size), (42, 36, 28, 255))
    for index, result in enumerate(images):
        contact_sheet.alpha_composite(result, ((index % columns) * frame_size, (index // columns) * frame_size))
    contact_sheet.save(FRAME_ROOT / f"{name}-contact-sheet.png")
    print(f"{name}: {len(images)} directional wreck frames at {frame_size}x{frame_size}")


def save_icon_frame(name: str, definition: dict[str, object], palette: Image.Image) -> None:
    source = Image.open(ICON_SOURCE_ROOT / str(definition["source"])).convert("RGB")
    target_ratio = 4 / 3
    if source.width / source.height > target_ratio:
        width = round(source.height * target_ratio)
        left = (source.width - width) // 2
        source = source.crop((left, 0, left + width, source.height))
    elif source.width / source.height < target_ratio:
        height = round(source.width / target_ratio)
        top = (source.height - height) // 2
        source = source.crop((0, top, source.width, top + height))

    cameo = source.resize((64, 48), Image.Resampling.LANCZOS)
    cameo = ImageEnhance.Color(cameo).enhance(0.82)
    cameo = ImageEnhance.Contrast(cameo).enhance(1.12)
    cameo = ImageEnhance.Sharpness(cameo).enhance(1.45).convert("RGBA")

    # Native Red Alert cameos paint a white all-caps label over the bottom of
    # the illustration. Darken only this small band, then render deterministic
    # text using the checked-in UI font so builds are portable.
    shade = Image.new("RGBA", cameo.size, (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    for y in range(34, 48):
        alpha = round(45 + (y - 34) * 12)
        shade_draw.line((0, y, 63, y), fill=(0, 0, 0, min(alpha, 205)))
    cameo.alpha_composite(shade)

    label = str(definition["label"])
    font_path = ROOT / "engine" / "openra" / "mods" / "common" / "FreeSansBold.ttf"
    font_size = 10
    while font_size > 6:
        font = ImageFont.truetype(font_path, font_size)
        bounds = ImageDraw.Draw(cameo).textbbox((0, 0), label, font=font, stroke_width=1)
        if bounds[2] - bounds[0] <= 60:
            break
        font_size -= 1
    draw = ImageDraw.Draw(cameo)
    bounds = draw.textbbox((0, 0), label, font=font, stroke_width=1)
    text_width = bounds[2] - bounds[0]
    draw.text(
        ((64 - text_width) // 2, 37),
        label,
        font=font,
        fill=(245, 245, 236, 255),
        stroke_width=1,
        stroke_fill=(12, 12, 12, 255),
    )

    output = FRAME_ROOT / name
    output.mkdir(parents=True, exist_ok=True)
    clear_output_frames(output, name)
    quantized = quantize_icon_to_reference(cameo, palette)
    quantized.save(output / f"{name}-0000.png")
    cameo.save(FRAME_ROOT / f"{name}-review.png")
    print(f"{name}: 1 opaque production cameo at 64x48")


def effect_frame(
    component: Image.Image,
    frame_size: int,
    angle: float,
    scale: float,
    opacity: int,
) -> Image.Image:
    rotated = component.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
    target = max(4, round(frame_size * 0.90 * scale))
    ratio = target / max(rotated.width, rotated.height)
    art = rotated.resize(
        (max(1, round(rotated.width * ratio)), max(1, round(rotated.height * ratio))),
        Image.Resampling.LANCZOS,
    )
    if opacity < 255:
        art.putalpha(art.getchannel("A").point(lambda value: round(value * opacity / 255)))

    canvas = Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0))
    canvas.alpha_composite(art, ((frame_size - art.width) // 2, (frame_size - art.height) // 2))
    return canvas


def save_effect_frames(name: str, definition: dict[str, object], palette: Image.Image) -> None:
    source = chroma_alpha(Image.open(SOURCE_ROOT / str(definition["source"])))
    component = isolate_parts(source, 1)[0]
    frame_size = int(definition["size"])
    scales = tuple(float(value) for value in definition["scales"])
    opacities = tuple(int(value) for value in definition["opacities"])
    facings = int(definition["facings"])
    if len(scales) != len(opacities):
        raise ValueError(f"{name} scale and opacity phases must match")

    output = FRAME_ROOT / name
    output.mkdir(parents=True, exist_ok=True)
    clear_output_frames(output, name)
    images: list[Image.Image] = []
    for facing in range(facings):
        angle = 360 * facing / facings
        for scale, opacity in zip(scales, opacities, strict=True):
            images.append(effect_frame(component, frame_size, angle, scale, opacity))

    for index, result in enumerate(images):
        quantized = quantize_to_reference(result, palette)
        quantized.save(output / f"{name}-{index:04d}.png", transparency=0)

    columns = len(scales)
    contact_sheet = Image.new("RGBA", (columns * frame_size, facings * frame_size), (42, 36, 28, 255))
    for index, result in enumerate(images):
        contact_sheet.alpha_composite(result, ((index % columns) * frame_size, (index // columns) * frame_size))
    contact_sheet.save(FRAME_ROOT / f"{name}-contact-sheet.png")
    print(f"{name}: {len(images)} frames at {frame_size}x{frame_size}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--palette", type=Path, required=True, help="Paletted PNG exported by OpenRA.Utility")
    args = parser.parse_args()
    palette = Image.open(args.palette)
    if palette.mode != "P":
        raise ValueError("reference palette image must use indexed color")

    for name, definition in ASSETS.items():
        save_frames(name, definition, palette)
    for name, definition in WRECKS.items():
        save_wreck_frames(name, definition, palette)
    for name, definition in ICONS.items():
        save_icon_frame(name, definition, palette)
    for name, definition in EFFECTS.items():
        save_effect_frames(name, definition, palette)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
