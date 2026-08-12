"""Fixed-camera 3D renderers for the fictional Turkey faction.

Every moving sprite is projected from low-poly geometry at its authored yaw.
No output frame is produced by rotating a source bitmap.
"""

from __future__ import annotations

import math
from PIL import Image, ImageDraw, ImageFilter

from red_sea_directional_vehicle import Mesh, _angles, _render


OLIVE = (91, 102, 65)
OLIVE_LIGHT = (124, 132, 83)
OLIVE_DARK = (48, 57, 39)
CHARCOAL = (43, 47, 43)
RUBBER = (28, 31, 29)
STEEL = (72, 78, 74)
GLASS = (38, 66, 70)
LAMP = (230, 218, 143)
RED = (174, 44, 43)
WHITE = (217, 219, 207)
NAVAL = (102, 116, 118)
NAVAL_LIGHT = (143, 154, 151)
NAVAL_DARK = (55, 67, 69)
AIR = (91, 101, 102)
AIR_LIGHT = (130, 139, 136)
AIR_DARK = (47, 55, 58)


def _wheeled_hull(axles: int, *, amphibious: bool = False, ew: bool = False) -> Mesh:
	mesh = Mesh()
	length = 3.7 if axles == 4 else 3.25
	for i in range(axles):
		y = -length / 2 + 0.45 + i * (length - 0.9) / max(1, axles - 1)
		mesh.cylinder_x((0, y, 0.37), 2.28, 0.34, RUBBER, segments=10)
		mesh.cylinder_x((0, y, 0.37), 2.34, 0.14, OLIVE_DARK, segments=8)
	mesh.box(-0.95, 0.95, -length / 2, length / 2, 0.40, 0.67, OLIVE_DARK)
	if amphibious:
		mesh.tapered_box((-1.12, 1.12, -1.82, 1.73, 0.50), (-0.84, 0.84, -1.52, 1.42, 1.26), OLIVE)
		mesh.polygon(((-0.84, -1.52, 1.24), (0.84, -1.52, 1.24), (0.52, -1.90, 0.66), (-0.52, -1.90, 0.66)), OLIVE_LIGHT)
	else:
		mesh.tapered_box((-0.96, 0.96, -length / 2 + 0.06, length / 2 - 0.08, 0.62), (-0.78, 0.78, -length / 2 + 0.30, length / 2 - 0.28, 1.24), OLIVE)
	mesh.box(-0.52, 0.52, -length / 2 + 0.18, -length / 2 + 0.29, 0.88, 1.16, GLASS)
	for x in (-0.67, 0.51):
		mesh.box(x, x + 0.15, -length / 2 - 0.03, -length / 2 + 0.10, 0.62, 0.77, LAMP, outline=False)
	mesh.box(-0.62, 0.62, length / 2 - 0.18, length / 2, 0.62, 0.88, CHARCOAL)
	if ew:
		mesh.box(-0.78, 0.78, -0.20, 1.34, 1.18, 1.52, OLIVE_DARK)
		for x in (-0.56, -0.19, 0.19, 0.56):
			mesh.cylinder_z((x, 0.65, 1.78), 0.55, 0.045, STEEL, segments=7)
		mesh.box(-0.56, 0.56, 0.94, 1.07, 1.48, 2.02, OLIVE_LIGHT)
	return mesh


def _tracked_hull() -> Mesh:
	mesh = Mesh()
	for x0, x1 in ((-1.28, -0.88), (0.88, 1.28)):
		mesh.box(x0, x1, -1.92, 1.72, 0.12, 0.78, CHARCOAL)
	for y in (-1.48, -0.74, 0.00, 0.74, 1.36):
		mesh.cylinder_x((0, y, 0.39), 2.62, 0.29, RUBBER, segments=10)
		mesh.cylinder_x((0, y, 0.39), 2.70, 0.12, OLIVE_DARK, segments=8)
	mesh.tapered_box((-1.02, 1.02, -1.77, 1.58, 0.58), (-0.82, 0.82, -1.42, 1.38, 1.10), OLIVE)
	mesh.polygon(((-0.82, -1.42, 1.08), (0.82, -1.42, 1.08), (0.55, -1.82, 0.70), (-0.55, -1.82, 0.70)), OLIVE_LIGHT)
	mesh.box(-0.70, 0.70, 0.72, 1.42, 1.07, 1.18, OLIVE_DARK)
	for x in (-0.67, 0.52):
		mesh.box(x, x + 0.14, -1.80, -1.65, 0.69, 0.84, LAMP, outline=False)
	return mesh


