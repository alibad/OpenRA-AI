"""Build deterministic HiDPI Red Sea faction flags for the OpenRA chrome atlas."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
UIBITS = ROOT / "engine" / "openra" / "mods" / "ra" / "uibits"


def draw_saudi_flag(draw: ImageDraw.ImageDraw, scale: int) -> None:
    x, y, width, height = 226 * scale, 1 * scale, 30 * scale, 15 * scale
    draw.rectangle((x, y, x + width - 1, y + height - 1), fill=(0, 108, 53, 255))

    # At native UI size the shahada reads as a restrained two-line white mark,
    # matching the abstraction level of the stock 30x15 country flags. The
    # sword remains independently legible at 1x, 2x, and 3x.
    stroke = max(1, scale)
    draw.line((x + 5 * scale, y + 5 * scale, x + 24 * scale, y + 5 * scale), fill="white", width=stroke)
    for offset in (7, 10, 14, 18, 22):
        draw.line(
            (x + offset * scale, y + 3 * scale, x + (offset + 1) * scale, y + 6 * scale),
            fill="white",
            width=stroke,
        )
    draw.line((x + 8 * scale, y + 8 * scale, x + 23 * scale, y + 8 * scale), fill="white", width=stroke)
    draw.line((x + 8 * scale, y + 11 * scale, x + 23 * scale, y + 11 * scale), fill="white", width=stroke)
    draw.line((x + 7 * scale, y + 10 * scale, x + 9 * scale, y + 12 * scale), fill="white", width=stroke)
    draw.line((x + 23 * scale, y + 11 * scale, x + 25 * scale, y + 10 * scale), fill="white", width=stroke)


def draw_yemen_flag(draw: ImageDraw.ImageDraw, scale: int) -> None:
    x, y, width, band = 226 * scale, 17 * scale, 30 * scale, 5 * scale
    draw.rectangle((x, y, x + width - 1, y + band - 1), fill=(206, 17, 38, 255))
    draw.rectangle((x, y + band, x + width - 1, y + 2 * band - 1), fill=(255, 255, 255, 255))
    draw.rectangle((x, y + 2 * band, x + width - 1, y + 3 * band - 1), fill=(0, 0, 0, 255))


def build_density(scale: int) -> Path:
    suffix = "" if scale == 1 else f"-{scale}x"
    source = UIBITS / f"glyphs{suffix}.png"
    output = UIBITS / f"glyphs-redsea{suffix}.png"
    atlas = Image.open(source).convert("RGBA")
    expected = 256 * scale
    # The upstream file named glyphs-3x.png currently carries a 1024px canvas,
    # while ChromeProvider intentionally addresses it at density 3. Preserve
    # that source canvas and only require enough room for density-scaled regions.
    if atlas.width < expected or atlas.height < expected:
        raise ValueError(f"unexpected {source.name} dimensions: {atlas.size}")

    draw = ImageDraw.Draw(atlas)
    draw_saudi_flag(draw, scale)
    draw_yemen_flag(draw, scale)
    atlas.save(output, optimize=True)
    return output


def main() -> int:
    for scale in (1, 2, 3):
        output = build_density(scale)
        print(output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
