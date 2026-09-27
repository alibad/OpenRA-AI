"""Authored concept geometry for every United States roster actor.

Each builder returns original low-poly geometry in model units (1 unit =
``GROUND_PX`` pixels at native scale; infantry use 1 unit = 1 pixel).  The nose
of every directional model points to -Y (north at yaw 0).  Landmark comments
cite the visual landmarks and player-colour zones frozen in
``OpenRA/docs/faction-spec-usa.md`` §5 so reviewers can trace each shape to its
contract line.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from PIL import Image, ImageDraw

from red_sea_directional_vehicle import Mesh

from usa_concept_models import (
	AIR_DARK, AIR_DARKER, AIR_LIGHT, AIR_PALE, APS, ARMY_AIR, ARMY_AIR_DARK, BAG, BLACK, BOOTS,
	CONCRETE, CONCRETE_DARK, DECK, DECK_DARK, GLASS, GREEN, GREEN_DARK, GREEN_LIGHT,
	GUNMETAL, HAZE, HAZE_DARK, HAZE_LIGHT, HELMET, HUB, KHAKI, KHAKI_DARK, KIT, KIT_DARK, LAMP,
	MESH_DISH, NVG, RADAR_FACE, RUBBER, SANDBAG, SANDBAG_DARK, SKIN, SLAT, STEEL, STEEL_DARK,
	SUB_BLACK, TARP, TEAM, TEAM_DARK, TRACK, TUBE, TUBE_DARK, UNIFORM, UNIFORM_DARK, VHULL, WEAPON,
	WEAPON_LIGHT, WHITE, Color, PaletteMap, Render, Vec3,
	add_face, beam, block, classic_yaws, composite, cylinder, even_yaws, flat, hull_solid, loft, merge,
	outline_sprite, prism, quantize_sprite, render_mesh, rotate_about_x, rotate_about_y, scaled, transformed,
)


# ---------------------------------------------------------------------------
# Shared running gear
# ---------------------------------------------------------------------------


def _tracked_base(mesh: Mesh, *, length: float, half_width: float, track_width: float = 0.42, skirt_team: bool = False,
				  skirt_z: tuple[float, float] = (0.34, 0.86), front: float | None = None, rear: float | None = None) -> None:
	"""Tracks hidden behind full-length armoured skirts, U.S. style.

	Skirts rather than exposed road-wheel combs keep the U.S. tracked family
	visibly different from the comb-wheeled tracked vehicles already shipped.
	"""

	y0 = -length / 2 if front is None else front
	y1 = length / 2 if rear is None else rear
	for side in (-1, 1):
		inner, outer = side * (half_width - track_width), side * half_width
		block(mesh, min(inner, outer), max(inner, outer), y0, y1, 0.04, 0.58, TRACK)
		# The skirt stands just proud of the track and stops short of the ground
		# so a dark track line survives underneath at every facing.
		sx0, sx1 = (outer - 0.02, outer + 0.06) if side > 0 else (outer - 0.06, outer + 0.02)
		block(mesh, min(sx0, sx1), max(sx0, sx1), y0 + 0.18, y1 - 0.30, skirt_z[0], skirt_z[1], GREEN)
		if skirt_team:
			bx0, bx1 = (outer + 0.06, outer + 0.09) if side > 0 else (outer - 0.09, outer - 0.06)
			block(mesh, min(bx0, bx1), max(bx0, bx1), y0 + 0.24, y1 - 0.36, skirt_z[1] - 0.36, skirt_z[1] - 0.02, TEAM)


def _wheel_line(mesh: Mesh, ys: tuple[float, ...], x: float, radius: float, width: float) -> None:
	for y in ys:
		for side in (-1, 1):
			cylinder(mesh, (side * (x - width / 2), y, radius), (side * (x + width / 2), y, radius), radius, RUBBER, segments=10)
			cylinder(mesh, (side * (x + width / 2 - 0.01), y, radius), (side * (x + width / 2 + 0.03), y, radius), radius * 0.46, HUB, segments=8)


# ---------------------------------------------------------------------------
# USMBT — M1A2 SEP v3 with active protection (contract §5.2, §8.1)
# ---------------------------------------------------------------------------


def usmbt_hull() -> Mesh:
	mesh = Mesh()
	_tracked_base(mesh, length=4.30, half_width=1.40, skirt_z=(0.30, 0.86))
	# Low wide hull with a long shallow glacis.
	prism(mesh, ((-1.02, -1.70), (1.02, -1.70), (1.02, 2.05), (-1.02, 2.05)), 0.40, 1.00, GREEN, top_color=GREEN_LIGHT, inset=0.97)
	add_face(mesh, ((-1.00, -1.72, 0.98), (1.00, -1.72, 0.98), (0.92, -2.22, 0.52), (-0.92, -2.22, 0.52)), GREEN_LIGHT, up=True)
	add_face(mesh, ((-0.92, -2.22, 0.52), (0.92, -2.22, 0.52), (0.92, -2.18, 0.30), (-0.92, -2.18, 0.30)), GREEN_DARK, outward_from=(0, 0, 0.6))
	# Small hull-front chevron (player colour zone 3).
	add_face(mesh, ((-0.70, -2.06, 0.70), (0.0, -1.80, 0.90), (0.0, -2.00, 0.77), (-0.62, -2.20, 0.56)), TEAM, up=True, outline=False)
	add_face(mesh, ((0.70, -2.06, 0.70), (0.0, -1.80, 0.90), (0.0, -2.00, 0.77), (0.62, -2.20, 0.56)), TEAM, up=True, outline=False)
	# Rear engine deck grille and exhaust make front/rear unambiguous.
	block(mesh, -0.86, 0.86, 1.10, 1.98, 0.99, 1.05, GREEN_DARK)
	for x in (-0.66, -0.30, 0.06, 0.42):
		block(mesh, x, x + 0.22, 1.22, 1.88, 1.04, 1.07, BLACK, outline=False)
	block(mesh, -0.80, 0.80, 2.03, 2.10, 0.52, 0.80, BLACK)
	for x in (-0.80, 0.62):
		block(mesh, x, x + 0.18, -2.26, -2.16, 0.56, 0.66, LAMP, outline=False)
	return mesh


def usmbt_turret() -> Mesh:
	mesh = Mesh()
	# Long, low, wedge-faced turret.  Player colour zone 1 is the full turret
	# side wall below the APS launchers (faces 2 and 6 of the footprint).
	footprint = ((-0.60, -1.30), (0.60, -1.30), (0.98, -0.62), (0.98, 0.72), (0.86, 0.86), (-0.86, 0.86), (-0.98, 0.72), (-0.98, -0.62))
	sides = (GREEN_DARK, TEAM_DARK, TEAM, TEAM_DARK, GREEN_DARK, TEAM_DARK, TEAM, TEAM_DARK)
	prism(mesh, footprint, 0.98, 1.50, GREEN, top_color=GREEN_LIGHT, inset=0.88, side_colors=sides)
	# Landmark 1: squared APS launcher boxes standing proud of the turret cheeks.
	for side in (-1, 1):
		x0, x1 = (0.92, 1.30) if side > 0 else (-1.30, -0.92)
		block(mesh, x0, x1, -0.80, -0.34, 1.24, 1.66, APS, top_color=(170, 170, 158))
		block(mesh, x0 + 0.05, x1 - 0.05, -0.86, -0.80, 1.32, 1.58, BLACK, outline=False)
	# Landmark 2: slatted roof screen - a raised light frame with dark gaps.
	block(mesh, -0.70, 0.70, -0.62, 0.58, 1.56, 1.60, BLACK, outline=False)
	for index in range(5):
		y = -0.62 + index * 0.26
		block(mesh, -0.70, 0.70, y, y + 0.13, 1.60, 1.66, SLAT, outline=False)
	# Landmark 3: deep rear bustle rack (player colour frame) packed with a
	# stowage lump that breaks the rear outline.
	block(mesh, -0.90, 0.90, 0.84, 1.70, 1.04, 1.10, GUNMETAL, outline=False)
	for x0 in (-0.98, 0.82):
		block(mesh, x0, x0 + 0.16, 0.80, 1.78, 1.04, 1.46, TEAM)
	block(mesh, -0.98, 0.98, 1.62, 1.78, 1.04, 1.46, TEAM)
	block(mesh, -0.70, 0.26, 0.94, 1.58, 1.10, 1.58, TARP, top_color=KHAKI_DARK)
	block(mesh, 0.22, 0.74, 1.02, 1.54, 1.10, 1.44, BAG)
	# 120 mm gun with thermal sleeve and mantlet.
	block(mesh, -0.30, 0.30, -1.44, -1.20, 1.08, 1.36, GREEN_DARK)
	cylinder(mesh, (0, -1.40, 1.24), (0, -2.50, 1.24), 0.10, GREEN_DARK)
	cylinder(mesh, (0, -2.50, 1.24), (0, -3.14, 1.24), 0.08, GREEN_DARK)
	cylinder(mesh, (0, -3.14, 1.24), (0, -3.26, 1.24), 0.10, BLACK)
	# Commander's independent viewer and gunner's sight (kept low and small).
	block(mesh, -0.58, -0.30, -0.06, 0.20, 1.56, 1.74, GUNMETAL)
	block(mesh, 0.30, 0.60, -1.04, -0.80, 1.40, 1.56, GUNMETAL, outline=False)
	return mesh


# ---------------------------------------------------------------------------
# USIFV — M2A4 Bradley (contract §5.2, §8.2)
# ---------------------------------------------------------------------------


# Bradley hull length is kept slightly under stock 2TNK, per contract §5.2.
IFV_SCALE = 0.90


def usifv_hull() -> Mesh:
	mesh = Mesh()
	# Landmark 3: tracked running gear behind visible skirt panels; the skirt
	# band is player colour zone 2.
	_tracked_base(mesh, length=3.62, half_width=1.34, skirt_team=True, skirt_z=(0.30, 0.94), front=-1.86, rear=1.80)
	# Tall slab-sided hull - noticeably taller than any stock tank hull.
	prism(mesh, ((-1.02, -1.30), (1.02, -1.30), (1.02, 1.80), (-1.02, 1.80)), 0.40, 1.46, GREEN, top_color=GREEN_LIGHT, inset=0.98)
	# Landmark 2: steeply sloped glacis with a squared driver's block offset left.
	center = (0.0, -1.2, 0.8)
	add_face(mesh, ((-1.00, -1.30, 1.44), (1.00, -1.30, 1.44), (0.96, -1.94, 0.68), (-0.96, -1.94, 0.68)), GREEN_LIGHT, outward_from=center)
	add_face(mesh, ((-0.96, -1.94, 0.68), (0.96, -1.94, 0.68), (0.96, -1.90, 0.38), (-0.96, -1.90, 0.38)), GREEN_DARK, outward_from=center)
	for side in (-1, 1):
		add_face(mesh, ((side * 1.00, -1.30, 1.44), (side * 1.00, -1.30, 0.40), (side * 0.96, -1.90, 0.38), (side * 0.96, -1.94, 0.68)), GREEN, outward_from=center)
	block(mesh, -0.94, -0.34, -1.56, -1.06, 1.38, 1.68, GREEN_DARK, top_color=GREEN)
	block(mesh, -0.86, -0.42, -1.58, -1.54, 1.50, 1.60, GLASS, outline=False)
	# Rear troop ramp outline.
	block(mesh, -0.66, 0.66, 1.80, 1.86, 0.48, 1.34, GREEN_DARK)
	for x in (-0.84, 0.66):
		block(mesh, x, x + 0.18, -1.98, -1.90, 0.52, 0.62, LAMP, outline=False)
	return scaled(mesh, IFV_SCALE)


def _bradley_launcher(raised: bool) -> Mesh:
	mesh = Mesh()
	# Landmark 1: boxy twin missile launcher folded on the turret's right flank.
	block(mesh, 0.74, 1.08, -0.46, 0.48, 1.60, 1.98, TUBE_DARK, top_color=TUBE)
	for z in (1.68, 1.84):
		block(mesh, 0.80, 1.02, -0.52, -0.46, z, z + 0.10, BLACK, outline=False)
	if raised:
		mesh = transformed(mesh, rotate_about_x((0.0, 0.48, 1.60), -58))
	return mesh


def usifv_turret(raised: bool = False) -> Mesh:
	mesh = Mesh()
	# Narrow, tall, slab-sided turret; its side slabs are player colour zone 1.
	footprint = ((-0.52, -0.64), (0.62, -0.64), (0.74, -0.42), (0.74, 0.68), (-0.64, 0.68), (-0.64, -0.42))
	sides = (GREEN_DARK, GREEN, TEAM, GREEN_DARK, TEAM, GREEN)
	prism(mesh, footprint, 1.44, 2.10, GREEN, top_color=GREEN_LIGHT, inset=0.93, side_colors=sides)
	block(mesh, -0.26, 0.26, -0.82, -0.62, 1.66, 1.92, GREEN_DARK)
	cylinder(mesh, (0.0, -0.80, 1.80), (0.0, -2.12, 1.80), 0.05, GUNMETAL, segments=6)
	cylinder(mesh, (0.0, -2.12, 1.80), (0.0, -2.26, 1.80), 0.08, BLACK, segments=6)
	block(mesh, -0.46, -0.16, -0.30, 0.02, 2.08, 2.26, GUNMETAL)
	block(mesh, -0.44, -0.18, -0.34, -0.30, 2.12, 2.22, GLASS, outline=False)
	return scaled(merge(mesh, _bradley_launcher(raised)), IFV_SCALE)


def usifv_turret_raised() -> Mesh:
	return usifv_turret(raised=True)


# ---------------------------------------------------------------------------
# USICV / USSHORAD — shared eight-wheel V-hull family (contract §5.2, §8.3)
# ---------------------------------------------------------------------------


STRYKER_WHEELS = (-1.44, -0.52, 0.42, 1.34)
STRYKER_BASE, STRYKER_ROOF = 0.86, 1.16


def _on_stryker_roof(mesh: Mesh) -> Mesh:
	# Turret meshes are authored against a 1.10 roof; seat them on the real one.
	return transformed(mesh, lambda p: (p[0], p[1], p[2] + STRYKER_ROOF - 1.10))


def _stryker_chassis(*, ramp: bool) -> Mesh:
	mesh = Mesh()
	center = (0.0, 0.0, 0.7)
	base, roof = STRYKER_BASE, STRYKER_ROOF
	# Landmark 2: the pronounced V-shaped underside - a deep dark wedge that
	# shows above and between the wheels on side facings, tapers up at both
	# ends, and reads as a clear V from front and rear.
	keel = 0.24
	y0, y1 = -1.90, 1.98
	k0, k1 = y0 + 0.95, y1 - 0.70
	for side in (-1, 1):
		add_face(mesh, ((side * 1.06, y0 + 0.10, base), (side * 1.06, y1, base), (side * keel, k1, 0.08), (side * keel, k0, 0.08)), VHULL, outward_from=center)
	add_face(mesh, ((-keel, k0, 0.08), (keel, k0, 0.08), (keel, k1, 0.08), (-keel, k1, 0.08)), VHULL, outward_from=center)
	add_face(mesh, ((-1.06, y0 + 0.10, base), (1.06, y0 + 0.10, base), (keel, k0, 0.08), (-keel, k0, 0.08)), VHULL, outward_from=center)
	add_face(mesh, ((-1.06, y1, base), (1.06, y1, base), (keel, k1, 0.08), (-keel, k1, 0.08)), VHULL, outward_from=center)
	# Landmark 1: eight large road wheels in one long, flat, unbroken line.
	_wheel_line(mesh, STRYKER_WHEELS, x=0.98, radius=0.33, width=0.24)
	# Low, flat upper hull with a noticeably lower roofline than ARAS8.
	# Player colour zone 1: the upper hull side above the wheels (faces 1 and 3).
	prism(mesh, ((-1.12, -1.60), (1.12, -1.60), (1.12, 1.98), (-1.12, 1.98)), base, roof, GREEN, top_color=GREEN_LIGHT, inset=0.98, side_colors=(GREEN_DARK, TEAM, GREEN_DARK, TEAM))
	add_face(mesh, ((-1.10, -1.60, roof), (1.10, -1.60, roof), (1.04, -2.12, base + 0.10), (-1.04, -2.12, base + 0.10)), GREEN_LIGHT, outward_from=center)
	add_face(mesh, ((-1.04, -2.12, base + 0.10), (1.04, -2.12, base + 0.10), (1.06, -1.96, base), (-1.06, -1.96, base)), GREEN_DARK, outward_from=center)
	for side in (-1, 1):
		add_face(mesh, ((side * 1.12, -1.60, roof), (side * 1.12, -1.60, base), (side * 1.06, -1.96, base), (side * 1.04, -2.12, base + 0.10)), GREEN, outward_from=center)
	# Front engine grille (right) and driver hatch (left) set the nose.
	block(mesh, 0.18, 0.92, -1.56, -1.10, roof - 0.01, roof + 0.03, BLACK, outline=False)
	block(mesh, -0.86, -0.46, -1.52, -1.16, roof, roof + 0.10, GREEN_DARK)
	for x in (-0.92, 0.74):
		block(mesh, x, x + 0.18, -2.16, -2.08, base + 0.12, base + 0.22, LAMP, outline=False)
	if ramp:
		# Troop carrier: rear ramp outline and roof hatches.
		block(mesh, -0.70, 0.70, 1.98, 2.04, base + 0.04, roof - 0.04, GREEN_DARK)
		block(mesh, -0.62, 0.62, 2.03, 2.06, base + 0.10, roof - 0.10, BLACK, outline=False)
		for x0 in (-0.78, 0.22):
			block(mesh, x0, x0 + 0.56, 0.72, 1.40, roof, roof + 0.05, GREEN_DARK, outline=False)
	else:
		# Air defense variant: sealed flanks and a flat, doorless rear.
		block(mesh, -0.86, 0.86, 1.10, 1.86, roof, roof + 0.14, GREEN_DARK, top_color=GREEN)
	return mesh


def usicv_hull() -> Mesh:
	return _stryker_chassis(ramp=True)


def usicv_turret() -> Mesh:
	mesh = Mesh()
	# Landmark 3: small remote weapon station perched well forward on the roof
	# and offset from the centreline; its body is player colour zone 2.
	cx, cy = 0.46, -1.02
	cylinder(mesh, (cx, cy, 1.10), (cx, cy, 1.22), 0.24, GUNMETAL, segments=8)
	block(mesh, cx - 0.22, cx + 0.22, cy - 0.20, cy + 0.26, 1.20, 1.46, TEAM, top_color=TEAM_DARK)
	block(mesh, cx - 0.30, cx - 0.18, cy - 0.12, cy + 0.10, 1.30, 1.44, GLASS, outline=False)
	cylinder(mesh, (cx + 0.04, cy - 0.20, 1.34), (cx + 0.04, cy - 0.98, 1.34), 0.05, GUNMETAL, segments=6)
	return _on_stryker_roof(mesh)


def _shorad_mast(deployed: bool) -> Mesh:
	mesh = Mesh()
	# Landmark 1: tall mission-equipment mast off the rear roof with a flat
	# panel radar face - the tallest element on any U.S. ground vehicle.
	if deployed:
		beam(mesh, (0.0, 1.50, 1.20), (0.0, 1.50, 2.70), 0.18, 0.18, GUNMETAL)
		block(mesh, -0.52, 0.52, 1.40, 1.54, 2.40, 3.20, GUNMETAL)
		block(mesh, -0.45, 0.45, 1.37, 1.40, 2.47, 3.13, RADAR_FACE, outline=False)
	else:
		beam(mesh, (0.0, 1.64, 1.30), (0.0, 0.20, 1.30), 0.16, 0.12, GUNMETAL)
		block(mesh, -0.52, 0.52, -0.40, 0.40, 1.26, 1.38, GUNMETAL)
		block(mesh, -0.45, 0.45, -0.33, 0.33, 1.38, 1.40, RADAR_FACE, outline=False)
	return mesh


def usshorad_hull() -> Mesh:
	return merge(_stryker_chassis(ramp=False), _shorad_mast(True))


def usshorad_hull_stowed() -> Mesh:
	return merge(_stryker_chassis(ramp=False), _shorad_mast(False))


def usshorad_turret() -> Mesh:
	mesh = Mesh()
	# Landmark 2: twin stubby missile pods flanking a short gun barrel on a
	# compact turret; the turret cheeks are player colour zone 2.
	footprint = ((-0.40, -0.66), (0.40, -0.66), (0.48, -0.40), (0.48, 0.34), (-0.48, 0.34), (-0.48, -0.40))
	sides = (GREEN_DARK, TEAM, TEAM, GREEN_DARK, TEAM, TEAM)
	prism(mesh, footprint, 1.10, 1.52, GREEN, top_color=GREEN_LIGHT, inset=0.92, side_colors=sides)
	cylinder(mesh, (0.0, -0.66, 1.32), (0.0, -1.34, 1.32), 0.07, GUNMETAL, segments=6)
	for side in (-1, 1):
		x0, x1 = (0.50, 0.84) if side > 0 else (-0.84, -0.50)
		block(mesh, x0, x1, -0.60, 0.22, 1.24, 1.58, TUBE_DARK, top_color=TUBE)
		for z in (1.30, 1.44):
			for offset in (0.06, 0.20):
				xa = (x0 + offset) if side > 0 else (x1 - offset - 0.10)
				block(mesh, xa, xa + 0.10, -0.66, -0.60, z, z + 0.09, BLACK, outline=False)
	return _on_stryker_roof(mesh)


# ---------------------------------------------------------------------------
# USHIMARS — M142 launcher (contract §5.2)
# ---------------------------------------------------------------------------


def ushimars_chassis() -> Mesh:
	mesh = Mesh()
	center = (0.0, 0.0, 0.8)
	# Landmark 2: six large wheels with an armoured cab set well forward,
	# leaving a visible gap between cab and pod.
	_wheel_line(mesh, (-1.46, 0.78, 1.56), x=0.96, radius=0.40, width=0.28)
	block(mesh, -0.70, 0.70, -1.90, 2.04, 0.50, 0.78, GREEN_DARK)
	for y in (0.78, 1.56):
		block(mesh, -1.14, 1.14, y - 0.46, y + 0.46, 0.80, 0.86, GREEN_DARK, outline=False)
	prism(mesh, ((-1.02, -2.16), (1.02, -2.16), (1.02, -0.98), (-1.02, -0.98)), 0.66, 1.62, GREEN, top_color=GREEN_LIGHT, inset=0.88, shift=(0.0, 0.06))
	add_face(mesh, ((-0.80, -2.12, 1.30), (0.80, -2.12, 1.30), (0.78, -2.06, 1.50), (-0.78, -2.06, 1.50)), GLASS, outward_from=center, outline=False)
	for side in (-1, 1):
		# Player colour zone 1: cab door panel.
		x0, x1 = (1.01, 1.05) if side > 0 else (-1.05, -1.01)
		block(mesh, x0, x1, -1.94, -1.12, 0.74, 1.46, TEAM)
		block(mesh, x0, x1, -1.80, -1.50, 1.18, 1.34, GLASS, outline=False)
	for x in (-0.90, 0.72):
		block(mesh, x, x + 0.18, -2.22, -2.14, 0.72, 0.82, LAMP, outline=False)
	# Bed between cab and pod (the visible gap) and the pod cradle.
	block(mesh, -0.86, 0.86, -0.96, -0.46, 0.78, 0.84, GREEN_DARK)
	block(mesh, -0.80, 0.80, -0.40, 1.98, 0.84, 0.96, GUNMETAL)
	return mesh


def _himars_pod(raised: bool) -> Mesh:
	mesh = Mesh()
	# Landmark 1: one squared launch pod carried high - not a tube bundle.
	block(mesh, -0.74, 0.74, -0.36, 1.94, 0.98, 1.78, GREEN, top_color=GREEN_LIGHT)
	# Launch face at the front end; its frame is player colour zone 2.  The
	# pod faces themselves stay neutral so the raise/lower read survives.
	block(mesh, -0.78, 0.78, -0.44, -0.34, 0.94, 1.82, TEAM)
	for x in (-0.46, 0.02):
		for z in (1.08, 1.42):
			block(mesh, x, x + 0.44, -0.47, -0.44, z, z + 0.28, BLACK, outline=False)
	block(mesh, -0.74, 0.74, 1.90, 1.98, 1.00, 1.76, GREEN_DARK)
	if raised:
		# Landmark 3: the pod elevates to a steep angle before firing.
		mesh = transformed(mesh, rotate_about_x((0.0, 1.94, 0.98), -48))
	return mesh


def _himars_scale(mesh: Mesh) -> Mesh:
	# Stretch to V2RL-comparable length while keeping authored proportions.
	return transformed(mesh, lambda p: (p[0] * 1.04, p[1] * 1.16, p[2] * 1.06))


def ushimars_body() -> Mesh:
	return _himars_scale(ushimars_chassis())


def ushimars_pod() -> Mesh:
	return _himars_scale(_himars_pod(False))


def ushimars_pod_raised() -> Mesh:
	return _himars_scale(_himars_pod(True))


# ---------------------------------------------------------------------------
# USRECOV — M88-family recovery vehicle (contract §5.2)
# ---------------------------------------------------------------------------


def _recov_boom(raised: bool) -> Mesh:
	mesh = Mesh()
	# Landmark 1: heavy A-frame boom folded flat along the hull top; its frame
	# members are player colour zone 2.
	pivot_y, pivot_z = -1.78, 1.70
	for side in (-1, 1):
		beam(mesh, (side * 0.78, pivot_y, pivot_z), (side * 0.20, 1.34, pivot_z + 0.10), 0.18, 0.18, TEAM)
	beam(mesh, (-0.26, 1.34, pivot_z + 0.10), (0.26, 1.34, pivot_z + 0.10), 0.20, 0.20, TEAM_DARK)
	beam(mesh, (-0.62, -0.60, pivot_z + 0.04), (0.62, -0.60, pivot_z + 0.04), 0.10, 0.10, TEAM_DARK)
	if raised:
		lift = rotate_about_x((0.0, pivot_y, pivot_z), 62)
		mesh = transformed(mesh, lift)
		# Hoist cable hangs from the raised apex.
		apex = lift((0.0, 1.34, pivot_z + 0.10))
		beam(mesh, apex, (0.0, apex[1] - 0.10, 0.60), 0.05, 0.05, BLACK)
	return mesh


def _recov_body() -> Mesh:
	mesh = Mesh()
	center = (0.0, 0.0, 0.8)
	_tracked_base(mesh, length=4.20, half_width=1.48, skirt_z=(0.30, 0.84))
	prism(mesh, ((-1.10, -1.94), (1.10, -1.94), (1.10, 2.06), (-1.10, 2.06)), 0.40, 1.12, GREEN, top_color=GREEN_LIGHT, inset=0.99)
	# Landmark 2: blunt, turretless hull with a tall front crew casemate
	# (its side panel is player colour zone 1)...
	casemate = ((-1.10, -1.94), (1.10, -1.94), (1.10, -0.18), (-1.10, -0.18))
	prism(mesh, casemate, 1.10, 1.68, GREEN, top_color=GREEN_LIGHT, inset=0.94, side_colors=(GREEN_DARK, TEAM, GREEN_DARK, TEAM))
	block(mesh, -0.70, -0.30, -1.20, -0.80, 1.66, 1.80, GREEN_DARK)
	block(mesh, 0.36, 0.78, -1.40, -1.00, 1.66, 1.76, GUNMETAL)
	# ...and a broad front dozer blade, wider than the tracks.
	add_face(mesh, ((-1.56, -2.30, 0.78), (1.56, -2.30, 0.78), (1.56, -2.46, 0.06), (-1.56, -2.46, 0.06)), STEEL, outward_from=center)
	add_face(mesh, ((-1.56, -2.18, 0.78), (1.56, -2.18, 0.78), (1.56, -2.30, 0.78), (-1.56, -2.30, 0.78)), STEEL_DARK, outward_from=center)
	for side in (-1, 1):
		beam(mesh, (side * 1.00, -2.24, 0.42), (side * 1.00, -1.60, 0.60), 0.16, 0.16, STEEL_DARK)
	# Landmark 3: thick spooled cable drum on the hull rear.
	cylinder(mesh, (-0.84, 1.78, 1.40), (0.84, 1.78, 1.40), 0.34, GUNMETAL, segments=10, cap_color=STEEL)
	for x in (-0.54, -0.18, 0.18, 0.54):
		cylinder(mesh, (x, 1.78, 1.40), (x + 0.16, 1.78, 1.40), 0.37, BLACK, segments=10)
	for x in (-0.90, 0.72):
		block(mesh, x, x + 0.18, -2.02, -1.94, 1.20, 1.30, LAMP, outline=False)
	return mesh


def usrecov_hull() -> Mesh:
	return merge(_recov_body(), _recov_boom(False))


def usrecov_hull_working() -> Mesh:
	return merge(_recov_body(), _recov_boom(True))


# ---------------------------------------------------------------------------
# Aircraft (contract §5.3).  Wings are authored as upward-facing plates so the
# planform is never lost to back-face culling.
# ---------------------------------------------------------------------------


def _slab(mesh: Mesh, outline: list[tuple[float, float]], z0: float, z1: float, color: Color, top: Color | None = None) -> None:
	prism(mesh, outline, z0, z1, color, top_color=top or color)


def usf35_airframe(bay_open: bool = False) -> Mesh:
	mesh = Mesh()
	# Landmark 1: one broad chined nose blending straight into the wing root -
	# a lifting body, not a fuselage tube.
	_slab(mesh, [(0.0, -2.78), (0.40, -2.10), (0.66, -1.20), (0.80, -0.20), (0.76, 1.40), (0.52, 2.24), (-0.52, 2.24), (-0.76, 1.40), (-0.80, -0.20), (-0.66, -1.20), (-0.40, -2.10)], 0.36, 0.60, AIR_DARKER, AIR_DARK)
	prism(mesh, [(0.0, -2.30), (0.30, -1.60), (0.34, 1.60), (0.0, 2.20), (-0.34, 1.60), (-0.30, -1.60)], 0.58, 0.80, AIR_DARK, top_color=AIR_DARK, inset=0.70)
	prism(mesh, [(0.0, -2.00), (0.18, -1.62), (0.20, -0.84), (-0.20, -0.84), (-0.18, -1.62)], 0.74, 0.98, GLASS, inset=0.6)
	# Player colour zone 2: a thin spine stripe.
	block(mesh, -0.15, 0.15, -1.10, 1.90, 0.80, 0.86, TEAM, outline=False)
	for side in (-1, 1):
		# Wide-chord trapezoid wing and stabilator.
		_slab(mesh, [(side * 0.76, -0.62), (side * 2.30, 0.58), (side * 2.30, 1.02), (side * 0.76, 1.30)], 0.44, 0.52, AIR_DARKER, AIR_DARK)
		_slab(mesh, [(side * 0.50, 1.54), (side * 1.46, 2.02), (side * 1.46, 2.40), (side * 0.50, 2.40)], 0.46, 0.52, AIR_DARKER, AIR_DARK)
		# Landmark 2: two strongly canted tail fins forming a shallow V from
		# above; player colour zone 1 is the band across their upper half.
		root = [(side * 0.52, 1.26, 0.62), (side * 0.52, 2.20, 0.62)]
		mid = [(side * 0.64, 2.28, 0.84), (side * 0.64, 1.42, 0.84)]
		tip = [(side * 0.92, 2.46, 1.30), (side * 0.92, 1.84, 1.30)]
		for a, b, color in ((root, mid, AIR_DARK), (mid, tip, TEAM)):
			quad = (a[0], a[1], b[0], b[1])
			add_face(mesh, quad, color, outward_from=(side * 0.2, 1.8, 0.2))
			add_face(mesh, quad, color, outward_from=(side * 2.0, 1.8, 1.4))
	if bay_open:
		# Attack-pass state: weapons-bay doors hang open with one store visible.
		for side in (-1, 1):
			add_face(mesh, ((side * 0.16, -0.60, 0.36), (side * 0.16, 0.70, 0.36), (side * 0.40, 0.70, 0.02), (side * 0.40, -0.60, 0.02)), AIR_DARK, outward_from=(0, 0, 0.4))
			add_face(mesh, ((side * 0.16, -0.60, 0.36), (side * 0.16, 0.70, 0.36), (side * 0.40, 0.70, 0.02), (side * 0.40, -0.60, 0.02)), AIR_DARK, outward_from=(side * 1.0, 0, -0.4))
		cylinder(mesh, (0.0, -0.40, 0.22), (0.0, 0.70, 0.22), 0.09, WHITE, segments=6)
	return mesh


def usf35_attack() -> Mesh:
	return usf35_airframe(bay_open=True)


def usmq9_airframe() -> Mesh:
	mesh = Mesh()
	# Thin fuselage with a drooped nose and a bulbous chin sensor ball (landmark 3).
	loft(mesh, [(-1.62, 0.06, 0.08, 0.34), (-1.40, 0.18, 0.20, 0.42), (-0.60, 0.20, 0.20, 0.50), (0.90, 0.16, 0.16, 0.50), (1.52, 0.07, 0.07, 0.50)], AIR_LIGHT, segments=8, top_color=AIR_PALE)
	cylinder(mesh, (0.0, -1.34, 0.20), (0.0, -1.20, 0.20), 0.18, GLASS, segments=8, cap_color=GUNMETAL)
	# Landmark 1: a very long, very thin, straight wing - by far the highest
	# aspect ratio in the catalog.  Wingtip panels are player colour zone 1.
	for side in (-1, 1):
		flat(mesh, [(side * 0.18, -0.20, 0.56), (side * 2.80, -0.12, 0.58), (side * 2.80, 0.16, 0.58), (side * 0.18, 0.26, 0.56)], AIR_PALE, both=True)
		flat(mesh, [(side * 2.80, -0.12, 0.58), (side * 3.60, -0.08, 0.60), (side * 3.60, 0.12, 0.60), (side * 2.80, 0.16, 0.58)], TEAM, both=True)
	# Landmark 2: downward-canted V tail (player colour zone 2) with a pusher
	# propeller behind it.
	for side in (-1, 1):
		tail = ((side * 0.06, 1.02, 0.48), (side * 0.06, 1.44, 0.48), (side * 0.82, 1.62, 0.10), (side * 0.82, 1.36, 0.10))
		add_face(mesh, tail, TEAM, outward_from=(-side * 1.0, 1.3, 0.1))
		add_face(mesh, tail, TEAM, outward_from=(side * 1.0, 1.3, 1.2))
	cylinder(mesh, (0.0, 1.56, 0.50), (0.0, 1.62, 0.50), 0.44, STEEL_DARK, segments=10)
	return mesh


def usmq9_loiter() -> Mesh:
	return usmq9_airframe()


def usuh60_airframe(doors_open: bool = False) -> Mesh:
	mesh = Mesh()
	center = (0.0, 0.0, 0.7)
	# Landmark 1: a wide, flat, low cabin with big square door openings.
	prism(mesh, ((-0.74, -1.10), (0.74, -1.10), (0.74, 0.96), (-0.74, 0.96)), 0.26, 1.06, ARMY_AIR, top_color=ARMY_AIR, inset=0.92)
	prism(mesh, ((-0.66, -1.90), (0.66, -1.90), (0.74, -1.10), (-0.74, -1.10)), 0.30, 0.98, ARMY_AIR, inset=0.80, shift=(0.0, 0.10))
	add_face(mesh, ((-0.54, -1.88, 0.62), (0.54, -1.88, 0.62), (0.56, -1.40, 0.98), (-0.56, -1.40, 0.98)), GLASS, outward_from=center, outline=False)
	for side in (-1, 1):
		x0, x1 = (0.74, 0.77) if side > 0 else (-0.77, -0.74)
		# Player colour zone 1: cabin door frames.
		block(mesh, x0, x1, -0.80, 0.70, 0.26, 1.06, TEAM)
		if doors_open:
			block(mesh, x0 + 0.01 * side, x1 + 0.01 * side, -0.52, 0.42, 0.40, 0.92, BLACK, outline=False)
			xs = (x0 + 0.04, x1 + 0.08) if side > 0 else (x0 - 0.08, x1 - 0.04)
			block(mesh, xs[0], xs[1], 0.48, 1.14, 0.34, 0.98, ARMY_AIR_DARK)
		else:
			block(mesh, x0 + 0.01 * side, x1 + 0.01 * side, -0.46, 0.36, 0.44, 0.90, ARMY_AIR_DARK, outline=False)
			block(mesh, x0 + 0.02 * side, x1 + 0.02 * side, -0.36, -0.06, 0.68, 0.86, GLASS, outline=False)
		block(mesh, x0, x1, -1.02, -0.72, 0.56, 0.92, GLASS, outline=False)
	# Engine deck and exhausts.
	block(mesh, -0.44, 0.44, -0.70, 0.64, 1.04, 1.36, ARMY_AIR_DARK)
	cylinder(mesh, (0.0, 0.0, 1.36), (0.0, 0.0, 1.52), 0.12, GUNMETAL)
	# Tail boom and landmark 2: a swept fin carrying a canted, high tail rotor.
	prism(mesh, ((-0.26, 0.90), (0.26, 0.90), (0.12, 3.30), (-0.12, 3.30)), 0.72, 1.06, ARMY_AIR, inset=0.9)
	fin = ((0.0, 3.00, 0.90), (0.0, 3.46, 0.92), (0.0, 3.74, 1.92), (0.0, 3.42, 1.96))
	add_face(mesh, fin, TEAM, outward_from=(-1.0, 3.3, 1.4))
	add_face(mesh, fin, TEAM, outward_from=(1.0, 3.3, 1.4))
	flat(mesh, [(-0.72, 3.02, 0.94), (0.72, 3.02, 0.94), (0.72, 3.30, 0.94), (-0.72, 3.30, 0.94)], ARMY_AIR_DARK, both=True)
	cylinder(mesh, (0.10, 3.52, 1.66), (0.20, 3.52, 1.72), 0.36, STEEL_DARK, segments=10)
	# Landmark 3: fixed gear with a distinctly long tail-wheel arm.
	for side in (-1, 1):
		beam(mesh, (side * 0.60, -0.92, 0.30), (side * 0.84, -0.96, 0.10), 0.06, 0.06, GUNMETAL)
		cylinder(mesh, (side * 0.80, -0.96, 0.10), (side * 0.92, -0.96, 0.10), 0.10, RUBBER, segments=6)
	beam(mesh, (0.0, 2.10, 0.76), (0.0, 2.62, 0.08), 0.07, 0.07, GUNMETAL)
	cylinder(mesh, (-0.05, 2.64, 0.07), (0.05, 2.64, 0.07), 0.08, RUBBER, segments=6)
	return mesh


def usuh60_unload() -> Mesh:
	return usuh60_airframe(doors_open=True)


def usuh60_rotor() -> Mesh:
	mesh = Mesh()
	# Four-blade main rotor; the motion-blur disc is added by the renderer.
	for index in range(4):
		angle = math.radians(20 + index * 90)
		tip = (math.cos(angle) * 2.55, math.sin(angle) * 2.55 - 0.05, 1.60)
		flat(mesh, [(tip[0] * 0.08 - math.sin(angle) * 0.10, tip[1] * 0.08 + math.cos(angle) * 0.10, 1.60),
				   (tip[0] - math.sin(angle) * 0.10, tip[1] + math.cos(angle) * 0.10, 1.60),
				   (tip[0] + math.sin(angle) * 0.10, tip[1] - math.cos(angle) * 0.10, 1.60),
				   (tip[0] * 0.08 + math.sin(angle) * 0.10, tip[1] * 0.08 - math.cos(angle) * 0.10, 1.60)], (132, 134, 128), both=True, outline=False)
	cylinder(mesh, (0.0, -0.05, 1.52), (0.0, -0.05, 1.66), 0.16, GUNMETAL)
	return mesh


def usac130_airframe() -> Mesh:
	mesh = Mesh()
	# Landmark 2: a long, fat fuselage with a tall square tail fin.
	loft(mesh, [(-3.20, 0.18, 0.18, 0.62), (-2.90, 0.48, 0.46, 0.66), (-2.30, 0.60, 0.58, 0.70), (1.40, 0.60, 0.58, 0.70), (2.60, 0.40, 0.36, 0.90), (3.30, 0.16, 0.14, 1.06)], AIR_DARKER, segments=10, top_color=AIR_DARK)
	add_face(mesh, ((-0.40, -3.02, 0.84), (0.40, -3.02, 0.84), (0.34, -2.72, 1.14), (-0.34, -2.72, 1.14)), GLASS, up=True, outline=False)
	# Landmark 1: a high straight wing carrying four propellers; the engine
	# nacelle bands are player colour zone 2.
	for side in (-1, 1):
		flat(mesh, [(side * 0.40, -0.66, 1.26), (side * 4.30, -0.46, 1.24), (side * 4.30, 0.12, 1.24), (side * 0.40, 0.36, 1.26)], AIR_DARK, both=True)
		for x in (1.40, 2.62):
			cylinder(mesh, (side * x, -1.30, 1.10), (side * x, 0.40, 1.10), 0.20, AIR_DARKER, segments=8)
			cylinder(mesh, (side * x, -0.90, 1.10), (side * x, -0.58, 1.10), 0.23, TEAM, segments=8)
			cylinder(mesh, (side * x, -1.40, 1.10), (side * x, -1.36, 1.10), 0.46, STEEL, segments=10)
	# Tail plane and the square fin (player colour zone 1).
	flat(mesh, [(-1.70, 2.46, 1.10), (1.70, 2.46, 1.10), (1.70, 3.10, 1.10), (-1.70, 3.10, 1.10)], AIR_DARK, both=True)
	fin = ((0.0, 2.10, 1.10), (0.0, 3.30, 1.16), (0.0, 3.36, 2.84), (0.0, 2.64, 2.84))
	add_face(mesh, fin, TEAM, outward_from=(-1.0, 2.8, 1.8))
	add_face(mesh, fin, TEAM, outward_from=(1.0, 2.8, 1.8))
	# Landmark 3: gun ports along the left side only.
	for y, size in ((-1.30, 0.12), (-0.60, 0.12), (0.30, 0.20)):
		block(mesh, -0.62, -0.58, y - size, y + size, 0.58, 0.58 + size * 1.6, BLACK, outline=False)
	return mesh


# ---------------------------------------------------------------------------
# Navy (contract §5.4)
# ---------------------------------------------------------------------------


def _ship_hull(outline: list[tuple[float, float]], freeboard: float, side: Color, deck: Color) -> Mesh:
	mesh = Mesh()
	prism(mesh, outline, 0.0, freeboard, side, top_color=deck)
	return mesh


DDG_OUTLINE = [(0.0, -5.10), (0.52, -4.20), (0.74, -2.80), (0.76, 3.90), (0.64, 5.00), (-0.64, 5.00), (-0.76, 3.90), (-0.74, -2.80), (-0.52, -4.20)]


def _vls_deck(mesh: Mesh, y0: float, y1: float, z: float) -> None:
	block(mesh, -0.44, 0.44, y0, y1, z, z + 0.05, DECK_DARK, outline=False)
	rows = 4
	for index in range(rows):
		y = y0 + 0.06 + index * (y1 - y0 - 0.06) / rows
		for x in (-0.36, 0.04):
			block(mesh, x, x + 0.32, y, y + (y1 - y0) / rows * 0.55, z + 0.05, z + 0.08, HAZE_LIGHT, outline=False)


def usddg_hull() -> Mesh:
	mesh = _ship_hull(DDG_OUTLINE, 0.56, HAZE, DECK)
	# Landmark 2: flat vertical-launch cell decks fore and aft (hatched).
	_vls_deck(mesh, -3.40, -2.50, 0.56)
	_vls_deck(mesh, 2.02, 2.74, 0.56)
	# Landmark 1: a blocky superstructure with large flat radar panels on its
	# four chamfered corners - two visible from any facing.
	house = ((-0.36, -2.24), (0.36, -2.24), (0.74, -1.84), (0.74, -0.34), (0.36, 0.06), (-0.36, 0.06), (-0.74, -0.34), (-0.74, -1.84))
	sides = (HAZE_LIGHT, RADAR_FACE, HAZE, RADAR_FACE, HAZE_LIGHT, RADAR_FACE, HAZE, RADAR_FACE)
	prism(mesh, house, 0.56, 1.86, HAZE, top_color=HAZE_LIGHT, inset=0.90, side_colors=sides)
	# Player colour zone 1: superstructure side band at its base.
	for side in (-1, 1):
		x0, x1 = (0.74, 0.80) if side > 0 else (-0.80, -0.74)
		block(mesh, x0, x1, -1.84, -0.34, 0.58, 1.42, TEAM)
	block(mesh, -0.40, 0.40, -1.60, -0.60, 1.84, 2.16, HAZE_LIGHT)
	beam(mesh, (0.0, -1.10, 2.10), (0.0, -1.00, 3.00), 0.10, 0.10, HAZE_DARK)
	beam(mesh, (-0.52, -1.02, 2.70), (0.52, -1.02, 2.70), 0.06, 0.06, HAZE_DARK)
	# Landmark 3: one squat funnel amidships; its cap is player colour zone 2.
	prism(mesh, ((-0.34, 0.40), (0.34, 0.40), (0.40, 0.66), (0.40, 1.26), (-0.40, 1.26), (-0.40, 0.66)), 0.56, 1.36, HAZE_DARK, inset=0.90)
	prism(mesh, ((-0.32, 0.46), (0.32, 0.46), (0.37, 0.68), (0.37, 1.20), (-0.37, 1.20), (-0.37, 0.68)), 1.36, 1.58, TEAM, top_color=BLACK, inset=0.95)
	# Aft hangar block and flight deck.
	block(mesh, -0.58, 0.58, 2.86, 3.42, 0.56, 1.10, HAZE, top_color=HAZE_LIGHT)
	block(mesh, -0.56, 0.56, 3.50, 4.90, 0.56, 0.59, DECK_DARK, outline=False)
	return mesh


def usddg_turret() -> Mesh:
	mesh = Mesh()
	cy = -4.00
	cylinder(mesh, (0.0, cy, 0.56), (0.0, cy, 0.64), 0.34, HAZE_DARK)
	prism(mesh, ((-0.28, cy - 0.30), (0.28, cy - 0.30), (0.32, cy + 0.10), (0.24, cy + 0.34), (-0.24, cy + 0.34), (-0.32, cy + 0.10)), 0.62, 0.96, HAZE_LIGHT, inset=0.8, shift=(0.0, 0.06))
	cylinder(mesh, (0.0, cy - 0.24, 0.82), (0.0, cy - 1.00, 0.84), 0.05, GUNMETAL, segments=6)
	return mesh


def usssn_hull() -> Mesh:
	mesh = Mesh()
	# Landmark 1: a smooth teardrop hull with no deck clutter, clearly fatter
	# than stock SS.
	loft(mesh, [(-4.62, 0.04, 0.04, 0.0), (-4.30, 0.38, 0.30, 0.0), (-3.70, 0.58, 0.44, 0.0), (-2.40, 0.64, 0.50, 0.0),
				(2.00, 0.64, 0.50, 0.0), (3.40, 0.44, 0.36, 0.0), (4.30, 0.14, 0.12, 0.0), (4.62, 0.04, 0.04, 0.0)],
		 SUB_BLACK, segments=12, z_clip=-0.02, top_color=SUB_BLACK)
	# Player colour zone 2: a narrow deck stripe, visible only when surfaced.
	block(mesh, -0.09, 0.09, -1.20, 3.10, 0.49, 0.53, TEAM, outline=False)
	# Landmark 3: a row of small circular payload hatches on the forward deck.
	for index in range(6):
		y = -3.86 + index * 0.25
		cylinder(mesh, (0.0, y, 0.44), (0.0, y, 0.54), 0.09, HAZE_DARK, segments=6)
	# Landmark 2: a short, thick, rounded sail set well forward (sides are
	# player colour zone 1).
	sail = ((-0.16, -2.66), (0.16, -2.66), (0.28, -2.44), (0.28, -1.56), (0.18, -1.36), (-0.18, -1.36), (-0.28, -1.56), (-0.28, -2.44))
	prism(mesh, sail, 0.40, 1.32, SUB_BLACK, top_color=SUB_BLACK, inset=0.94, side_colors=(SUB_BLACK, TEAM, TEAM, SUB_BLACK, SUB_BLACK, SUB_BLACK, TEAM, TEAM))
	# Cruciform stern control surfaces.
	fin = ((0.0, 3.70, 0.20), (0.0, 4.34, 0.10), (0.0, 4.40, 0.70), (0.0, 3.98, 0.70))
	add_face(mesh, fin, SUB_BLACK, outward_from=(-1.0, 4.0, 0.4))
	add_face(mesh, fin, SUB_BLACK, outward_from=(1.0, 4.0, 0.4))
	flat(mesh, [(-0.72, 3.80, 0.06), (0.72, 3.80, 0.06), (0.72, 4.26, 0.06), (-0.72, 4.26, 0.06)], SUB_BLACK, both=True)
	return mesh


LPD_OUTLINE = [(0.0, -5.60), (0.62, -4.66), (0.96, -3.20), (0.96, 4.96), (0.90, 5.50), (-0.90, 5.50), (-0.96, 4.96), (-0.96, -3.20), (-0.62, -4.66)]


def uslpd_hull(ramp_down: bool = False) -> Mesh:
	mesh = _ship_hull(LPD_OUTLINE, 1.04, HAZE, DECK)
	# Player colour zone 1: a hull side band along the waterline.
	for side in (-1, 1):
		x = side * 0.97
		add_face(mesh, ((x, -3.10, 0.12), (x, 4.90, 0.12), (x, 4.90, 0.40), (x, -3.10, 0.40)), TEAM, outward_from=(0.0, 0.8, 0.3))
		add_face(mesh, ((side * 0.63, -4.60, 0.12), (x, -3.14, 0.12), (x, -3.14, 0.40), (side * 0.63, -4.60, 0.40)), TEAM, outward_from=(0.0, -3.2, 0.3))
	# Large faceted superstructure forward of the flight deck.
	house = ((-0.70, -3.40), (0.70, -3.40), (0.90, -3.00), (0.90, 0.60), (-0.90, 0.60), (-0.90, -3.00))
	prism(mesh, house, 1.04, 2.34, HAZE, top_color=HAZE_LIGHT, inset=0.86, side_colors=(HAZE_LIGHT, HAZE_LIGHT, HAZE, HAZE_DARK, HAZE, HAZE_LIGHT))
	block(mesh, -0.52, 0.52, -3.10, -2.66, 2.10, 2.44, GLASS)
	# Landmark 1: a tall enclosed faceted mast with sharply angled flat faces
	# (player colour zone 2).
	ring = [(math.cos(math.tau * i / 8 + math.pi / 8), math.sin(math.tau * i / 8 + math.pi / 8)) for i in range(8)]
	bottom = [(x * 0.56, -1.60 + y * 0.56, 2.30) for x, y in ring]
	top = [(x * 0.24, -1.60 + y * 0.24, 4.30) for x, y in ring]
	hull_solid(mesh, bottom, top, TEAM, top_color=TEAM_DARK, side_colors=(TEAM, TEAM_DARK, TEAM, TEAM_DARK, TEAM, TEAM_DARK, TEAM, TEAM_DARK))
	cylinder(mesh, (0.0, -1.60, 4.30), (0.0, -1.60, 4.70), 0.06, HAZE_DARK)
	# Landmark 2: a long flat helicopter deck occupying the entire stern.
	block(mesh, -0.86, 0.86, 0.64, 5.36, 1.04, 1.07, DECK_DARK, outline=False)
	block(mesh, -0.04, 0.04, 0.90, 5.20, 1.07, 1.08, WHITE, outline=False)
	for y in (2.10, 4.00):
		ring_pts = [(math.cos(a) * 0.40, y + math.sin(a) * 0.40, 1.08) for a in (math.tau * k / 10 for k in range(10))]
		inner = [(x * 0.72, y + (py - y) * 0.72, 1.08) for x, py, _ in ring_pts]
		for k in range(10):
			flat(mesh, [ring_pts[k], ring_pts[(k + 1) % 10], inner[(k + 1) % 10], inner[k]], WHITE, outline=False)
	# Landmark 3: a stern ramp that lowers into the water on unload.
	if ramp_down:
		add_face(mesh, ((-0.66, 5.50, 0.26), (0.66, 5.50, 0.26), (0.66, 6.40, -0.02), (-0.66, 6.40, -0.02)), HAZE_DARK, up=True)
		block(mesh, -0.62, 0.62, 5.46, 5.52, 0.28, 0.92, BLACK, outline=False)
	else:
		block(mesh, -0.66, 0.66, 5.50, 5.58, 0.20, 0.96, HAZE_DARK)
	return mesh


def uslpd_hull_ramp() -> Mesh:
	return uslpd_hull(ramp_down=True)


# ---------------------------------------------------------------------------
# Buildings and defenses (contract §5.5).  One cell is 24 px = 3.72 units.
# ---------------------------------------------------------------------------


CELL = 24 / 6.45


def _pad(mesh: Mesh, half_x: float, half_y: float, color: Color = CONCRETE) -> None:
	block(mesh, -half_x, half_x, -half_y, half_y, 0.0, 0.08, color, top_color=color)


def ustoc_structure(active: bool = True) -> Mesh:
	mesh = Mesh()
	# Landmark 1: two boxy shelter containers side by side with a covered
	# walkway between them; the container end walls are player colour zone 1.
	for x0, x1 in ((-3.30, -1.05), (1.05, 3.30)):
		prism(mesh, ((x0, -1.20), (x1, -1.20), (x1, 2.60), (x0, 2.60)), 0.0, 1.55, GREEN, top_color=GREEN_LIGHT, side_colors=(TEAM, GREEN, TEAM, GREEN))
		for index in range(3):
			y = -0.90 + index * 1.15
			block(mesh, x0 + 0.22, x1 - 0.22, y, y + 0.18, 1.55, 1.62, GREEN_DARK, outline=False)
		block(mesh, (x0 + x1) / 2 - 0.40, (x0 + x1) / 2 + 0.40, 2.60, 2.64, 0.0, 1.10, GREEN_DARK, outline=False)
	block(mesh, -1.05, 1.05, -0.60, 2.20, 1.12, 1.26, KHAKI_DARK, top_color=KHAKI)
	for x in (-0.95, 0.85):
		for y in (-0.50, 2.00):
			block(mesh, x, x + 0.10, y, y + 0.10, 0.0, 1.14, GUNMETAL, outline=False)
	# Landmark 2: a large mesh dish on a short mast behind the shelters; the
	# dish mount is player colour zone 2.
	mx, my = 0.0, -2.30
	cylinder(mesh, (mx, my, 0.0), (mx, my, 1.90), 0.18, GUNMETAL)
	block(mesh, mx - 0.42, mx + 0.42, my - 0.36, my + 0.36, 1.70, 2.20, TEAM)
	tilt = math.radians(38)
	rim = []
	for k in range(14):
		a = math.tau * k / 14
		u, v = math.cos(a) * 1.75, math.sin(a) * 1.75
		rim.append((mx + u, my + 0.30 + v * math.sin(tilt) * -1.0, 3.10 + v * math.cos(tilt)))
	add_face(mesh, rim, MESH_DISH, outward_from=(mx, my - 1.5, 2.2))
	add_face(mesh, rim, GUNMETAL, outward_from=(mx, my + 1.5, 4.0))
	for k in range(0, 14, 2):
		beam(mesh, (mx, my + 0.30, 3.10), rim[k], 0.05, 0.05, CONCRETE_DARK)
	beam(mesh, (mx, my + 0.30, 3.10), (mx, my + 1.10, 3.55), 0.07, 0.07, GUNMETAL)
	# Landmark 3: cable run and a generator skid on the ground.
	block(mesh, 2.00, 3.40, -2.90, -1.70, 0.0, 0.85, GREEN_DARK, top_color=GREEN)
	cylinder(mesh, (3.10, -2.10, 0.85), (3.10, -2.10, 1.30), 0.09, BLACK)
	for a, b in (((mx, my, 0.05), (-1.60, -1.20, 0.05)), ((2.00, -2.30, 0.05), (1.60, -1.20, 0.05)), ((-1.60, -1.20, 0.05), (-1.60, 3.20, 0.05))):
		beam(mesh, a, b, 0.09, 0.06, BLACK)
	if active:
		block(mesh, mx - 0.12, mx + 0.12, my + 1.00, my + 1.20, 3.46, 3.70, LAMP, outline=False)
	return mesh


def usiamd_structure(elevated: bool = False) -> Mesh:
	mesh = Mesh()
	# Landmark 1: a large flat panel array tilted back at a steep angle that
	# dominates the footprint; its frame edge is player colour zone 1.
	base_y = 1.80
	tilt = math.radians(34)

	def array_point(u: float, v: float, depth: float = 0.0) -> Vec3:
		return (u, base_y - v * math.sin(tilt) + depth * math.cos(tilt), 0.50 + v * math.cos(tilt) + depth * math.sin(tilt))

	outer = [array_point(-3.20, 0.0), array_point(-0.30, 0.0), array_point(-0.30, 3.40), array_point(-3.20, 3.40)]
	inner = [array_point(-2.98, 0.22, 0.02), array_point(-0.52, 0.22, 0.02), array_point(-0.52, 3.18, 0.02), array_point(-2.98, 3.18, 0.02)]
	back = [array_point(-3.20, 0.0, -0.26), array_point(-0.30, 0.0, -0.26), array_point(-0.30, 3.40, -0.26), array_point(-3.20, 3.40, -0.26)]
	hull_solid(mesh, back, outer, GUNMETAL, top_color=TEAM)
	add_face(mesh, inner, RADAR_FACE, outward_from=(-1.75, 0.02, 1.35), outline=False)
	for row in range(1, 4):
		v = 0.22 + row * (2.96 / 4)
		beam(mesh, array_point(-2.98, v, 0.04), array_point(-0.52, v, 0.04), 0.04, 0.02, (84, 100, 118))
	block(mesh, -3.00, -0.50, 1.60, 2.90, 0.0, 0.60, GREEN_DARK, top_color=GREEN)
	for x in (-2.80, -0.70):
		beam(mesh, (x, 2.60, 0.60), array_point(x, 2.60, -0.26), 0.14, 0.14, GUNMETAL)
	# Landmark 2: a separate four-canister launcher box that elevates to
	# near-vertical to fire; its sides are player colour zone 2.
	# The box lies across the footprint (pointing east) so that stowed reads
	# long and low and elevated reads as a tall column from the RA camera.
	launcher = Mesh()
	prism(launcher, ((0.10, 0.00), (3.50, 0.00), (3.50, 1.40), (0.10, 1.40)), 0.80, 1.96, GREEN, top_color=GREEN_LIGHT, side_colors=(TEAM, GREEN_DARK, TEAM, GREEN_DARK))
	for y in (0.12, 0.76):
		for z in (0.92, 1.46):
			block(launcher, 3.50, 3.62, y, y + 0.52, z, z + 0.42, KHAKI, outline=False)
	if elevated:
		launcher = transformed(launcher, rotate_about_y((0.10, 0.0, 0.80), 72))
	block(mesh, 0.00, 3.60, -0.10, 1.50, 0.20, 0.80, GUNMETAL)
	for x in (0.70, 2.80):
		cylinder(mesh, (x, -0.20, 0.30), (x, 1.60, 0.30), 0.30, RUBBER, segments=8)
	mesh = merge(mesh, launcher)
	# Landmark 3: a low power unit with a visible exhaust stack.
	block(mesh, 0.80, 2.60, -3.20, -1.90, 0.0, 0.80, GREEN_DARK, top_color=GREEN)
	cylinder(mesh, (2.20, -2.50, 0.80), (2.20, -2.50, 2.00), 0.14, BLACK)
	return mesh


def usiamd_firing() -> Mesh:
	return usiamd_structure(elevated=True)


def uscuas_structure() -> Mesh:
	mesh = Mesh()
	# Landmark 3: a sandbagged base ring - the cheap-emplacement read.
	for index in range(10):
		a0, a1 = math.tau * index / 10, math.tau * (index + 1) / 10
		r0, r1 = 1.10, 1.70
		pts = [(math.cos(a0) * r0, math.sin(a0) * r0), (math.cos(a0) * r1, math.sin(a0) * r1), (math.cos(a1) * r1, math.sin(a1) * r1), (math.cos(a1) * r0, math.sin(a1) * r0)]
		prism(mesh, pts, 0.0, 0.55, SANDBAG if index % 2 else SANDBAG_DARK, inset=0.92)
	# Landmark 2: a tight bundle of thin tube launchers pointed steeply upward;
	# the bundle frame is player colour zone 2.
	block(mesh, -0.10, 1.10, -0.40, 0.70, 0.30, 0.80, TEAM)
	for x in (0.05, 0.50, 0.95):
		for y in (-0.20, 0.30):
			cylinder(mesh, (x, y + 0.10, 0.80), (x, y - 0.55, 2.90), 0.15, TUBE_DARK, segments=6, cap_color=BLACK)
	beam(mesh, (-0.10, -0.05, 1.70), (1.10, -0.05, 1.70), 0.14, 0.14, TEAM)
	# Landmark 1: a small squared radar face on a short post (collar is zone 1).
	cylinder(mesh, (-0.70, 0.20, 0.0), (-0.70, 0.20, 1.90), 0.10, GUNMETAL)
	cylinder(mesh, (-0.70, 0.20, 1.10), (-0.70, 0.20, 1.40), 0.22, TEAM)
	block(mesh, -1.20, -0.20, 0.08, 0.16, 1.90, 2.80, RADAR_FACE)
	return mesh


def usnode_structure(active: bool = True) -> Mesh:
	mesh = Mesh()
	# Landmark 3: a tiny ground shelter box at the base (player colour zone 1).
	block(mesh, 0.30, 1.20, 0.30, 1.10, 0.0, 0.70, TEAM, top_color=TEAM_DARK)
	# Landmark 1: a single lattice mast, far taller than wide, with guy wires.
	height = 6.40
	legs = [(math.cos(a) * 0.24, -0.20 + math.sin(a) * 0.24) for a in (math.pi / 2, math.pi / 2 + math.tau / 3, math.pi / 2 + 2 * math.tau / 3)]
	for x, y in legs:
		beam(mesh, (x, y, 0.0), (x * 0.7, -0.20 + (y + 0.20) * 0.7, height), 0.07, 0.07, GUNMETAL)
	for index in range(7):
		z0 = index * height / 7
		z1 = z0 + height / 7
		a, b = legs[index % 3], legs[(index + 1) % 3]
		beam(mesh, (a[0], a[1], z0), (b[0], b[1], z1), 0.04, 0.04, STEEL_DARK)
	for x, y in ((1.60, -0.20), (-0.80, 1.20), (-0.80, -1.60)):
		beam(mesh, (0.0, -0.20, height * 0.72), (x, y, 0.02), 0.025, 0.025, STEEL_DARK)
	# Player colour zone 2: a band near the mast top.
	cylinder(mesh, (0.0, -0.20, height - 0.70), (0.0, -0.20, height - 0.40), 0.30, TEAM)
	# Landmark 2: a small drum-shaped sensor head at the top.
	cylinder(mesh, (0.0, -0.20, height), (0.0, -0.20, height + 0.56), 0.40, HAZE_LIGHT, cap_color=GUNMETAL)
	if active:
		block(mesh, -0.06, 0.06, -0.62, -0.58, height + 0.18, height + 0.36, LAMP, outline=False)
	return mesh


# ---------------------------------------------------------------------------
# Infantry (contract §5.1).  Built in pixel units on the 50x39 canvas.
# ---------------------------------------------------------------------------


def _limb(mesh: Mesh, a: Vec3, b: Vec3, width: float, color: Color) -> None:
	beam(mesh, a, b, width, width, color)


def _soldier(kind: str, pose: str = "stand") -> Mesh:
	"""An articulated low-poly figure; ``kind`` selects contract landmarks."""

	mesh = Mesh()
	slim = kind == "talonsix"
	crouch = pose in ("launch", "crouch") or kind == "usjav"
	shoulder = 2.80 if slim else 3.55
	hip_z = 5.6 if crouch else 6.8
	knee_z = 2.9 if crouch else 3.5
	chest_z = hip_z + 5.6
	lean = -0.7 if pose == "crouch" else 0.0
	stance = 2.7 if kind == "usjav" else 1.70
	leg = 2.2 if not slim else 1.9
	# Legs and boots.
	for side in (-1, 1):
		foot = (side * stance, 0.5 if side > 0 else -0.5, 0.0)
		knee = (side * (stance * 0.8), -1.2 if crouch else -0.2, knee_z)
		hip = (side * 1.1, 0.2, hip_z)
		tone = (UNIFORM_DARK if side < 0 else UNIFORM) if not slim else ((70, 74, 60) if side < 0 else (88, 92, 74))
		_limb(mesh, hip, knee, leg, tone)
		_limb(mesh, knee, (foot[0], foot[1], 1.0), leg * 0.9, tone)
		block(mesh, foot[0] - 0.8, foot[0] + 0.8, foot[1] - 1.3, foot[1] + 0.6, 0.0, 1.1, BOOTS)
	if slim:
		# TALONSIX landmark 3: slim body with a thigh rig (player colour zone 2).
		block(mesh, 1.20, 2.70, -1.00, 0.90, hip_z - 3.3, hip_z - 0.3, TEAM)
	# Torso.
	cloth = (88, 92, 74) if slim else UNIFORM
	block(mesh, -shoulder + 0.5, shoulder - 0.5, -1.2 + lean, 1.2 + lean, hip_z, chest_z, cloth)
	if kind == "usrifle":
		# USRIFLE landmark 3: front-heavy plate carrier with two square chest
		# pouches; the pouch faces are player colour zone 2.
		block(mesh, -3.30, 3.30, -2.00 + lean, 1.50 + lean, hip_z + 1.2, chest_z - 0.1, KIT)
		for x0 in (-3.15, 0.20):
			block(mesh, x0, x0 + 2.95, -2.95 + lean, -1.95 + lean, hip_z + 1.2, hip_z + 4.5, TEAM)
	elif kind == "talonsix":
		block(mesh, -2.00, 2.00, -1.50 + lean, 1.30 + lean, hip_z + 2.0, chest_z - 0.4, KIT_DARK)
	else:
		block(mesh, -2.50, 2.50, -1.60 + lean, 1.35 + lean, hip_z + 1.4, chest_z - 0.3, KIT)
	if kind == "usjtac":
		# JTAC landmark 1: radio pack whose tall whip antenna rises far above
		# the helmet and is never trimmed for canvas reasons.
		block(mesh, -1.80, 0.60, 1.20, 2.80, hip_z + 1.0, chest_z + 0.3, KIT_DARK)
		_limb(mesh, (-1.20, 2.10, chest_z + 0.1), (-1.30, 2.40, chest_z + 10.4), 0.85, BLACK)
		block(mesh, -1.70, -0.90, 2.00, 2.80, chest_z + 9.8, chest_z + 10.8, LAMP, outline=False)
	if kind == "usjav":
		block(mesh, -1.60, 1.60, 1.20, 2.60, hip_z + 1.0, chest_z - 0.2, KIT_DARK)
	# Arms.  USRIFLE's upper sleeve is its zone 3; USJTAC's shoulder panel is its zone 1.
	sleeve = TEAM if kind in ("usrifle", "usjtac") else cloth
	for side in (-1, 1):
		shoulder_point = (side * (shoulder - 0.4), 0.0 + lean, chest_z - 0.7)
		if kind == "usjtac" and pose == "deploy":
			hand = (side * 1.4, -3.0 + lean, chest_z - 1.2)
		elif kind == "usjav":
			hand = (side * 1.0, -2.0, chest_z + 1.0) if side > 0 else (-0.7, 1.0, chest_z + 2.2)
		else:
			hand = (side * 0.8 + 0.5, -3.4 + lean, chest_z - 1.7)
		elbow = (side * (shoulder + 0.2), -1.3 + lean, chest_z - 3.0)
		_limb(mesh, shoulder_point, elbow, 1.6, sleeve)
		_limb(mesh, elbow, hand, 1.4, cloth)
	# Head and headgear.
	head_z = chest_z + 0.3
	block(mesh, -1.50, 1.50, -1.40 + lean, 1.30 + lean, head_z, head_z + 2.5, SKIN)
	if kind in ("usrifle", "usjav"):
		# USRIFLE landmark 1: squared helmet with a bulky forward-tilted optic
		# and a stubby mandible cover; the cover band is player colour zone 1.
		prism(mesh, ((-2.70, -2.50 + lean), (2.70, -2.50 + lean), (2.70, 2.30 + lean), (-2.70, 2.30 + lean)), head_z + 1.3, head_z + 4.6, HELMET, top_color=HELMET, inset=0.88)
		block(mesh, -2.78, 2.78, -2.58 + lean, 2.38 + lean, head_z + 1.4, head_z + 2.5, TEAM)
		if kind == "usrifle":
			block(mesh, -1.40, 1.40, -2.70 + lean, -1.60 + lean, head_z - 0.3, head_z + 1.0, KIT_DARK)
			beam(mesh, (0.0, -2.0 + lean, head_z + 3.9), (0.0, -3.6 + lean, head_z + 3.0), 1.70, 1.30, NVG)
	else:
		# Low-profile bump helmet (USJTAC, TALONSIX).
		prism(mesh, ((-2.10, -1.90 + lean), (2.10, -1.90 + lean), (2.10, 1.80 + lean), (-2.10, 1.80 + lean)), head_z + 1.7, head_z + 3.7, UNIFORM_DARK, top_color=UNIFORM_DARK, inset=0.72)
		if kind == "usjtac":
			# Headset with a boom microphone.
			block(mesh, 1.50, 2.00, -0.50, 0.50, head_z + 0.7, head_z + 2.3, NVG)
			_limb(mesh, (1.70, -0.50, head_z + 0.9), (0.70, -1.90, head_z + 0.3), 0.40, NVG)
		else:
			# TALONSIX landmark 1: quad-tube night vision flipped down - a
			# four-pronged front.  The helmet cover strip is player colour zone 1.
			block(mesh, -2.25, 2.25, -1.95 + lean, 1.95 + lean, head_z + 2.4, head_z + 3.6, TEAM)
			for x in (-1.10, -0.38, 0.38, 1.10):
				cylinder(mesh, (x * 1.15, -1.50 + lean, head_z + 1.7), (x * 1.15, -3.70 + lean, head_z + 1.5), 0.42, NVG, segments=6, cap_color=(90, 220, 170))
	# Weapons and role equipment.
	if kind == "usrifle":
		# Landmark 2: chunky rifle with a fat suppressor can and a boxy sight.
		wz = chest_z - 1.5 + (0.7 if pose == "fire" else 0.0)
		block(mesh, 1.20, 2.50, -4.20 + lean, 1.00 + lean, wz - 0.90, wz + 0.90, WEAPON)
		cylinder(mesh, (1.85, -4.20 + lean, wz), (1.85, -7.00 + lean, wz), 0.85, WEAPON, segments=6, cap_color=BLACK)
		block(mesh, 1.30, 2.40, -2.90 + lean, -1.20 + lean, wz + 0.90, wz + 2.20, NVG)
		if pose == "fire":
			flat(mesh, [(1.85, -7.20, wz + 1.0), (3.05, -9.10, wz + 0.5), (1.85, -9.90, wz), (0.65, -9.10, wz + 0.5)], (226, 206, 146), both=True, outline=False)
	elif kind == "usjav":
		# Landmark 1: fat, blunt, square-shouldered tube at a steep upward
		# angle; landmark 2: boxy command launch unit under it with a squared
		# eyepiece hood.  The rear grip housing is player colour zone 2; the
		# tube stays neutral olive.
		rear = (0.3, 4.4, chest_z - 1.0)
		front = (0.3, -4.6, chest_z + 5.0)
		beam(mesh, rear, front, 2.70, 2.70, TUBE, up=(1.0, 0.0, 0.0))
		cylinder(mesh, front, (front[0], front[1] - 0.30, front[2] + 0.20), 1.55, TUBE_DARK, segments=8)
		block(mesh, -1.30, 1.90, 1.80, 4.50, chest_z - 2.9, chest_z + 0.3, TEAM)
		block(mesh, -0.70, 1.50, -1.60, 0.80, chest_z + 0.2, chest_z + 1.9, KIT_DARK)
		block(mesh, -0.40, 0.80, 0.80, 1.60, chest_z + 0.7, chest_z + 2.0, NVG)
		if pose == "launch":
			tip = (front[0], front[1] - 3.2, front[2] + 2.8)
			cylinder(mesh, front, tip, 0.45, WHITE, segments=6)
			flat(mesh, [(0.3, 5.0, chest_z - 1.8), (2.6, 8.4, chest_z - 3.2), (0.3, 9.6, chest_z - 3.6), (-2.0, 8.4, chest_z - 3.2)], (214, 204, 184), both=True, outline=False)
	elif kind == "usjtac":
		# Landmark 2: flat slab tablet held chest-high; its back shell is zone 2.
		tz = chest_z - (1.0 if pose == "deploy" else 2.6)
		ty = -3.3 if pose == "deploy" else -2.6
		block(mesh, -1.90, 1.90, ty - 0.45 + lean, ty + 0.10 + lean, tz - 1.6, tz + 0.9, TEAM)
		block(mesh, -1.60, 1.60, ty + 0.10 + lean, ty + 0.20 + lean, tz - 1.3, tz + 0.6, (70, 130, 140), outline=False)
		block(mesh, -2.90, -2.20, -1.40, 1.80, hip_z + 0.4, hip_z + 1.4, WEAPON)
	elif kind == "talonsix":
		# Landmark 2: compact suppressed carbine held tight to the chest.
		wz = chest_z - 2.0
		block(mesh, -0.70, 0.50, -2.90 + lean, -0.40 + lean, wz - 0.6, wz + 0.6, WEAPON)
		cylinder(mesh, (-0.10, -2.90 + lean, wz), (-0.10, -4.20 + lean, wz), 0.52, WEAPON_LIGHT, segments=6)
	return mesh


def usrifle_figure() -> Mesh:
	return _soldier("usrifle")


def usrifle_fire() -> Mesh:
	return _soldier("usrifle", "fire")


def usjav_figure() -> Mesh:
	return _soldier("usjav")


def usjav_launch() -> Mesh:
	return _soldier("usjav", "launch")


def usjtac_figure() -> Mesh:
	return _soldier("usjtac")


def usjtac_deploy() -> Mesh:
	return _soldier("usjtac", "deploy")


def talonsix_figure() -> Mesh:
	return _soldier("talonsix")


def talonsix_crouch() -> Mesh:
	return _soldier("talonsix", "crouch")


# ---------------------------------------------------------------------------
# Actor registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class State:
	name: str
	layers: tuple[Callable[[], Mesh], ...]
	roll: float = 0.0
	pitch: float = 0.0


@dataclass(frozen=True)
class ActorSpec:
	actor: str
	domain: str  # infantry | vehicle | aircraft | helicopter | ship | structure
	label: str
	frame: tuple[int, int]
	origin: tuple[float, float]
	states: tuple[State, ...]
	facings: int = 32
	px: float = 6.45
	altitude: float = 0.0  # board-only flying height in pixels (engine altitude is compressed)
	projection: tuple[float, float] = (0.57, 0.82)
	shadow: str = "footprint"
	rotor: tuple[float, float, float] | None = None  # (y, z, radius) of a rotor blur disc
	cells: tuple[int, int] | None = None  # building footprint in cells

	def yaws(self) -> tuple[float, ...]:
		"""Eight representative facings in native frame order (N, NW, W, SW, S, SE, E, NE)."""

		if self.facings == 1:
			return (0.0,)
		if self.facings == 32:
			return classic_yaws(4)
		return even_yaws(self.facings, self.facings // 8)


def _vehicle(actor: str, label: str, states: tuple[State, ...], frame: int = 44) -> ActorSpec:
	return ActorSpec(actor, "vehicle", label, (frame, frame), (frame / 2, frame * 0.60), states)


def _infantry(actor: str, label: str, states: tuple[State, ...]) -> ActorSpec:
	return ActorSpec(actor, "infantry", label, (50, 39), (25.0, 26.5), states, facings=8, px=1.0, projection=(0.46, 0.98))


def _aircraft(actor: str, label: str, states: tuple[State, ...], frame: int, facings: int = 16, altitude: float = 14.0, rotor=None) -> ActorSpec:
	domain = "helicopter" if facings == 32 else "aircraft"
	return ActorSpec(actor, domain, label, (frame, frame), (frame / 2, frame * 0.56), states, facings=facings, altitude=altitude, shadow="none", rotor=rotor)


def _ship(actor: str, label: str, states: tuple[State, ...], frame: int) -> ActorSpec:
	return ActorSpec(actor, "ship", label, (frame, frame), (frame / 2, frame * 0.56), states, facings=16, shadow="none")


def _structure(actor: str, label: str, states: tuple[State, ...], cells: tuple[int, int], frame: tuple[int, int], origin: tuple[float, float]) -> ActorSpec:
	return ActorSpec(actor, "structure", label, frame, origin, states, facings=1, projection=(0.75, 0.66), cells=cells)


ACTORS: dict[str, ActorSpec] = {
	"USRIFLE": _infantry("USRIFLE", "Squad Automatic Rifleman", (State("stand", (usrifle_figure,)), State("burst fire", (usrifle_fire,)))),
	"USJAV": _infantry("USJAV", "Javelin team", (State("stand", (usjav_figure,)), State("top-attack launch", (usjav_launch,)))),
	"USJTAC": _infantry("USJTAC", "JTAC", (State("stand", (usjtac_figure,)), State("deployed", (usjtac_deploy,)))),
	"TALONSIX": _infantry("TALONSIX", "Talon Six", (State("stand", (talonsix_figure,)), State("crouch-walk", (talonsix_crouch,)))),
	"USMBT": _vehicle("USMBT", "M1A2 SEP v3", (State("idle", (usmbt_hull, usmbt_turret)),), frame=44),
	"USIFV": _vehicle("USIFV", "M2A4 Bradley", (
		State("idle", (usifv_hull, usifv_turret)),
		State("launcher raised", (usifv_hull, usifv_turret_raised)),
	), frame=44),
	"USICV": _vehicle("USICV", "Stryker ICV", (State("idle", (usicv_hull, usicv_turret)),), frame=44),
	"USHIMARS": _vehicle("USHIMARS", "M142 HIMARS", (
		State("stowed", (ushimars_body, ushimars_pod)),
		State("pod raised", (ushimars_body, ushimars_pod_raised)),
	), frame=48),
	"USSHORAD": _vehicle("USSHORAD", "SGT STOUT", (
		State("mast raised", (usshorad_hull, usshorad_turret)),
		State("mast stowed", (usshorad_hull_stowed, usshorad_turret)),
	), frame=48),
	"USRECOV": _vehicle("USRECOV", "M88 recovery", (
		State("boom stowed", (usrecov_hull,)),
		State("boom working", (usrecov_hull_working,)),
	), frame=48),
	"USF35": _aircraft("USF35", "F-35A", (State("transit", (usf35_airframe,)), State("bay open", (usf35_attack,))), frame=48),
	"USMQ9": _aircraft("USMQ9", "MQ-9 class UAS", (State("transit", (usmq9_airframe,)), State("loiter bank", (usmq9_loiter,), roll=-20)), frame=56),
	"USUH60": _aircraft("USUH60", "UH-60M", (State("flight", (usuh60_airframe, usuh60_rotor)), State("doors open", (usuh60_unload, usuh60_rotor))), frame=56, facings=32, altitude=10.0),
	"USAC130": _aircraft("USAC130", "AC-130J", (State("transit", (usac130_airframe,)), State("left orbit", (usac130_airframe,), roll=-16)), frame=72),
	"USDDG": _ship("USDDG", "DDG 51 Flt III", (State("idle", (usddg_hull, usddg_turret)),), frame=76),
	"USSSN": _ship("USSSN", "Virginia SSN", (State("surfaced", (usssn_hull,)),), frame=70),
	"USLPD": _ship("USLPD", "San Antonio LPD", (State("idle", (uslpd_hull,)), State("ramp lowered", (uslpd_hull_ramp,))), frame=92),
	"USTOC": _structure("USTOC", "Tactical operations center", (State("active", (ustoc_structure,)),), (2, 2), (56, 64), (28.0, 40.0)),
	"USIAMD": _structure("USIAMD", "Integrated air defense", (State("ready", (usiamd_structure,)), State("launcher elevated", (usiamd_firing,))), (2, 2), (56, 64), (28.0, 40.0)),
	"USCUAS": _structure("USCUAS", "Counter-UAS", (State("ready", (uscuas_structure,)),), (1, 1), (28, 40), (14.0, 26.0)),
	"USNODE": _structure("USNODE", "Sensor node", (State("active", (usnode_structure,)),), (1, 1), (28, 48), (14.0, 36.0)),
}

ROSTER = tuple(ACTORS)


def sprite(spec: ActorSpec, state: State, yaw: float, palette: PaletteMap) -> Image.Image:
	"""The indexed frame exactly as a shipping SHP frame would store it."""

	frame = quantize_sprite(render_state(spec, state, yaw), palette)
	if spec.domain == "infantry":
		frame = outline_sprite(frame, palette)
	return frame


def render_state(spec: ActorSpec, state: State, yaw: float) -> Render:
	"""Render one actor state at one yaw: layers composited in draw order."""

	ky, kz = spec.projection
	infantry = spec.domain == "infantry"
	renders = [
		render_mesh(build(), yaw, spec.frame, spec.origin, px=spec.px, ky=ky, kz=kz, pitch=state.pitch, roll=state.roll,
					shadow=spec.shadow if index == 0 else "none", outlines=not infantry,
					shadow_offset=(0.6, 0.4) if infantry else (1.0, 1.5))
		for index, build in enumerate(state.layers)
	]
	result = composite(*renders)
	if spec.rotor is not None:
		ry, rz, radius = spec.rotor
		cx = spec.origin[0] + (-ry * math.sin(math.radians(yaw))) * spec.px
		cy = spec.origin[1] + (ry * math.cos(math.radians(yaw)) * ky - rz * kz) * spec.px
		rx_px, ry_px = radius * spec.px, radius * spec.px * ky
		ImageDraw.Draw(result.shadow).ellipse((cx - rx_px, cy - ry_px, cx + rx_px, cy + ry_px), fill=255)
	return result
