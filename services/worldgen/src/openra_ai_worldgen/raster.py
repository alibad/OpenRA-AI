from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import io
from random import Random
from PIL import Image

from .models import GeoSelection, TerrainAnalysis
from .osm import GeoFeature, project_point
from .terrain import TerrainView

LAND = 0
WATER = 1
ROAD = 2
URBAN = 3
FOREST = 4
ROUGH = 5
SAND = 6


@dataclass
class TerrainPlan:
    width: int
    height: int
    cells: list[list[int]]
    spawns: list[tuple[int, int]]
    mines: list[tuple[int, int]]
    roads: set[tuple[int, int]]
    scenery: list[tuple[str, int, int]]
    source_feature_count: int
    feature_counts: dict[str, int]
    tileset: str
    analysis: TerrainAnalysis


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
                and cells[ny][nx] not in {WATER, ROUGH}
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
            if cells[y][x] not in {WATER, ROUGH}:
                candidates.append(((x - tx) ** 2 + (y - ty) ** 2, x, y))
    if not candidates:
        raise ValueError("generation produced no passable land")
    _, x, y = min(candidates)
    return x, y


def _clear_base(cells: list[list[int]], point: tuple[int, int], radius: int = 4) -> None:
    _paint_disk(cells, point[0], point[1], radius, LAND)


