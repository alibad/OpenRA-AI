"""Deterministic isometric vehicle renderer for Red Sea 2026 sprites.

OpenRA ground vehicles need real directional geometry.  Rotating a single
top-down bitmap produces a flat "cardboard" turn, so this module renders the
hull and turret as separate low-poly models from the same fixed orthographic
camera for every facing.  The high-resolution renders are reduced to the
native Red Alert canvas by the asset builder.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter


Vec3 = tuple[float, float, float]
Color = tuple[int, int, int]


@dataclass(frozen=True)
class Face:
    vertices: tuple[Vec3, ...]
    normal: Vec3
    color: Color
    outline: bool = True


def _normal(vertices: tuple[Vec3, ...]) -> Vec3:
    a, b, c = vertices[:3]
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    length = math.sqrt(sum(value * value for value in cross)) or 1.0
    return tuple(value / length for value in cross)  # type: ignore[return-value]


class Mesh:
    def __init__(self) -> None:
        self.faces: list[Face] = []

    def polygon(self, vertices: Iterable[Vec3], color: Color, *, outline: bool = True) -> None:
        points = tuple(vertices)
        self.faces.append(Face(points, _normal(points), color, outline))

    def box(
        self,
        x0: float,
        x1: float,
        y0: float,
        y1: float,
        z0: float,
        z1: float,
        color: Color,
        *,
        outline: bool = True,
    ) -> None:
        p000 = (x0, y0, z0)
        p100 = (x1, y0, z0)
        p110 = (x1, y1, z0)
        p010 = (x0, y1, z0)
        p001 = (x0, y0, z1)
        p101 = (x1, y0, z1)
        p111 = (x1, y1, z1)
        p011 = (x0, y1, z1)
        self.polygon((p000, p010, p110, p100), color, outline=outline)
        self.polygon((p000, p100, p101, p001), color, outline=outline)
        self.polygon((p100, p110, p111, p101), color, outline=outline)
        self.polygon((p110, p010, p011, p111), color, outline=outline)
        self.polygon((p010, p000, p001, p011), color, outline=outline)
        self.polygon((p001, p101, p111, p011), color, outline=outline)

    def tapered_box(
        self,
        bottom: tuple[float, float, float, float, float],
        top: tuple[float, float, float, float, float],
        color: Color,
    ) -> None:
        bx0, bx1, by0, by1, bz = bottom
        tx0, tx1, ty0, ty1, tz = top
        b = ((bx0, by0, bz), (bx1, by0, bz), (bx1, by1, bz), (bx0, by1, bz))
        t = ((tx0, ty0, tz), (tx1, ty0, tz), (tx1, ty1, tz), (tx0, ty1, tz))
        self.polygon((b[0], b[3], b[2], b[1]), color)
        self.polygon((b[0], b[1], t[1], t[0]), color)
        self.polygon((b[1], b[2], t[2], t[1]), color)
        self.polygon((b[2], b[3], t[3], t[2]), color)
        self.polygon((b[3], b[0], t[0], t[3]), color)
        self.polygon(t, color)

    def cylinder_x(
        self,
        center: Vec3,
        length: float,
        radius: float,
        color: Color,
        *,
        segments: int = 10,
    ) -> None:
        cx, cy, cz = center
        x0, x1 = cx - length / 2, cx + length / 2
        left: list[Vec3] = []
        right: list[Vec3] = []
        for index in range(segments):
            angle = 2 * math.pi * index / segments
            y = cy + radius * math.cos(angle)
            z = cz + radius * math.sin(angle)
            left.append((x0, y, z))
            right.append((x1, y, z))
        self.polygon(tuple(reversed(left)), color)
        self.polygon(tuple(right), color)
        for index in range(segments):
            following = (index + 1) % segments
            self.polygon((left[index], right[index], right[following], left[following]), color, outline=False)

    def cylinder_y(
        self,
        center: Vec3,
        length: float,
        radius: float,
        color: Color,
        *,
        segments: int = 8,
    ) -> None:
        cx, cy, cz = center
        y0, y1 = cy - length / 2, cy + length / 2
        front: list[Vec3] = []
        rear: list[Vec3] = []
        for index in range(segments):
            angle = 2 * math.pi * index / segments
            x = cx + radius * math.cos(angle)
            z = cz + radius * math.sin(angle)
            front.append((x, y0, z))
            rear.append((x, y1, z))
        self.polygon(tuple(reversed(front)), color)
        self.polygon(tuple(rear), color)
        for index in range(segments):
            following = (index + 1) % segments
            self.polygon((front[index], front[following], rear[following], rear[index]), color, outline=False)

    def cylinder_z(
        self,
        center: Vec3,
        height: float,
        radius: float,
        color: Color,
        *,
        segments: int = 10,
    ) -> None:
        cx, cy, cz = center
        z0, z1 = cz - height / 2, cz + height / 2
        bottom: list[Vec3] = []
        top: list[Vec3] = []
        for index in range(segments):
            angle = 2 * math.pi * index / segments
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            bottom.append((x, y, z0))
            top.append((x, y, z1))
        self.polygon(tuple(reversed(bottom)), color)
        self.polygon(tuple(top), color)
        for index in range(segments):
            following = (index + 1) % segments
            self.polygon((bottom[index], bottom[following], top[following], top[index]), color, outline=False)

    def slanted_box_y(
        self,
        x0: float,
        x1: float,
        y0: float,
        y1: float,
        z0: float,
        z1: float,
        height: float,
        color: Color,
    ) -> None:
        """Add a rectangular beam whose center rises from y0/z0 to y1/z1."""

        bottom = ((x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1))
        top = tuple((x, y, z + height) for x, y, z in bottom)
        self.polygon(tuple(reversed(bottom)), color)
        self.polygon((bottom[0], bottom[1], top[1], top[0]), color)
        self.polygon((bottom[1], bottom[2], top[2], top[1]), color)
        self.polygon((bottom[2], bottom[3], top[3], top[2]), color)
        self.polygon((bottom[3], bottom[0], top[0], top[3]), color)
        self.polygon(top, color)


SAND = (190, 155, 88)
SAND_LIGHT = (211, 178, 105)
SAND_DARK = (137, 109, 61)
TRACK = (48, 43, 34)
RUBBER = (37, 35, 31)
STEEL = (72, 68, 54)
GRILLE = (49, 45, 36)
GLASS = (41, 61, 56)
LAMP = (235, 206, 112)
OLIVE = (116, 112, 70)
OLIVE_LIGHT = (145, 138, 83)
OLIVE_DARK = (72, 72, 48)
METAL = (78, 76, 65)
RED = (168, 58, 38)


def _m1_hull() -> Mesh:
    mesh = Mesh()

    # Full-depth tracks establish a large, stable Abrams footprint.
    mesh.box(-1.34, -0.91, -2.05, 1.93, 0.08, 0.77, TRACK)
    mesh.box(0.91, 1.34, -2.05, 1.93, 0.08, 0.77, TRACK)
    for y in (-1.62, -0.88, -0.14, 0.60, 1.34):
        mesh.cylinder_x((0, y, 0.39), 2.76, 0.30, RUBBER)
        mesh.cylinder_x((0, y, 0.39), 2.82, 0.13, SAND_DARK)

    # Tread blocks remain readable in north/south views and on the upper run.
    for y in tuple(-1.94 + index * 0.30 for index in range(14)):
        mesh.box(-1.37, -0.88, y, y + 0.10, 0.72, 0.82, STEEL, outline=False)
        mesh.box(0.88, 1.37, y, y + 0.10, 0.72, 0.82, STEEL, outline=False)

    mesh.box(-1.02, 1.02, -1.78, 1.67, 0.47, 0.78, SAND_DARK)
    mesh.tapered_box(
        (-1.06, 1.06, -1.74, 1.66, 0.70),
        (-0.91, 0.91, -1.23, 1.48, 1.13),
        SAND,
    )

    # Segmented side skirts make side-on motion visually unambiguous.
    for x0, x1 in ((-1.39, -1.03), (1.03, 1.39)):
        for y0 in (-1.72, -0.92, -0.12, 0.68):
            mesh.box(x0, x1, y0, y0 + 0.72, 0.48, 0.94, SAND, outline=True)

    # Rear engine deck and vents differentiate front from rear at every angle.
    mesh.box(-0.82, 0.82, 0.72, 1.51, 1.08, 1.17, SAND_DARK)
    for x0 in (-0.70, -0.35, 0.00, 0.35):
        mesh.box(x0, x0 + 0.22, 0.88, 1.38, 1.16, 1.20, GRILLE, outline=False)
    mesh.box(-0.62, 0.62, -0.36, 0.35, 1.11, 1.16, SAND_LIGHT)
    mesh.box(-0.48, 0.48, -1.18, -0.70, 1.09, 1.15, SAND_LIGHT)

    # Front lamps and dark rear exhaust blocks provide strong facing cues.
    for x in (-0.72, 0.59):
        mesh.box(x, x + 0.13, -1.82, -1.68, 0.78, 0.91, LAMP, outline=False)
    for x in (-0.76, 0.56):
        mesh.box(x, x + 0.20, 1.60, 1.75, 0.64, 0.82, GRILLE, outline=False)
    return mesh


def _m1_turret() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, -0.06, 1.18), 0.12, 0.74, SAND_DARK)

    footprint = (
        (-0.58, -1.03),
        (0.58, -1.03),
        (0.91, -0.56),
        (0.88, 0.62),
        (0.56, 0.96),
        (-0.56, 0.96),
        (-0.88, 0.62),
        (-0.91, -0.56),
    )
    bottom = tuple((x, y, 1.18) for x, y in footprint)
    top = tuple((x * 0.89, y * 0.88 - 0.02, 1.62) for x, y in footprint)
    mesh.polygon(tuple(reversed(bottom)), SAND)
    for index in range(len(footprint)):
        following = (index + 1) % len(footprint)
        mesh.polygon((bottom[index], bottom[following], top[following], top[index]), SAND)
    mesh.polygon(top, SAND_LIGHT)

    # Rear bustle, hatches, optics, and smoke launchers survive downsampling.
    mesh.box(-0.72, 0.72, 0.62, 1.15, 1.28, 1.56, SAND_DARK)
    mesh.box(-0.59, 0.59, 0.98, 1.18, 1.35, 1.52, GRILLE, outline=False)
    mesh.cylinder_z((-0.34, 0.03, 1.67), 0.08, 0.25, SAND_DARK, segments=8)
    mesh.cylinder_z((0.34, 0.18, 1.67), 0.08, 0.23, SAND_DARK, segments=8)
    mesh.box(0.18, 0.42, -0.43, -0.15, 1.61, 1.76, GLASS)
    for x in (-0.88, 0.76):
        for y in (-0.48, -0.25, -0.02):
            mesh.cylinder_y((x, y, 1.49), 0.20, 0.065, STEEL, segments=6)

    # A segmented 120 mm cannon yields correct per-angle foreshortening.
    mesh.box(-0.28, 0.28, -1.22, -0.84, 1.38, 1.65, SAND_DARK)
    mesh.cylinder_y((0, -1.72, 1.54), 1.18, 0.095, SAND_LIGHT)
    mesh.cylinder_y((0, -2.43, 1.54), 0.34, 0.12, SAND_DARK)
    mesh.cylinder_y((0, -2.83, 1.54), 0.48, 0.075, STEEL)
    mesh.cylinder_y((0, -3.09, 1.54), 0.14, 0.12, GRILLE)
    return mesh


def _sads_hull() -> Mesh:
    mesh = Mesh()
    for y in (-1.38, 1.18):
        mesh.cylinder_x((0, y, 0.35), 2.30, 0.34, RUBBER, segments=10)
        mesh.cylinder_x((0, y, 0.35), 2.38, 0.15, SAND_DARK, segments=8)
    mesh.box(-0.92, 0.92, -1.62, 1.57, 0.42, 0.66, SAND_DARK)
    mesh.box(-0.91, 0.91, 0.02, 1.42, 0.63, 0.88, SAND)
    mesh.tapered_box(
        (-0.88, 0.88, -1.54, -0.02, 0.58),
        (-0.78, 0.78, -1.30, -0.15, 1.34),
        SAND,
    )
    mesh.box(-0.64, 0.64, -1.38, -1.24, 0.92, 1.22, GLASS)
    mesh.box(-0.82, -0.66, -1.18, -0.58, 0.84, 1.18, GLASS)
    mesh.box(0.66, 0.82, -1.18, -0.58, 0.84, 1.18, GLASS)
    for x in (-0.70, 0.54):
        mesh.box(x, x + 0.16, -1.63, -1.50, 0.68, 0.82, LAMP, outline=False)
    mesh.box(-0.80, 0.80, 1.43, 1.59, 0.58, 0.78, GRILLE)
    return mesh


def _sads_turret() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, 0.42, 0.93), 0.14, 0.60, SAND_DARK, segments=10)
    mesh.box(-0.62, 0.62, -0.08, 0.82, 0.92, 1.16, SAND)
    # Four highly legible missile canisters.
    for x in (-0.47, -0.16, 0.16, 0.47):
        mesh.cylinder_y((x, -0.56, 1.28), 1.34, 0.12, OLIVE_DARK, segments=8)
        mesh.cylinder_y((x, -1.25, 1.28), 0.10, 0.14, METAL, segments=8)
    # Upright radar panel creates a clear rear-facing silhouette.
    mesh.box(-0.53, 0.53, 0.73, 0.84, 1.12, 1.88, OLIVE_LIGHT)
    mesh.box(-0.39, 0.39, 0.70, 0.72, 1.25, 1.75, GLASS, outline=False)
    return mesh


def _tech_hull() -> Mesh:
    mesh = Mesh()
    for y in (-1.02, 0.92):
        mesh.cylinder_x((0, y, 0.28), 1.76, 0.29, RUBBER, segments=10)
        mesh.cylinder_x((0, y, 0.28), 1.84, 0.12, OLIVE_DARK, segments=8)
    mesh.box(-0.67, 0.67, -1.28, 1.24, 0.31, 0.52, OLIVE_DARK)
    mesh.box(-0.66, 0.66, -1.25, -0.58, 0.49, 0.70, OLIVE)
    mesh.tapered_box(
        (-0.65, 0.65, -0.57, 0.21, 0.48),
        (-0.56, 0.56, -0.48, 0.12, 1.11),
        OLIVE,
    )
    mesh.box(-0.47, 0.47, -0.54, -0.44, 0.75, 1.03, GLASS)
    mesh.box(-0.67, 0.67, 0.20, 1.18, 0.47, 0.67, OLIVE_DARK)
    mesh.box(-0.61, 0.61, 0.27, 1.10, 0.68, 0.76, METAL)
    for x in (-0.54, 0.42):
        mesh.box(x, x + 0.12, -1.31, -1.20, 0.50, 0.62, LAMP, outline=False)
    return mesh


def _tech_turret() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_z((0, 0.48, 0.84), 0.12, 0.34, OLIVE_DARK, segments=10)
    mesh.cylinder_z((0, 0.44, 1.12), 0.46, 0.09, METAL, segments=8)
    mesh.box(-0.25, 0.25, 0.22, 0.65, 1.27, 1.41, OLIVE)
    mesh.cylinder_y((0, -0.28, 1.37), 1.25, 0.055, STEEL, segments=8)
    mesh.box(-0.10, 0.10, -0.96, -0.77, 1.27, 1.48, GRILLE)
    return mesh


def _ymlr_hull(*, loaded: bool) -> Mesh:
    mesh = Mesh()
    for y in (-1.44, 0.18, 1.35):
        mesh.cylinder_x((0, y, 0.34), 2.18, 0.32, RUBBER, segments=10)
        mesh.cylinder_x((0, y, 0.34), 2.26, 0.14, OLIVE_DARK, segments=8)
    mesh.box(-0.86, 0.86, -1.69, 1.68, 0.39, 0.62, OLIVE_DARK)
    mesh.tapered_box(
        (-0.84, 0.84, -1.61, -0.37, 0.56),
        (-0.72, 0.72, -1.43, -0.49, 1.24),
        OLIVE,
    )
    mesh.box(-0.58, 0.58, -1.48, -1.36, 0.84, 1.12, GLASS)
    mesh.box(-0.80, 0.80, -0.29, 1.55, 0.58, 0.81, OLIVE)
    mesh.slanted_box_y(-0.65, 0.65, -0.05, 1.46, 0.78, 1.30, 0.13, METAL)
    mesh.slanted_box_y(-0.49, -0.37, -0.15, 1.45, 0.91, 1.45, 0.12, STEEL)
    mesh.slanted_box_y(0.37, 0.49, -0.15, 1.45, 0.91, 1.45, 0.12, STEEL)
    if loaded:
        mesh.slanted_box_y(-0.30, 0.30, -0.50, 1.42, 1.04, 1.70, 0.34, OLIVE_LIGHT)
        # Contrasting launch nose makes loaded and empty states unmistakable.
        mesh.box(-0.32, 0.32, -0.64, -0.44, 1.03, 1.41, RED)
        mesh.box(-0.23, 0.23, 1.38, 1.58, 1.70, 2.04, GRILLE)
    for x in (-0.66, 0.52):
        mesh.box(x, x + 0.14, -1.70, -1.58, 0.57, 0.70, LAMP, outline=False)
    return mesh


def _samad_airframe() -> Mesh:
    mesh = Mesh()
    mesh.cylinder_y((0, -0.05, 0.35), 2.82, 0.18, OLIVE_LIGHT, segments=10)
    mesh.tapered_box(
        (-0.18, 0.18, -1.70, -1.43, 0.22),
        (-0.03, 0.03, -1.92, -1.70, 0.35),
        OLIVE_LIGHT,
    )
    # Long straight wings and a small V-tail identify the UAV at tiny scale.
    mesh.polygon(((-1.72, -0.28, 0.34), (1.72, -0.28, 0.34), (1.28, 0.34, 0.34), (-1.28, 0.34, 0.34)), OLIVE)
    mesh.polygon(((-0.72, 1.05, 0.36), (0.72, 1.05, 0.36), (0.58, 1.48, 0.36), (-0.58, 1.48, 0.36)), OLIVE)
    mesh.polygon(((0, 0.94, 0.37), (0, 1.52, 0.37), (0, 1.40, 0.91), (0, 1.10, 0.74)), OLIVE_DARK)
    mesh.box(-0.08, 0.08, 1.47, 1.71, 0.22, 0.48, STEEL)
    mesh.box(-0.44, 0.44, 1.68, 1.73, 0.15, 0.55, METAL, outline=False)
    return mesh


def _rotate(point: Vec3, angle: float) -> Vec3:
    radians = math.radians(angle)
    cosine, sine = math.cos(radians), math.sin(radians)
    x, y, z = point
    return (x * cosine - y * sine, x * sine + y * cosine, z)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _shade(color: Color, intensity: float) -> Color:
    return tuple(max(0, min(255, round(value * intensity))) for value in color)  # type: ignore[return-value]


def _render(
    mesh: Mesh,
    angle: float,
    frame_size: int,
    *,
    shadow: bool,
    model_span: float = 5.45,
    center_y_factor: float = 0.63,
) -> Image.Image:
    supersample = 4
    scale = frame_size * supersample / model_span
    center_x = frame_size * supersample / 2
    center_y = frame_size * supersample * center_y_factor
    camera = (0.0, -0.82, 0.57)
    light = (-0.48, -0.58, 0.66)

    canvas = Image.new("RGBA", (frame_size * supersample, frame_size * supersample), (0, 0, 0, 0))
    if shadow:
        shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_points = []
        vertices = [vertex for face in mesh.faces for vertex in face.vertices]
        x0, x1 = min(vertex[0] for vertex in vertices), max(vertex[0] for vertex in vertices)
        y0, y1 = min(vertex[1] for vertex in vertices), max(vertex[1] for vertex in vertices)
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            rx, ry, _ = _rotate((x, y, 0), angle)
            shadow_points.append((round(center_x + rx * scale + 4), round(center_y + ry * 0.57 * scale + 7)))
        ImageDraw.Draw(shadow_layer).polygon(shadow_points, fill=(0, 0, 0, 92))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(2.7 * supersample))
        canvas.alpha_composite(shadow_layer)

    visible: list[tuple[float, list[tuple[float, float]], Color, bool]] = []
    for face in mesh.faces:
        vertices = tuple(_rotate(vertex, angle) for vertex in face.vertices)
        normal = _rotate(face.normal, angle)
        visibility = _dot(normal, camera)
        if visibility <= 0.005:
            continue
        points = [(center_x + x * scale, center_y + (y * 0.57 - z * 0.82) * scale) for x, y, z in vertices]
        depth = sum(_dot(vertex, camera) for vertex in vertices) / len(vertices)
        diffuse = max(0.0, _dot(normal, light))
        color = _shade(face.color, 0.62 + 0.48 * diffuse)
        visible.append((depth, points, color, face.outline))

    draw = ImageDraw.Draw(canvas)
    for _, points, color, outline in sorted(visible, key=lambda item: item[0]):
        draw.polygon(points, fill=(*color, 255))
        if outline:
            edge = _shade(color, 0.46)
            draw.line(points + [points[0]], fill=(*edge, 255), width=max(2, supersample // 2), joint="curve")

    return canvas.resize((frame_size, frame_size), Image.Resampling.LANCZOS)


CLASSIC_YAWS = (
    0, 40, 74, 112, 146, 172, 200, 228,
    256, 284, 312, 340, 370, 402, 436, 472,
    512, 552, 588, 626, 658, 684, 712, 740,
    768, 796, 824, 852, 882, 914, 948, 984,
)


def _angles(facings: int, *, classic: bool) -> tuple[float, ...]:
    if classic:
        if facings != 32:
            raise ValueError("classic Red Alert vehicle artwork requires 32 facings")
        return tuple(yaw * 360 / 1024 for yaw in CLASSIC_YAWS)
    return tuple(360 * facing / facings for facing in range(facings))


def render_m1a2s_frames(frame_size: int = 40, facings: int = 32) -> tuple[list[Image.Image], list[Image.Image]]:
    """Return unique hull and turret frames in clockwise ClassicFacing order."""

    hull = _m1_hull()
    turret = _m1_turret()
    angles = _angles(facings, classic=True)
    hull_frames = [_render(hull, angle, frame_size, shadow=True, model_span=6.20) for angle in angles]
    turret_frames = [_render(turret, angle, frame_size, shadow=False, model_span=6.20) for angle in angles]
    return hull_frames, turret_frames


def render_sads_frames(frame_size: int = 40, facings: int = 32) -> tuple[list[Image.Image], list[Image.Image]]:
    angles = _angles(facings, classic=True)
    hull = [_render(_sads_hull(), angle, frame_size, shadow=True, model_span=5.25) for angle in angles]
    turret = [_render(_sads_turret(), angle, frame_size, shadow=False, model_span=5.25) for angle in angles]
    return hull, turret


def render_tech_frames(frame_size: int = 28, facings: int = 32) -> tuple[list[Image.Image], list[Image.Image]]:
    angles = _angles(facings, classic=True)
    hull = [_render(_tech_hull(), angle, frame_size, shadow=True, model_span=3.95) for angle in angles]
    turret = [_render(_tech_turret(), angle, frame_size, shadow=False, model_span=3.95) for angle in angles]
    return hull, turret


def render_ymlr_frames(frame_size: int = 40, facings: int = 32) -> tuple[list[Image.Image], list[Image.Image]]:
    angles = _angles(facings, classic=True)
    loaded = [_render(_ymlr_hull(loaded=True), angle, frame_size, shadow=True, model_span=5.45) for angle in angles]
    empty = [_render(_ymlr_hull(loaded=False), angle, frame_size, shadow=True, model_span=5.45) for angle in angles]
    return loaded, empty


def render_samad_frames(frame_size: int = 40, facings: int = 16) -> list[Image.Image]:
    angles = _angles(facings, classic=False)
    return [
        _render(_samad_airframe(), angle, frame_size, shadow=False, model_span=4.85, center_y_factor=0.58)
        for angle in angles
    ]


DIRECTIONAL_RENDERERS = {
    "m1a2s": render_m1a2s_frames,
    "sads": render_sads_frames,
    "tech": render_tech_frames,
    "ymlr": render_ymlr_frames,
    "samad": render_samad_frames,
}


def render_directional_asset(name: str, frame_size: int, facings: int) -> list[Image.Image]:
    try:
        result = DIRECTIONAL_RENDERERS[name](frame_size, facings)
    except KeyError as error:
        raise ValueError(f"unknown directional model: {name}") from error
    if isinstance(result, tuple):
        return result[0] + result[1]
    return result
