from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from random import Random

from .models import GeoSelection
from .osm import GeoFeature, project_point

LAND = 0
WATER = 1
ROAD = 2


@dataclass
class TerrainPlan:
    width: int
    height: int
    cells: list[list[int]]
    spawns: list[tuple[int, int]]
    mines: list[tuple[int, int]]
    roads: set[tuple[int, int]]
    source_feature_count: int


def _line(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    result: list[tuple[int, int]] = []
    while True:
        result.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return result
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _point_in_polygon(x: int, y: int, points: list[tuple[int, int]]) -> bool:
    inside = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        if ((yi > y) != (yj > y)) and x < (xj - xi) * (y - yi) / (yj - yi or 1) + xi:
            inside = not inside
        j = i
    return inside


def _paint_disk(cells: list[list[int]], x: int, y: int, radius: int, value: int) -> None:
    for yy in range(max(0, y - radius), min(len(cells), y + radius + 1)):
        for xx in range(max(0, x - radius), min(len(cells[0]), x + radius + 1)):
            if (xx - x) ** 2 + (yy - y) ** 2 <= radius * radius:
                cells[yy][xx] = value


def _reachable(cells: list[list[int]], start: tuple[int, int]) -> set[tuple[int, int]]:
    queue = deque([start])
    seen = {start}
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (
                0 <= ny < len(cells)
                and 0 <= nx < len(cells[0])
                and cells[ny][nx] != WATER
                and (nx, ny) not in seen
            ):
                seen.add((nx, ny))
                queue.append((nx, ny))
    return seen


def _nearest_land(cells: list[list[int]], target: tuple[int, int], margin: int) -> tuple[int, int]:
    tx, ty = target
    candidates: list[tuple[int, int, int]] = []
    for y in range(margin, len(cells) - margin):
        for x in range(margin, len(cells[0]) - margin):
            if cells[y][x] != WATER:
                candidates.append(((x - tx) ** 2 + (y - ty) ** 2, x, y))
    if not candidates:
        raise ValueError("generation produced no passable land")
    _, x, y = min(candidates)
    return x, y


def _clear_base(cells: list[list[int]], point: tuple[int, int], radius: int = 4) -> None:
    _paint_disk(cells, point[0], point[1], radius, LAND)


def _synthetic_water(cells: list[list[int]], rng: Random, margin: int) -> None:
    width = len(cells[0])
    height = len(cells)
    if rng.random() < 0.5:
        center = rng.randint(width // 3, 2 * width // 3)
        for y in range(margin, height - margin):
            x = center + round(5 * __import__("math").sin((y + rng.random()) / 8))
            _paint_disk(cells, x, y, 1, WATER)
    else:
        edge = rng.choice(("north", "south", "east", "west"))
        depth = rng.randint(7, 13)
        for y in range(margin, height - margin):
            for x in range(margin, width - margin):
                noise = rng.randint(-2, 2)
                if (
                    (edge == "north" and y < margin + depth + noise)
                    or (edge == "south" and y >= height - margin - depth + noise)
                    or (edge == "west" and x < margin + depth + noise)
                    or (edge == "east" and x >= width - margin - depth + noise)
                ):
                    cells[y][x] = WATER


def build_terrain(selection: GeoSelection, features: list[GeoFeature]) -> TerrainPlan:
    size = selection.map_size
    margin = max(4, size // 16)
    lower, upper = margin, size - margin - 1
    rng = Random(selection.seed)
    cells = [[LAND for _ in range(size)] for _ in range(size)]
    roads: set[tuple[int, int]] = set()

    water_features = [f for f in features if f.kind in {"water", "river"}]
    if not water_features:
        _synthetic_water(cells, rng, margin)

    projected: list[tuple[GeoFeature, list[tuple[int, int]]]] = []
    for feature in features:
        points = [project_point(lat, lon, selection, lower, upper) for lat, lon in feature.points]
        compact = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
        if len(compact) >= 2:
            projected.append((feature, compact))

    for feature, points in projected:
        if feature.kind != "water" or not feature.closed:
            continue
        min_x, max_x = min(x for x, _ in points), max(x for x, _ in points)
        min_y, max_y = min(y for _, y in points), max(y for _, y in points)
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                if _point_in_polygon(x, y, points):
                    cells[y][x] = WATER

    for feature, points in projected:
        for start, end in zip(points, points[1:]):
            for x, y in _line(start, end):
                if feature.kind in {"water", "river"}:
                    _paint_disk(cells, x, y, 1 if feature.kind == "river" else 2, WATER)
                elif feature.kind == "road":
                    roads.add((x, y))
                    if cells[y][x] != WATER:
                        cells[y][x] = ROAD

    spawn_targets = [(lower + 7, lower + 7), (upper - 7, upper - 7)]
    spawns = [_nearest_land(cells, target, margin + 2) for target in spawn_targets]
    for spawn in spawns:
        _clear_base(cells, spawn)

    reachable = _reachable(cells, spawns[0])
    if spawns[1] not in reachable:
        # A readable causeway is preferable to silently emitting an unwinnable map.
        for x, y in _line(spawns[0], spawns[1]):
            _paint_disk(cells, x, y, 1, ROAD)
            roads.add((x, y))
        for spawn in spawns:
            _clear_base(cells, spawn)

    mines: list[tuple[int, int]] = []
    for sx, sy in spawns:
        candidates = [
            (sx + dx, sy + dy)
            for dx, dy in ((7, 0), (-7, 0), (0, 7), (0, -7), (6, 4), (-6, -4))
        ]
        mine = next(
            ((x, y) for x, y in candidates if margin < x < size - margin and margin < y < size - margin and cells[y][x] != WATER),
            (sx, sy),
        )
        mines.append(mine)

    # Reserve equivalent harvesting space around both starts. This is a game
    # readability repair, not an attempt to reproduce the source literally.
    for mine in mines:
        _clear_base(cells, mine, radius=6)

    return TerrainPlan(size, size, cells, spawns, mines, roads, len(features))
