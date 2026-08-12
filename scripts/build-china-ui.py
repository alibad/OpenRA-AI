"""Build deterministic HiDPI Saudi, Yemen, and China faction flags."""

from __future__ import annotations

import math
import argparse
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
UIBITS = ROOT / "engine" / "openra" / "mods" / "ra" / "uibits"


def saudi(draw: ImageDraw.ImageDraw, scale: int) -> None:
    x, y, w, h = 226 * scale, 1 * scale, 30 * scale, 15 * scale
    draw.rectangle((x, y, x + w - 1, y + h - 1), fill=(0, 108, 53, 255))
    stroke = max(1, scale)
    draw.line((x + 5 * scale, y + 5 * scale, x + 24 * scale, y + 5 * scale), fill="white", width=stroke)
    draw.line((x + 8 * scale, y + 8 * scale, x + 23 * scale, y + 8 * scale), fill="white", width=stroke)
    draw.line((x + 8 * scale, y + 11 * scale, x + 23 * scale, y + 11 * scale), fill="white", width=stroke)


def yemen(draw: ImageDraw.ImageDraw, scale: int) -> None:
    x, y, w, band = 226 * scale, 17 * scale, 30 * scale, 5 * scale
    draw.rectangle((x, y, x + w - 1, y + band - 1), fill=(206, 17, 38, 255))
    draw.rectangle((x, y + band, x + w - 1, y + 2 * band - 1), fill=(255, 255, 255, 255))
    draw.rectangle((x, y + 2 * band, x + w - 1, y + 3 * band - 1), fill=(0, 0, 0, 255))


def china(draw: ImageDraw.ImageDraw, scale: int, selector_y: int) -> None:
    x, y, w, h = 226 * scale, selector_y * scale, 30 * scale, 15 * scale
    draw.rectangle((x, y, x + w - 1, y + h - 1), fill=(222, 41, 16, 255))
    # Five deterministic stars at each density; coordinates are centered in the
    # stock 30x15 selector region and remain legible at 1x.
    gold = (255, 222, 0, 255)
    points = ((5, 4, 2.2), (10, 2, 1.0), (12, 5, 1.0), (12, 9, 1.0), (9, 11, 1.0))
    for sx, sy, radius in points:
        polygon = []
        for index in range(10):
            angle = math.radians(-90 + index * 36)
            r = radius * scale * (1 if index % 2 == 0 else 0.42)
            polygon.append((x + sx * scale + math.cos(angle) * r, y + sy * scale + math.sin(angle) * r))
        draw.polygon(polygon, fill=gold)


def main(engine_root: Path | None = None) -> int:
    uibits = (engine_root / "mods" / "ra" / "uibits") if engine_root else UIBITS
    chrome = (uibits.parent / "chrome.yaml").read_text(encoding="utf-8")
    marker = "\t\tchina: 226, "
    selector_y = int(chrome.split(marker, 1)[1].split(",", 1)[0])
    for suffix in ("", "-2x", "-3x"):
        output = uibits / f"glyphs-redsea{suffix}.png"
        source = output if output.exists() else uibits / f"glyphs{suffix}.png"
        atlas = Image.open(source).convert("RGBA")
        scale = atlas.width // 256
        required_height = (selector_y + 15) * scale
        if atlas.height < required_height:
            expanded = Image.new("RGBA", (atlas.width, required_height), (0, 0, 0, 0))
            expanded.paste(atlas, (0, 0))
            atlas = expanded
        draw = ImageDraw.Draw(atlas)
        saudi(draw, scale)
        yemen(draw, scale)
        china(draw, scale, selector_y)
        atlas.save(output, optimize=True)
        print(output)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", type=Path)
    args = parser.parse_args()
    raise SystemExit(main(args.engine_root))
