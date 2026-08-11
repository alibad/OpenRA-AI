"""Build the deterministic stylized Bab al-Mandab mission terrain.

The map is a gameplay abstraction: a north-south waterway separates two coasts,
with a central island representing Mayyun.  The script writes only map terrain
and ore density; actors and all tactical events remain in the authored mission.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


WIDTH = 96
HEIGHT = 96
HEADER_SIZE = 17
CLEAR_TEMPLATE = 255
WATER_TEMPLATE = 256
BEACH_TEMPLATE = 439
ORE_TYPE = 1


def is_island(x: int, y: int) -> bool:
    return ((x - 47) / 6.0) ** 2 + ((y - 48) / 11.0) ** 2 <= 1.0


def is_water(x: int, y: int) -> bool:
    western_coast = 24 + (y // 18) % 3
    eastern_coast = 67 - (y // 24) % 2
    return western_coast <= x <= eastern_coast and not is_island(x, y)


def is_beach(x: int, y: int) -> bool:
    if is_water(x, y):
        return False
    return any(
        0 <= nx < WIDTH and 0 <= ny < HEIGHT and is_water(nx, ny)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
    )


def ore_density(x: int, y: int) -> int:
    fields = ((88, 72, 7), (82, 52, 6), (76, 14, 5))
    for center_x, center_y, radius in fields:
        distance = (x - center_x) ** 2 + (y - center_y) ** 2
        if distance <= radius * radius:
            return max(3, 12 - distance // max(1, radius))
    return 0


def build() -> bytes:
    tiles_offset = HEADER_SIZE
    resources_offset = HEADER_SIZE + WIDTH * HEIGHT * 3
    result = bytearray(struct.pack("<BHHIII", 2, WIDTH, HEIGHT, tiles_offset, 0, resources_offset))

    for x in range(WIDTH):
        for y in range(HEIGHT):
            if is_water(x, y):
                template, index = WATER_TEMPLATE, 0
            elif is_beach(x, y):
                template, index = BEACH_TEMPLATE, (x + y) % 6
            else:
                template, index = CLEAR_TEMPLATE, (x * 7 + y * 11) % 16
            result.extend(struct.pack("<HB", template, index))

    for x in range(WIDTH):
        for y in range(HEIGHT):
            density = ore_density(x, y)
            result.extend(struct.pack("<BB", ORE_TYPE if density else 0, density))

    expected = HEADER_SIZE + WIDTH * HEIGHT * 5
    if len(result) != expected:
        raise AssertionError(f"unexpected map.bin size: {len(result)} != {expected}")
    return bytes(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(build())
    print(f"Wrote {args.output} ({args.output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
