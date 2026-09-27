"""Deterministic low-poly concept models for the United States (`usa`) faction.

Checkpoint B (roadmap gate 2) needs a concept and silhouette board before any
full U.S. frame sheet is produced.  Every U.S. roster actor is authored here as
original project geometry and rendered from a fixed camera for each facing, in
the same spirit as the Red Sea, Türkiye, Iran and China directional builders.
No output frame is produced by rotating or copying a finished bitmap, and no
third-party artwork, photograph or logo is used as a source.

The module is palette-agnostic: renders return an RGBA colour image, a
player-colour mask and a contact-shadow layer.  ``quantize_sprite`` then maps a
render into an indexed Red Alert sprite whose player-colour zones use the
native remap ramp (indexes 80-95), exactly as a shipping SHP would.

Camera note: this renderer keeps the Red Sea renderer's projection and
lighting, but culls and depth-sorts against the camera that the projection
actually implies (looking from the south and above).  See ``render_mesh``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable, Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from red_sea_directional_vehicle import CLASSIC_YAWS, Mesh


Vec3 = tuple[float, float, float]
Color = tuple[int, int, int]


# ---------------------------------------------------------------------------
# Materials.  Values are chosen to land on the temperate "player" palette that
# Red Alert uses for every unit on every tileset.  The U.S. set deliberately
# uses the palette's cool green ramp (148-154), not the warm olive of Türkiye
# or the sand of the Saudi pack, so faction reads before shape does.
# ---------------------------------------------------------------------------

GREEN = (72, 96, 62)
GREEN_LIGHT = (86, 112, 72)
GREEN_DARK = (52, 72, 42)
GREEN_DEEP = (36, 52, 24)
KHAKI = (168, 162, 118)
KHAKI_DARK = (132, 124, 96)
BAG = (148, 136, 104)
TARP = (100, 88, 70)
TRACK = (40, 40, 38)
RUBBER = (58, 58, 56)
HUB = (104, 136, 92)
STEEL = (100, 100, 100)
STEEL_DARK = (58, 58, 58)
GUNMETAL = (72, 72, 72)
BLACK = (22, 22, 22)
GLASS = (40, 56, 66)
SENSOR = (32, 44, 96)
LAMP = (232, 214, 150)
APS = (150, 150, 138)
SLAT = (190, 184, 150)
VHULL = (24, 30, 20)
HAZE = (148, 150, 152)
HAZE_LIGHT = (176, 178, 180)
HAZE_DARK = (108, 112, 116)
DECK = (80, 82, 84)
DECK_DARK = (56, 58, 60)
BOOT = (96, 36, 28)
AIR_DARK = (84, 88, 94)
AIR_DARKER = (62, 66, 72)
AIR_LIGHT = (172, 174, 170)
AIR_PALE = (196, 198, 194)
ARMY_AIR = (58, 64, 52)
ARMY_AIR_DARK = (40, 44, 36)
SUB_BLACK = (36, 36, 38)
WHITE = (228, 228, 224)
CONCRETE = (150, 146, 136)
CONCRETE_DARK = (112, 108, 100)
SANDBAG = (164, 146, 108)
SANDBAG_DARK = (124, 108, 80)
MESH_DISH = (190, 192, 186)
RADAR_FACE = (58, 70, 84)
# Infantry: an original muted multi-tone field uniform and coyote-brown kit.
UNIFORM = (176, 166, 128)
UNIFORM_DARK = (140, 130, 100)
KIT = (156, 132, 98)
KIT_DARK = (118, 98, 74)
HELMET = (128, 126, 84)
SKIN = (196, 146, 108)
BOOTS = (92, 78, 60)
WEAPON = (46, 46, 44)
WEAPON_LIGHT = (84, 84, 80)
TUBE = (104, 114, 72)
TUBE_DARK = (70, 78, 50)
NVG = (30, 32, 30)

# Player-colour marker materials.  Faces painted with these colours are
# shaded like any other face in the colour pass and are recorded in the mask
# pass; ``quantize_sprite`` then maps them onto the remap ramp by brightness.
TEAM = (206, 206, 206)
TEAM_DARK = (160, 160, 160)
TEAM_COLORS = frozenset((TEAM, TEAM_DARK))

# The ramp every Red Alert unit uses for player colour.
REMAP_INDEXES = tuple(range(80, 96))
# Indexes a unit sprite must not use for ordinary colours: transparency,
# shadow, the remap ramp, the rotating water colours and the light rotator.
RESERVED_INDEXES = frozenset((0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, *REMAP_INDEXES, *range(96, 104)))
SHADOW_INDEX = 4

GROUND_PX = 6.45  # pixels per model unit: parity with the shipped M1A2S (40 px / 6.2)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _sub(a: Vec3, b: Vec3) -> Vec3:
	return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec3, b: Vec3) -> Vec3:
	return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a: Vec3, b: Vec3) -> float:
	return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: Vec3) -> Vec3:
	length = math.sqrt(_dot(a, a)) or 1.0
	return (a[0] / length, a[1] / length, a[2] / length)


def _centroid(points: Sequence[Vec3]) -> Vec3:
	count = len(points)
	return (sum(p[0] for p in points) / count, sum(p[1] for p in points) / count, sum(p[2] for p in points) / count)


def _face_normal(points: Sequence[Vec3]) -> Vec3:
	# Newell's method is robust for any planar polygon, convex or not.
	nx = ny = nz = 0.0
	for index, current in enumerate(points):
		following = points[(index + 1) % len(points)]
		nx += (current[1] - following[1]) * (current[2] + following[2])
		ny += (current[2] - following[2]) * (current[0] + following[0])
		nz += (current[0] - following[0]) * (current[1] + following[1])
	return _norm((nx, ny, nz))


def add_face(mesh: Mesh, points: Sequence[Vec3], color: Color, *, outward_from: Vec3 | None = None, up: bool = False, outline: bool = True) -> None:
	"""Add a polygon, orienting its normal away from ``outward_from`` or upward."""

	pts = tuple(points)
	normal = _face_normal(pts)
	if outward_from is not None:
		if _dot(normal, _sub(_centroid(pts), outward_from)) < 0:
			pts = tuple(reversed(pts))
	elif up and normal[2] < 0:
		pts = tuple(reversed(pts))
	mesh.polygon(pts, color, outline=outline)


def flat(mesh: Mesh, points: Sequence[Vec3], color: Color, *, both: bool = False, outline: bool = True) -> None:
	"""A thin horizontal-ish plate (wing, deck marking).  ``both`` makes it two-sided."""

	add_face(mesh, points, color, up=True, outline=outline)
	if both:
		pts = tuple(points)
		normal = _face_normal(pts)
		mesh.polygon(tuple(reversed(pts)) if normal[2] > 0 else pts, color, outline=outline)


def hull_solid(mesh: Mesh, bottom: Sequence[Vec3], top: Sequence[Vec3], color: Color, *, top_color: Color | None = None, side_colors: Sequence[Color] | None = None, cap_bottom: bool = True) -> None:
	"""Loft between two rings of equal length (a convex frustum)."""

	center = _centroid(list(bottom) + list(top))
	count = len(bottom)
	if cap_bottom:
		add_face(mesh, bottom, color, outward_from=center)
	add_face(mesh, top, top_color or color, outward_from=center)
	for index in range(count):
		following = (index + 1) % count
		side = side_colors[index] if side_colors else color
		add_face(mesh, (bottom[index], bottom[following], top[following], top[index]), side, outward_from=center)


def prism(mesh: Mesh, footprint: Sequence[tuple[float, float]], z0: float, z1: float, color: Color, *, top_color: Color | None = None, inset: float = 1.0, shift: tuple[float, float] = (0.0, 0.0), side_colors: Sequence[Color] | None = None) -> None:
	cx = sum(p[0] for p in footprint) / len(footprint)
	cy = sum(p[1] for p in footprint) / len(footprint)
	bottom = [(x, y, z0) for x, y in footprint]
	top = [(cx + (x - cx) * inset + shift[0], cy + (y - cy) * inset + shift[1], z1) for x, y in footprint]
	hull_solid(mesh, bottom, top, color, top_color=top_color, side_colors=side_colors)


def block(mesh: Mesh, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, color: Color, *, top_color: Color | None = None, outline: bool = True) -> None:
	if top_color is None and outline:
		mesh.box(x0, x1, y0, y1, z0, z1, color)
		return
	prism(mesh, ((x0, y0), (x1, y0), (x1, y1), (x0, y1)), z0, z1, color, top_color=top_color)


def beam(mesh: Mesh, p0: Vec3, p1: Vec3, width: float, height: float, color: Color, *, up: Vec3 = (0.0, 0.0, 1.0)) -> None:
	"""An oriented box from ``p0`` to ``p1`` (limbs, masts, booms, rails)."""

	axis = _norm(_sub(p1, p0))
	if abs(_dot(axis, up)) > 0.95:
		up = (0.0, 1.0, 0.0)
	side = _norm(_cross(axis, up))
	lift = _norm(_cross(side, axis))
	hw, hh = width / 2, height / 2
	corners = []
	for end in (p0, p1):
		for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
			corners.append((end[0] + side[0] * hw * sx + lift[0] * hh * sz,
							end[1] + side[1] * hw * sx + lift[1] * hh * sz,
							end[2] + side[2] * hw * sx + lift[2] * hh * sz))
	hull_solid(mesh, corners[:4], corners[4:], color)


def cylinder(mesh: Mesh, p0: Vec3, p1: Vec3, radius: float, color: Color, *, segments: int = 8, cap_color: Color | None = None, radius1: float | None = None) -> None:
	axis = _norm(_sub(p1, p0))
	helper = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (1.0, 0.0, 0.0)
	u = _norm(_cross(axis, helper))
	v = _norm(_cross(axis, u))
	r1 = radius if radius1 is None else radius1
	ring0, ring1 = [], []
	for index in range(segments):
		angle = math.tau * index / segments
		cu, sv = math.cos(angle), math.sin(angle)
		ring0.append((p0[0] + (u[0] * cu + v[0] * sv) * radius, p0[1] + (u[1] * cu + v[1] * sv) * radius, p0[2] + (u[2] * cu + v[2] * sv) * radius))
		ring1.append((p1[0] + (u[0] * cu + v[0] * sv) * r1, p1[1] + (u[1] * cu + v[1] * sv) * r1, p1[2] + (u[2] * cu + v[2] * sv) * r1))
	center = _centroid(ring0 + ring1)
	add_face(mesh, ring0, cap_color or color, outward_from=center)
	add_face(mesh, ring1, cap_color or color, outward_from=center)
	for index in range(segments):
		following = (index + 1) % segments
		add_face(mesh, (ring0[index], ring0[following], ring1[following], ring1[index]), color, outward_from=center, outline=False)


def loft(mesh: Mesh, stations: Sequence[tuple[float, float, float, float]], color: Color, *, segments: int = 10, z_clip: float | None = None, top_color: Color | None = None) -> None:
	"""Loft elliptical sections along Y: stations are (y, half_width, half_height, z_center)."""

	rings = []
	for y, hw, hh, zc in stations:
		ring = []
		for index in range(segments):
			angle = math.tau * index / segments
			z = zc + math.sin(angle) * hh
			if z_clip is not None:
				z = max(z_clip, z)
			ring.append((math.cos(angle) * hw, y, z))
		rings.append(ring)
	center = _centroid([p for ring in rings for p in ring])
	for a, b in zip(rings, rings[1:]):
		for index in range(segments):
			following = (index + 1) % segments
			quad = (a[index], a[following], b[following], b[index])
			shade_top = top_color if top_color and min(p[2] for p in quad) > (z_clip or -9) + 0.05 else color
			add_face(mesh, quad, shade_top, outward_from=center, outline=False)
	add_face(mesh, rings[0], color, outward_from=center)
	add_face(mesh, rings[-1], color, outward_from=center)


def transformed(mesh: Mesh, fn: Callable[[Vec3], Vec3]) -> Mesh:
	out = Mesh()
	for face in mesh.faces:
		out.polygon(tuple(fn(v) for v in face.vertices), face.color, outline=face.outline)
	return out


def rotate_about_x(pivot: Vec3, degrees: float) -> Callable[[Vec3], Vec3]:
	radians = math.radians(degrees)
	c, s = math.cos(radians), math.sin(radians)

	def apply(point: Vec3) -> Vec3:
		y, z = point[1] - pivot[1], point[2] - pivot[2]
		return (point[0], pivot[1] + y * c - z * s, pivot[2] + y * s + z * c)

	return apply


def rotate_about_y(pivot: Vec3, degrees: float) -> Callable[[Vec3], Vec3]:
	radians = math.radians(degrees)
	c, s = math.cos(radians), math.sin(radians)

	def apply(point: Vec3) -> Vec3:
		x, z = point[0] - pivot[0], point[2] - pivot[2]
		return (pivot[0] + x * c - z * s, point[1], pivot[2] + x * s + z * c)

	return apply


def scaled(mesh: Mesh, factor: float) -> Mesh:
	return transformed(mesh, lambda p: (p[0] * factor, p[1] * factor, p[2] * factor))


def merge(*meshes: Mesh) -> Mesh:
	out = Mesh()
	for mesh in meshes:
		out.faces.extend(mesh.faces)
	return out


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

# Light from the west, slightly toward the camera and high above, so the
# walls the player actually sees are lit rather than silhouetted.
LIGHT = _norm((-0.62, 0.30, 0.72))


def _shade(color: Color, intensity: float) -> Color:
	return tuple(max(0, min(255, round(value * intensity))) for value in color)  # type: ignore[return-value]


def _yaw(point: Vec3, degrees: float) -> Vec3:
	radians = math.radians(degrees)
	c, s = math.cos(radians), math.sin(radians)
	x, y, z = point
	return (x * c - y * s, x * s + y * c, z)


def _pitch(point: Vec3, degrees: float) -> Vec3:
	radians = math.radians(degrees)
	c, s = math.cos(radians), math.sin(radians)
	x, y, z = point
	return (x, y * c - z * s, y * s + z * c)


def _roll(point: Vec3, degrees: float) -> Vec3:
	radians = math.radians(degrees)
	c, s = math.cos(radians), math.sin(radians)
	x, y, z = point
	return (x * c - z * s, y, x * s + z * c)


@dataclass
class Render:
	"""One rendered sprite frame before quantization."""

	color: Image.Image
	mask: Image.Image
	shadow: Image.Image


def render_mesh(
	mesh: Mesh,
	yaw: float,
	size: tuple[int, int],
	origin: tuple[float, float],
	*,
	px: float = GROUND_PX,
	ky: float = 0.57,
	kz: float = 0.82,
	pitch: float = 0.0,
	roll: float = 0.0,
	shadow: str = "footprint",
	shadow_offset: tuple[float, float] = (1.0, 1.5),
	supersample: int = 4,
	outlines: bool = True,
) -> Render:
	"""Render ``mesh`` at a compass ``yaw`` (degrees clockwise from north).

	Projection: screen_x = x, screen_y = y * ky - z * kz (model units scaled by
	``px``), which views the scene from the south and above along
	(0, kz, ky).  Faces are culled and depth-sorted against that same vector,
	so the roof and the camera-facing (south) walls are what the player sees.
	"""

	width, height = size
	scale = px * supersample
	ox, oy = origin[0] * supersample, origin[1] * supersample
	view = _norm((0.0, kz, ky))

	color = Image.new("RGBA", (width * supersample, height * supersample), (0, 0, 0, 0))
	mask = Image.new("L", color.size, 0)
	shadow_layer = Image.new("L", color.size, 0)

	def project(point: Vec3) -> tuple[float, float]:
		return (ox + point[0] * scale, oy + (point[1] * ky - point[2] * kz) * scale)

	def pose(point: Vec3) -> Vec3:
		return _yaw(_roll(_pitch(point, pitch), roll), yaw)

	if shadow == "footprint" and mesh.faces:
		ground = [pose(v) for face in mesh.faces for v in face.vertices]
		hull = _convex_hull([(p[0], p[1]) for p in ground])
		points = [(ox + (x * scale) + shadow_offset[0] * supersample, oy + (y * ky * scale) + shadow_offset[1] * supersample) for x, y in hull]
		if len(points) >= 3:
			ImageDraw.Draw(shadow_layer).polygon(points, fill=255)
			shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(0.9 * supersample))

	faces = []
	for face in mesh.faces:
		vertices = [pose(v) for v in face.vertices]
		normal = pose(face.normal)
		if _dot(normal, view) <= 0.005:
			continue
		depth = sum(_dot(v, view) for v in vertices) / len(vertices)
		diffuse = max(0.0, _dot(normal, LIGHT))
		shaded = _shade(face.color, 0.62 + 0.48 * diffuse)
		faces.append((depth, [project(v) for v in vertices], shaded, face.outline, face.color in TEAM_COLORS))

	draw = ImageDraw.Draw(color)
	mask_draw = ImageDraw.Draw(mask)
	line_width = max(2, supersample // 2)
	for _, points, shaded, outline, team in sorted(faces, key=lambda item: item[0]):
		draw.polygon(points, fill=(*shaded, 255))
		mask_draw.polygon(points, fill=255 if team else 0)
		if outline and outlines:
			edge = _shade(shaded, 0.46)
			draw.line(points + [points[0]], fill=(*edge, 255), width=line_width, joint="curve")
			# Team outlines stay team: remapped art keeps its own dark shading.
			mask_draw.line(points + [points[0]], fill=255 if team else 0, width=line_width, joint="curve")

	return Render(
		color=color.resize(size, Image.Resampling.LANCZOS),
		mask=mask.resize(size, Image.Resampling.BOX),
		shadow=shadow_layer.resize(size, Image.Resampling.BOX),
	)


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
	pts = sorted(set((round(x, 5), round(y, 5)) for x, y in points))
	if len(pts) <= 2:
		return pts

	def turn(o, a, b):
		return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

	lower: list[tuple[float, float]] = []
	for p in pts:
		while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
			lower.pop()
		lower.append(p)
	upper: list[tuple[float, float]] = []
	for p in reversed(pts):
		while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
			upper.pop()
		upper.append(p)
	return lower[:-1] + upper[:-1]


def composite(*renders: Render) -> Render:
	"""Stack renders (e.g. hull then turret) in draw order."""

	base = renders[0]
	color = base.color.copy()
	mask = base.mask.copy()
	shadow = base.shadow.copy()
	for layer in renders[1:]:
		alpha = layer.color.getchannel("A").point(lambda value: 255 if value >= 96 else 0)
		color.alpha_composite(layer.color)
		mask.paste(layer.mask, (0, 0), alpha)
		shadow = ImageChops.lighter(shadow, layer.shadow)
	return Render(color, mask, shadow)


# ---------------------------------------------------------------------------
# Quantization to an indexed Red Alert sprite
# ---------------------------------------------------------------------------


@dataclass
class PaletteMap:
	"""Nearest-colour lookup restricted to indexes a unit sprite may use."""

	colors: tuple[Color, ...]
	allowed: tuple[int, ...] = field(init=False)
	cache: dict[Color, int] = field(default_factory=dict, init=False)

	def __post_init__(self) -> None:
		self.allowed = tuple(index for index in range(256) if index not in RESERVED_INDEXES)

	def nearest(self, rgb: Color) -> int:
		cached = self.cache.get(rgb)
		if cached is not None:
			return cached
		r, g, b = rgb
		best, best_distance = 0, None
		for index in self.allowed:
			pr, pg, pb = self.colors[index]
			# Weighted RGB distance keeps greens green and greys neutral.
			distance = 2 * (r - pr) ** 2 + 4 * (g - pg) ** 2 + 3 * (b - pb) ** 2
			if best_distance is None or distance < best_distance:
				best, best_distance = index, distance
		self.cache[rgb] = best
		return best

	def remap(self, rgb: Color) -> int:
		value = max(rgb)
		return min(REMAP_INDEXES, key=lambda index: (abs(max(self.colors[index]) - value), index))


def load_pal(path) -> tuple[Color, ...]:
	data = open(path, "rb").read()
	if len(data) != 768:
		raise ValueError(f"{path}: expected a 768-byte VGA palette")
	return tuple((data[i * 3] << 2, data[i * 3 + 1] << 2, data[i * 3 + 2] << 2) for i in range(256))


def quantize_sprite(render: Render, palette: PaletteMap, *, alpha_cut: int = 96, shadow_cut: int = 110) -> Image.Image:
	"""Return an indexed frame: 0 transparent, 4 shadow, 80-95 player colour."""

	width, height = render.color.size
	rgba = render.color.tobytes()
	mask = render.mask.tobytes()
	shadow = render.shadow.tobytes()
	out = bytearray(width * height)
	for index in range(width * height):
		r, g, b, a = rgba[index * 4:index * 4 + 4]
		if a >= alpha_cut:
			# Undo LANCZOS premultiplication artefacts on semi-opaque edges.
			if a < 255:
				r, g, b = (min(255, round(r * 255 / a)), min(255, round(g * 255 / a)), min(255, round(b * 255 / a)))
			out[index] = palette.remap((r, g, b)) if mask[index] >= 128 else palette.nearest((r, g, b))
		elif shadow[index] >= shadow_cut:
			out[index] = SHADOW_INDEX
	image = Image.frombytes("P", (width, height), bytes(out))
	flat_palette = [channel for color in palette.colors for channel in color]
	image.putpalette(flat_palette)
	image.info["transparency"] = 0
	return image


def outline_sprite(indexed: Image.Image, palette: PaletteMap, color: Color = (24, 20, 16)) -> Image.Image:
	"""Add a one-pixel dark rim outside the opaque silhouette.

	Native Red Alert infantry carry a dark rim that keeps them legible on
	white snow and on dark grass alike; the concept infantry get the same.
	"""

	width, height = indexed.size
	data = indexed.tobytes()
	out = bytearray(data)
	rim = palette.nearest(color)
	for y in range(height):
		for x in range(width):
			index = y * width + x
			if data[index] not in (0, SHADOW_INDEX):
				continue
			for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
				nx, ny = x + dx, y + dy
				if 0 <= nx < width and 0 <= ny < height and data[ny * width + nx] not in (0, SHADOW_INDEX):
					out[index] = rim
					break
	image = Image.frombytes("P", (width, height), bytes(out))
	image.putpalette(indexed.getpalette())
	image.info["transparency"] = 0
	return image


# ---------------------------------------------------------------------------
# Facing helpers
# ---------------------------------------------------------------------------


def classic_yaws(step: int = 4) -> tuple[float, ...]:
	"""Compass yaws for ClassicFacing frames 0, step, 2*step... (32-facing ring)."""

	return tuple(-yaw * 360 / 1024 for yaw in CLASSIC_YAWS[::step])


def even_yaws(facings: int, step: int = 1) -> tuple[float, ...]:
	return tuple(-360 * index / facings for index in range(0, facings, step))


FACING_LABELS = ("N", "NW", "W", "SW", "S", "SE", "E", "NE")