def _turret(kind: str) -> Mesh:
	mesh = Mesh()
	mesh.cylinder_z((0, 0, 1.18), 0.14, 0.55, OLIVE_DARK, segments=10)
	if kind == "bozkir":
		mesh.tapered_box((-0.82, 0.82, -0.86, 0.92, 1.18), (-0.62, 0.62, -0.70, 0.72, 1.62), OLIVE)
		mesh.box(-0.66, 0.66, 0.61, 1.13, 1.30, 1.58, OLIVE_DARK)
		mesh.cylinder_y((0, -1.82, 1.51), 2.32, 0.10, STEEL, segments=10)
		mesh.cylinder_y((0, -2.93, 1.51), 0.20, 0.14, CHARCOAL, segments=10)
		mesh.box(0.22, 0.45, -0.31, -0.05, 1.60, 1.78, GLASS)
	elif kind == "yildirim":
		mesh.box(-0.76, 0.76, -0.58, 0.78, 1.16, 1.68, OLIVE_DARK)
		mesh.slanted_box_y(-0.20, 0.20, -2.75, -0.25, 1.72, 1.47, 0.18, STEEL)
		mesh.cylinder_y((0, -2.92, 1.58), 0.26, 0.16, CHARCOAL, segments=10)
	elif kind == "gokkalkan":
		mesh.box(-0.67, 0.67, -0.48, 0.72, 1.18, 1.55, OLIVE)
		for x in (-0.47, -0.16, 0.16, 0.47):
			mesh.cylinder_y((x, -0.82, 1.58), 1.45, 0.11, OLIVE_DARK, segments=8)
		mesh.box(-0.48, 0.48, 0.70, 0.82, 1.45, 2.12, AIR_DARK)
		mesh.box(-0.37, 0.37, 0.68, 0.70, 1.58, 2.00, GLASS, outline=False)
	elif kind == "sancak":
		mesh.cylinder_z((0, 0.10, 1.16), 0.40, 0.12, STEEL, segments=10)
		mesh.box(-0.62, 0.62, -0.06, 0.08, 1.25, 2.02, OLIVE_LIGHT)
		mesh.box(-0.49, 0.49, -0.08, -0.06, 1.38, 1.90, GLASS, outline=False)
		mesh.cylinder_y((0, -0.20, 1.42), 0.45, 0.08, STEEL, segments=8)
		mesh.box(-0.10, 0.10, -0.48, -0.36, 1.32, 1.52, RED)
	else:
		mesh.tapered_box((-0.42, 0.42, -0.45, 0.48, 1.18), (-0.29, 0.29, -0.33, 0.35, 1.48), OLIVE)
		mesh.cylinder_y((0, -0.92, 1.43), 1.32, 0.055, STEEL, segments=8)
		mesh.box(0.11, 0.30, -0.23, -0.03, 1.46, 1.62, GLASS)
	return mesh


