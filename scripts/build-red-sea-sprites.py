"""Build deterministic OpenRA SHP frame sources from Red Sea concept art.

The checked-in concept sources use a flat magenta key.  This script isolates
their components, rotates the north-facing masters into ClassicFacing order,
adds a restrained contact shadow, downsamples with crisp pixel-art filtering,
and writes indexed PNG frames for OpenRA.Utility's ``--shp`` command.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "assets" / "red-sea-2026" / "sprite-sources"
FRAME_ROOT = ROOT / "generated" / "red-sea-sprites"


ASSETS = {
    "m1a2s": {"source": "m1a2s-source.png", "parts": 2, "size": 56, "scales": (0.86, 0.66)},
    "sads": {"source": "sads-source.png", "parts": 2, "size": 58, "scales": (0.88, 0.68)},
    "tech": {"source": "tech-source.png", "parts": 2, "size": 50, "scales": (0.88, 0.58)},
    "ymlr": {"source": "ymlr-source.png", "parts": 2, "size": 58, "scales": (0.90, 0.90)},
    "samad": {"source": "samad-source.png", "parts": 1, "size": 58, "scales": (0.90,)},
}


def chroma_alpha(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, _ = pixels[x, y]
            # Generated backgrounds vary by a few values around pure magenta.
            magenta_distance = math.sqrt((255 - r) ** 2 + g**2 + (255 - b) ** 2)
            alpha = max(0, min(255, int((magenta_distance - 8) * 8)))
            pixels[x, y] = (r, g, b, alpha)

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


def frame(component: Image.Image, frame_size: int, angle: float, shadow: bool = True) -> Image.Image:
    rotated = component.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
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


def icon(component: Image.Image, frame_size: int) -> Image.Image:
    icon_canvas = Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0))
    art = component.copy()
    target = int(frame_size * 0.78)
    ratio = min(target / art.width, target / art.height)
    art = art.resize((max(1, round(art.width * ratio)), max(1, round(art.height * ratio))), Image.Resampling.LANCZOS)
    icon_canvas.alpha_composite(art, ((frame_size - art.width) // 2, (frame_size - art.height) // 2))
    return icon_canvas


def quantize_to_reference(image: Image.Image, palette_image: Image.Image) -> Image.Image:
    # Reserve index 0 for transparency.  The source palette is the native RA
    # palette exported by OpenRA.Utility, preserving its expected color space.
    reference = palette_image.copy()
    paletted = image.convert("RGB").quantize(palette=reference, dither=Image.Dither.FLOYDSTEINBERG)
    alpha = image.getchannel("A")
    data = bytearray(paletted.tobytes())
    alpha_data = alpha.tobytes()
    for index, value in enumerate(alpha_data):
        if value < 96:
            data[index] = 0
    paletted.frombytes(bytes(data))
    paletted.info["transparency"] = 0
    return paletted


def save_frames(name: str, definition: dict[str, object], palette: Image.Image) -> None:
    source = chroma_alpha(Image.open(SOURCE_ROOT / str(definition["source"])))
    parts = isolate_parts(source, int(definition["parts"]))
    frame_size = int(definition["size"])
    scales = tuple(float(value) for value in definition["scales"])
    masters = [master_component(part, frame_size, scales[index]) for index, part in enumerate(parts)]
    output = FRAME_ROOT / name
    output.mkdir(parents=True, exist_ok=True)

    images: list[Image.Image] = []
    for master in masters:
        for facing in range(32 if name != "samad" else 16):
            images.append(frame(master, frame_size, 360 * facing / (32 if name != "samad" else 16)))

    images.append(icon(masters[0], frame_size))
    for index, result in enumerate(images):
        quantized = quantize_to_reference(result, palette)
        quantized.save(output / f"{name}-{index:04d}.png", transparency=0)

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