def _polygon_cells(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    min_x, max_x = min(x for x, _ in points), max(x for x, _ in points)
    min_y, max_y = min(y for _, y in points), max(y for _, y in points)
    return [
        (x, y)
        for y in range(min_y, max_y + 1)
        for x in range(min_x, max_x + 1)
        if _point_in_polygon(x, y, points)
    ]


def _road_radius(feature: GeoFeature) -> int:
    highway = dict(feature.tags).get("highway", "")
    return 1 if highway in {"motorway", "trunk", "primary"} else 0


def _seed_from_terrain_view(
    cells: list[list[int]],
    view: TerrainView,
    margin: int,
    analysis: TerrainAnalysis,
) -> None:
    """Translate the same terrain pixels shown to vision into a conservative OpenRA grid."""
    with Image.open(io.BytesIO(view.image)) as source:
        image = source.convert("RGB")
    playable = len(cells) - 2 * margin
    for grid_y in range(playable):
        for grid_x in range(playable):
            left = round(grid_x * image.width / playable)
            top = round(grid_y * image.height / playable)
            right = max(left + 1, round((grid_x + 1) * image.width / playable))
            bottom = max(top + 1, round((grid_y + 1) * image.height / playable))
            pixels = list(image.crop((left, top, right, bottom)).getdata())
            count = max(1, len(pixels))
            water = sum(1 for red, green, blue in pixels if blue > 145 and blue > red * 1.10 and blue > green * 1.02) / count
            green_land = sum(1 for red, green, blue in pixels if green > 85 and green > red * 1.08 and green > blue * 1.06) / count
            colored_road = sum(
                1 for red, green, blue in pixels
                if red > 135 and green > 65 and red > green * 1.16 and green > blue * 1.35
            ) / count
            urban_lines = sum(
                1 for red, green, blue in pixels
                if max(red, green, blue) - min(red, green, blue) < 24 and 70 < (red + green + blue) / 3 < 205
            ) / count
            contour = sum(
                1 for red, green, blue in pixels
                if red > 90 and 0.55 < green / max(1, red) < 0.92 and blue < green * 0.82
            ) / count

            value = LAND
            if water >= 0.20:
                value = WATER
            elif colored_road >= 0.045:
                value = ROAD
            elif green_land >= 0.30:
                value = FOREST
            elif analysis.relief in {"rolling", "mountainous"} and contour >= 0.12:
                value = ROUGH
            elif analysis.urban_density >= 0.35 and urban_lines >= 0.055:
                value = URBAN
            elif analysis.biome == "desert":
                value = SAND
            cells[margin + grid_y][margin + grid_x] = value

    # Map labels and transit icons can contain isolated blue pixels. Keep only
    # water shapes large enough to represent a real visible feature.
    seen: set[tuple[int, int]] = set()
    for y in range(margin, len(cells) - margin):
        for x in range(margin, len(cells) - margin):
            if cells[y][x] != WATER or (x, y) in seen:
                continue
            queue = deque([(x, y)])
            seen.add((x, y))
            component: list[tuple[int, int]] = []
            while queue:
                px, py = queue.popleft()
                component.append((px, py))
                for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
                    if 0 <= ny < len(cells) and 0 <= nx < len(cells) and cells[ny][nx] == WATER and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        queue.append((nx, ny))
            if len(component) < 3:
                replacement = SAND if analysis.biome == "desert" else LAND
                for px, py in component:
                    cells[py][px] = replacement


def build_terrain(
    selection: GeoSelection,
    features: list[GeoFeature],
    analysis: TerrainAnalysis | None = None,
    terrain_view: TerrainView | None = None,
) -> TerrainPlan:
    analysis = analysis or TerrainAnalysis()
    size = selection.map_size
    margin = max(4, size // 16)
    lower, upper = margin, size - margin - 1
    rng = Random(selection.seed)
    cells = [[LAND for _ in range(size)] for _ in range(size)]
    roads: set[tuple[int, int]] = set()
    if terrain_view:
        _seed_from_terrain_view(cells, terrain_view, margin, analysis)
        roads.update(
            (x, y)
            for y in range(margin, size - margin)
            for x in range(margin, size - margin)
            if cells[y][x] == ROAD
        )
    projected: list[tuple[GeoFeature, list[tuple[int, int]]]] = []

    for feature in features:
        points = [project_point(lat, lon, selection, lower, upper) for lat, lon in feature.points]
        compact = [point for index, point in enumerate(points) if index == 0 or point != points[index - 1]]
        if len(compact) >= 2:
            projected.append((feature, compact))

    polygon_order = {
        "sand": SAND,
        "forest": FOREST,
        "urban": URBAN,
        "building": URBAN,
        "rough": ROUGH,
        "water": WATER,
    }
    for feature, points in projected:
        if not feature.closed or feature.kind not in polygon_order:
            continue
        value = polygon_order[feature.kind]
        for x, y in _polygon_cells(points):
            cells[y][x] = value

    for feature, points in projected:
        for start, end in zip(points, points[1:]):
            for x, y in _line(start, end):
                if feature.kind in {"water", "river"}:
                    _paint_disk(cells, x, y, 1 if feature.kind == "river" else 2, WATER)
                elif feature.kind == "dry-river":
                    _paint_disk(cells, x, y, 1, ROUGH if analysis.relief != "flat" else SAND)
                elif feature.kind in {"road", "rail"}:
                    radius = _road_radius(feature) if feature.kind == "road" else 0
                    _paint_disk(cells, x, y, radius, ROAD)
                    for yy in range(max(0, y - radius), min(size, y + radius + 1)):
                        for xx in range(max(0, x - radius), min(size, x + radius + 1)):
                            if cells[yy][xx] == ROAD:
                                roads.add((xx, yy))
                elif feature.kind == "local-road" and cells[y][x] not in {WATER, ROAD}:
                    cells[y][x] = URBAN

    if selection.generation_mode == "playability-first":
        # Preserve the street geometry but reclaim small pockets for bases and
        # maneuvering where dense city maps would otherwise become all road.
        for y in range(margin, size - margin):
            for x in range(margin, size - margin):
                if cells[y][x] == ROAD and (x * 3 + y * 5) % 11 == 0:
                    cells[y][x] = URBAN
                    roads.discard((x, y))
    elif selection.generation_mode == "creative-remix":
        accent = SAND if analysis.biome == "desert" else FOREST
        for _ in range(max(3, size // 16)):
            x = rng.randrange(margin + 4, size - margin - 4)
            y = rng.randrange(margin + 4, size - margin - 4)
            if cells[y][x] not in {WATER, ROAD}:
                _paint_disk(cells, x, y, rng.randint(1, 3), accent)

    spawn_targets = [(lower + 7, lower + 7), (upper - 7, upper - 7)]
    spawns = [_nearest_land(cells, target, margin + 2) for target in spawn_targets]
    for spawn in spawns:
        _clear_base(cells, spawn)

    if spawns[1] not in _reachable(cells, spawns[0]):
        for x, y in _line(spawns[0], spawns[1]):
            _paint_disk(cells, x, y, 1, ROAD)
            roads.add((x, y))
        for spawn in spawns:
            _clear_base(cells, spawn)

    mines: list[tuple[int, int]] = []
    for sx, sy in spawns:
        candidates = [(sx + dx, sy + dy) for dx, dy in ((7, 0), (-7, 0), (0, 7), (0, -7), (6, 4), (-6, -4))]
        mine = next(
            ((x, y) for x, y in candidates if margin < x < size - margin and margin < y < size - margin and cells[y][x] not in {WATER, ROUGH}),
            (sx, sy),
        )
        mines.append(mine)
    for mine in mines:
        _clear_base(cells, mine, radius=6)

    tileset = {"desert": "DESERT", "snow": "SNOW"}.get(analysis.biome, "TEMPERAT")
    scenery: list[tuple[str, int, int]] = []
    building_actor = "v20" if tileset == "DESERT" else "v01"
    building_points: list[tuple[int, int]] = []
    for feature, points in projected:
        if feature.kind == "building" and feature.closed:
            building_points.append((round(sum(x for x, _ in points) / len(points)), round(sum(y for _, y in points) / len(points))))
    if not building_points and analysis.urban_density >= 0.25:
        building_points.extend(
            (x, y)
            for y in range(margin + 2, size - margin - 2)
            for x in range(margin + 2, size - margin - 2)
            if cells[y][x] == URBAN and any(
                cells[ny][nx] == ROAD
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
            )
        )
    rng.shuffle(building_points)
    occupied: list[tuple[int, int]] = []
    max_buildings = max(4, min(45, round(size * analysis.urban_density / 1.8)))
    for x, y in building_points:
        if len(scenery) >= max_buildings:
            break
        if any((x - px) ** 2 + (y - py) ** 2 < 12 for px, py in occupied + spawns + mines):
            continue
        if margin + 2 <= x < size - margin - 2 and margin + 2 <= y < size - margin - 2 and cells[y][x] != WATER:
            scenery.append((building_actor, x, y))
            occupied.append((x, y))

    tree_actor = "t04" if tileset == "DESERT" else "t01"
    forest_cells = [(x, y) for y in range(margin, size - margin) for x in range(margin, size - margin) if cells[y][x] == FOREST]
    rng.shuffle(forest_cells)
    max_trees = min(55, round(len(forest_cells) * max(0.04, analysis.vegetation_density) / 8))
    for x, y in forest_cells:
        if max_trees <= 0:
            break
        if any((x - px) ** 2 + (y - py) ** 2 < 10 for _, px, py in scenery) or any((x - px) ** 2 + (y - py) ** 2 < 28 for px, py in spawns):
            continue
        scenery.append((tree_actor, x, y))
        max_trees -= 1

    return TerrainPlan(
        size,
        size,
        cells,
        spawns,
        mines,
        roads,
        scenery,
        len(features),
        dict(Counter(feature.kind for feature in features)),
        tileset,
        analysis,
    )