def _airframe(kind: str) -> Mesh:
	mesh = Mesh()
	if kind == "kuzgunm":
		mesh.cylinder_y((0, -0.05, 0.42), 3.7, 0.20, AIR_LIGHT, segments=10)
		mesh.polygon(((-2.30, -0.25, 0.43), (2.30, -0.25, 0.43), (1.55, 0.62, 0.43), (-1.55, 0.62, 0.43)), AIR)
		mesh.polygon(((-0.82, 1.28, 0.44), (0.82, 1.28, 0.44), (0.62, 1.78, 0.44), (-0.62, 1.78, 0.44)), AIR_DARK)
		for x in (-0.40, 0.40):
			mesh.polygon(((x, 1.25, 0.44), (x, 1.84, 0.44), (x, 1.66, 1.05), (x, 1.38, 0.92)), AIR_DARK)
		mesh.cylinder_z((0, -0.72, 0.20), 0.24, 0.18, GLASS, segments=10)
	elif kind == "sahinx":
		mesh.cylinder_y((0, -0.15, 0.55), 5.2, 0.30, AIR, segments=12)
		mesh.tapered_box((-0.28, 0.28, -3.18, -2.55, 0.40), (-0.02, 0.02, -3.70, -3.18, 0.54), AIR_LIGHT)
		mesh.polygon(((-0.28, -1.1, 0.55), (-2.55, 0.78, 0.50), (-1.75, 1.42, 0.51), (0, 0.46, 0.61), (1.75, 1.42, 0.51), (2.55, 0.78, 0.50), (0.28, -1.1, 0.55)), AIR)
		mesh.polygon(((-0.22, 1.72, 0.57), (-1.20, 2.56, 0.55), (0, 2.22, 0.61), (1.20, 2.56, 0.55), (0.22, 1.72, 0.57)), AIR_DARK)
		for x in (-0.52, 0.52):
			mesh.polygon(((x, 1.55, 0.58), (x, 2.70, 0.58), (x, 2.42, 1.55), (x, 1.80, 1.30)), AIR_DARK)
		mesh.tapered_box((-0.25, 0.25, -1.85, -0.55, 0.68), (-0.15, 0.15, -1.65, -0.66, 1.07), GLASS)
		mesh.box(-0.10, 0.10, -2.25, -1.92, 0.58, 0.70, RED)
	else:
		mesh.tapered_box((-0.62, 0.62, -1.72, 0.95, 0.30), (-0.44, 0.44, -1.47, 0.72, 1.14), OLIVE)
		mesh.tapered_box((-0.44, 0.44, -1.98, -0.65, 0.40), (-0.31, 0.31, -1.75, -0.82, 1.22), GLASS)
		mesh.slanted_box_y(-0.20, 0.20, 0.65, 3.30, 0.72, 1.18, 0.20, OLIVE_DARK)
		mesh.polygon(((-0.22, 2.72, 1.04), (-0.22, 3.42, 1.15), (-0.22, 3.22, 2.02), (-0.22, 2.86, 1.73)), OLIVE)
		mesh.polygon(((-1.45, 0.20, 0.60), (-0.32, -0.08, 0.66), (0.32, -0.08, 0.66), (1.45, 0.20, 0.60), (1.30, 0.68, 0.58), (-1.30, 0.68, 0.58)), OLIVE)
		for x in (-1.12, 1.12):
			mesh.cylinder_y((x, 0.42, 0.48), 0.88, 0.17, OLIVE_DARK, segments=8)
		mesh.cylinder_y((0, -2.16, 0.20), 0.82, 0.055, STEEL, segments=8)
		mesh.cylinder_z((0, -0.02, 1.38), 0.38, 0.13, STEEL, segments=10)
	return mesh


def _ship_hull(kind: str) -> Mesh:
	mesh = Mesh()
	length = {"marmara": 5.9, "ege": 4.8, "poyraz": 3.5}[kind]
	width = {"marmara": 1.45, "ege": 1.28, "poyraz": 0.94}[kind]
	bow = -length / 2
	stern = length / 2
	bottom = ((-width * .62, bow + .55, 0), (width * .62, bow + .55, 0), (width, stern - .45, 0), (-width, stern - .45, 0))
	top = ((0, bow, .66), (-width * .82, bow + .72, .68), (width * .82, bow + .72, .68), (width * .90, stern - .35, .62), (-width * .90, stern - .35, .62))
	mesh.polygon(tuple(reversed(bottom)), NAVAL_DARK)
	mesh.polygon((bottom[0], bottom[1], top[0]), NAVAL_DARK)
	mesh.polygon((bottom[1], bottom[2], top[3], top[2], top[0]), NAVAL)
	mesh.polygon((bottom[2], bottom[3], top[4], top[3]), NAVAL_DARK)
	mesh.polygon((bottom[3], bottom[0], top[0], top[1], top[4]), NAVAL)
	mesh.polygon(top, NAVAL_LIGHT)
	if kind == "marmara":
		mesh.tapered_box((-0.65, 0.65, -0.72, 1.24, .66), (-0.45, .45, -.52, .98, 1.56), NAVAL)
		mesh.box(-.12, .12, .10, .26, 1.52, 2.50, STEEL)
		mesh.box(-.48, .48, -.58, -.44, 1.20, 1.42, GLASS)
		for x in (-.62, .62):
			mesh.box(x-.08, x+.08, .76, 1.58, .76, 1.03, AIR_DARK)
	elif kind == "ege":
		mesh.tapered_box((-.54, .54, -.40, 1.0, .64), (-.35, .35, -.22, .82, 1.42), NAVAL)
		mesh.box(-.10, .10, .20, .34, 1.39, 2.17, STEEL)
		mesh.box(-.40, .40, -.30, -.18, 1.12, 1.34, GLASS)
	else:
		mesh.tapered_box((-.39, .39, -.24, .70, .62), (-.25, .25, -.12, .58, 1.18), NAVAL_DARK)
		mesh.box(-.08, .08, .08, .18, 1.16, 1.65, STEEL)
		mesh.box(-.28, .28, -.18, -.08, .92, 1.10, GLASS)
	mesh.box(-width*.55, width*.55, stern-.34, stern-.20, .68, .82, CHARCOAL)
	return mesh


