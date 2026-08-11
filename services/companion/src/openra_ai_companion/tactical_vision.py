from __future__ import annotations

import struct
import zlib

from .models import GameSnapshot


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TERRAIN_COLORS = (
    (78, 91, 68),
    (102, 87, 66),
    (76, 91, 96),
    (118, 105, 72),
    (67, 83, 61),
    (91, 75, 62),
    (81, 88, 104),
    (111, 96, 79),
)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _png_rgb(width: int, height: int, pixels: bytes) -> bytes:
    stride = width * 3
    scanlines = b"".join(b"\0" + pixels[y * stride : (y + 1) * stride] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(scanlines, 6)) + _chunk(b"IEND", b"")


def tactical_overview_png(snapshot: GameSnapshot) -> bytes | None:
    """Render the complete explored battlefield without revealing hidden cells or actors."""
    width = snapshot.map_width
    height = snapshot.map_height
    channels = snapshot.spatial_channels
    expected = width * height * channels * 4
    if width <= 0 or height <= 0 or channels < 9 or len(snapshot.spatial_map) != expected:
        return None

    scale = max(1, min(6, 640 // max(width, height)))
    out_width = width * scale
    out_height = height * scale
    pixels = bytearray(out_width * out_height * 3)

    for cell_y in range(height):
        for cell_x in range(width):
            offset = (cell_y * width + cell_x) * channels * 4
            values = struct.unpack_from(f"<{channels}f", snapshot.spatial_map, offset)
            fog = values[4]
            if fog <= 0:
                color = (5, 7, 11)
            else:
                terrain = max(0, int(values[0]))
                base = TERRAIN_COLORS[terrain % len(TERRAIN_COLORS)]
                height_light = min(24, max(0, int(values[1]) * 3))
                visibility = 1.0 if fog >= 0.99 else 0.62
                color = tuple(min(255, int((component + height_light) * visibility)) for component in base)
                if values[3] < 0.5:
                    color = tuple(component // 2 for component in color)
                if values[2] > 0:
                    density = min(1.0, values[2] / 10.0)
                    color = tuple(int(component * (1 - density) + ore * density) for component, ore in zip(color, (222, 180, 52)))

                if values[5] > 0:
                    color = (72, 224, 224)
                elif values[6] > 0:
                    color = (76, 145, 255)
                elif values[7] > 0:
                    color = (244, 72, 72)
                elif values[8] > 0:
                    color = (255, 146, 55)

            row_pixel = bytes(color) * scale
            out_x = cell_x * scale * 3
            for dy in range(scale):
                row = (cell_y * scale + dy) * out_width * 3
                pixels[row + out_x : row + out_x + scale * 3] = row_pixel

    return _png_rgb(out_width, out_height, bytes(pixels))