def _ship_turret(kind: str) -> Mesh:
	mesh = Mesh()
	base_z = .76
	mesh.cylinder_z((0, -0.75, base_z), .16, .30 if kind != "poyraz" else .20, NAVAL_DARK, segments=10)
	mesh.tapered_box((-.34, .34, -1.00, -.50, base_z), (-.22, .22, -.92, -.56, 1.10), NAVAL)
	mesh.cylinder_y((0, -1.25, 1.02), .72 if kind != "poyraz" else .46, .05, STEEL, segments=8)
	return mesh


def render_ground(name: str, size: int) -> list[Image.Image]:
	angles = _angles(32, classic=True)
	if name == "bozkir":
		hull = _tracked_hull()
	elif name == "sancak":
		hull = _wheeled_hull(4, ew=True)
	else:
		hull = _wheeled_hull(4, amphibious=name == "denizkaplan")
	bodies = [_render(hull, a, size, shadow=True, model_span=6.2) for a in angles]
	turret = _turret(name if name in {"bozkir", "yildirim", "gokkalkan", "sancak"} else "remote")
	return bodies + [_render(turret, a, size, shadow=False, model_span=6.2) for a in angles]


def render_air(name: str, size: int) -> list[Image.Image]:
	facings = 32 if name == "turnaah" else 16
	angles = _angles(facings, classic=facings == 32)
	span = 7.4 if name == "sahinx" else 6.3
	return [_render(_airframe(name), a, size, shadow=False, model_span=span, center_y_factor=.59) for a in angles]


def render_ship(name: str, size: int) -> list[Image.Image]:
	bodies = [_render(_ship_hull(name), a, size, shadow=False, model_span=7.2, center_y_factor=.58) for a in _angles(16, classic=False)]
	turrets = [_render(_ship_turret(name), a, size, shadow=False, model_span=7.2, center_y_factor=.58) for a in _angles(32, classic=True)]
	return bodies + turrets


def render_rotor(size: int = 56) -> list[Image.Image]:
	images = []
	for index, angle in enumerate(tuple(i * 22.5 for i in range(4)) + tuple(i * 11.25 for i in range(8))):
		canvas = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
		draw = ImageDraw.Draw(canvas)
		cx = cy = size * 2
		for blade in range(4):
			a = math.radians(angle + blade * 90)
			dx, dy = math.cos(a) * size * 1.78, math.sin(a) * size * .72
			draw.line((cx-dx, cy-dy, cx+dx, cy+dy), fill=(70, 76, 70, 190), width=8)
		draw.ellipse((cx-13, cy-10, cx+13, cy+10), fill=(38, 43, 40, 255))
		if index < 4:
			canvas = canvas.filter(ImageFilter.GaussianBlur(1.5))
		images.append(canvas.resize((size, size), Image.Resampling.LANCZOS))
	return images


def render_spinner(size: int = 40) -> list[Image.Image]:
	images = []
	for phase in range(8):
		canvas = Image.new("RGBA", (size*4, size*4), (0,0,0,0))
		draw = ImageDraw.Draw(canvas)
		cx, cy = size*2, round(size*1.9)
		width = max(5, round(abs(math.cos(phase * math.pi / 8)) * size * 1.1))
		draw.ellipse((cx-width, cy-size*.48, cx+width, cy+size*.32), fill=(*OLIVE_LIGHT,235), outline=(*CHARCOAL,255), width=5)
		draw.line((cx, cy, cx, cy+size*.42), fill=(*STEEL,255), width=6)
		# A moving feed horn makes all eight dish phases visually and hash-unique.
		feed_x = cx + math.cos(phase * math.tau / 8) * max(4, width * .65)
		feed_y = cy + math.sin(phase * math.tau / 8) * size * .18
		draw.ellipse((feed_x-5, feed_y-5, feed_x+5, feed_y+5), fill=(*RED,255))
		images.append(canvas.resize((size,size), Image.Resampling.LANCZOS))
	return images
