"""Saudi Arabia and Yemen in RA2's native voxel, SHP and cameo formats.

The Red Sea vehicles and aircraft reuse the authored Classic geometry in
``red_sea_directional_vehicle.py``; new RA2 roles (howitzer, IFV, technicals,
ships) are authored here with the same low-poly vocabulary. Infantry and
defenses are articulated meshes rendered from a fixed 2:1 camera, never
rotated bitmaps. No proprietary game art is read.

Native voxels store one normal per voxel, so this module enforces outward
normals at construction time: the shared primitive helpers wind X/Y cylinders
inward, and single-sided wing/fin polygons otherwise light as black surfaces in
real GPU captures (the lesson from the China/Iran/Turkey reviews).
"""
from __future__ import annotations

import contextlib
from dataclasses import replace
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
import struct

from PIL import Image, ImageDraw, ImageFont, ImageOps

import ra2_faction_voxels as vx
import red_sea_directional_vehicle as rs
from red_sea_directional_vehicle import Face, Mesh, _normal

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps/installer/ra2/modern-factions"

# Ownership markers. Sprites remap pure reds; voxels map them to 16..31.
TEAM = (232, 0, 0)
TEAM_DARK = (150, 0, 0)
VOXEL_TEAM = {TEAM: 22, TEAM_DARK: 27}

# Shared material vocabulary. The Red Sea sand/olive set comes from Classic.
SAND, SAND_LIGHT, SAND_DARK = rs.SAND, rs.SAND_LIGHT, rs.SAND_DARK
OLIVE, OLIVE_LIGHT, OLIVE_DARK = rs.OLIVE, rs.OLIVE_LIGHT, rs.OLIVE_DARK
TRACK, RUBBER, STEEL, GRILLE, GLASS, LAMP, METAL = rs.TRACK, rs.RUBBER, rs.STEEL, rs.GRILLE, rs.GLASS, rs.LAMP, rs.METAL
AIRFRAME, AIRFRAME_LIGHT, AIRFRAME_DARK = rs.AIRFRAME, rs.AIRFRAME_LIGHT, rs.AIRFRAME_DARK
NAVAL = (118, 126, 124)
NAVAL_LIGHT = (164, 170, 164)
NAVAL_DARK = (62, 70, 72)
DECK = (86, 92, 88)
WHITE = (220, 222, 210)
CONCRETE = (150, 142, 118)
STONE = (131, 112, 84)
STONE_DARK = (92, 78, 60)
NET = (122, 108, 70)
SKIN = (126, 83, 55)
TEAL = (64, 128, 118)
AMBER = (196, 140, 58)


# Turret pivots are authored at the origin and placed by Turreted.Offset,
# so a rotating turret never orbits the hull center.
TURRET_POSITIONS = {"r2sads": (0, .42), "r2technical": (0, .48), "r2ytechrr": (0, .48), "r2yzu": (0, .48),
                    "r2riyadh": (0, -2.05), "r2sadiq": (0, -1.25), "r2mokha": (0, -1.20)}
ROTOR_ACTORS = ("r2ah64sa",)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _centroid(face):
    return tuple(sum(v[i] for v in face.vertices) / len(face.vertices) for i in range(3))


def _flip(face):
    return replace(face, normal=tuple(-n for n in face.normal))


class RA2Mesh(Mesh):
    """Mesh whose primitives always carry outward normals for VXL lighting."""

    def __init__(self) -> None:
        super().__init__()
        self._depth = 0

    def _primitive(self, method, *args, **kwargs):
        self._depth += 1
        try:
            return method(self, *args, **kwargs)
        finally:
            self._depth -= 1

    def box(self, x0, x1, y0, y1, z0, z1, color, *, outline=True):
        # Reversed bounds would mirror the winding and point every face inward.
        return self._primitive(Mesh.box, min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1),
                               min(z0, z1), max(z0, z1), color, outline=outline)

    def tapered_box(self, *args, **kwargs):
        return self._primitive(Mesh.tapered_box, *args, **kwargs)

    def slanted_box_y(self, x0, x1, y0, y1, z0, z1, height, color):
        """The shared helper assumes y0 < y1; a beam authored toward -Y (the
        nose) mirrors its winding. Real GPU captures showed such barrels and
        launch rails as black: restore outward normals for reversed beams."""
        start = len(self.faces)
        self._primitive(Mesh.slanted_box_y, min(x0, x1), max(x0, x1), y0, y1, z0, z1, height, color)
        if y1 < y0:
            self.faces[start:] = [_flip(face) for face in self.faces[start:]]

    def cylinder_z(self, *args, **kwargs):
        return self._primitive(Mesh.cylinder_z, *args, **kwargs)

    def _cylinder(self, method, axis, center, length, radius, color, segments):
        start = len(self.faces)
        self._primitive(method, center, length, radius, color, segments=segments)
        for i in range(start, len(self.faces)):
            face = self.faces[i]
            offset = [c - o for c, o in zip(_centroid(face), center)]
            radial = list(offset)
            radial[axis] = 0
            if math.hypot(*radial) < radius * .5:
                direction = [0., 0., 0.]
                direction[axis] = offset[axis]
            else:
                direction = radial
            if _dot(face.normal, direction) < 0:
                self.faces[i] = _flip(face)

    def cylinder_x(self, center, length, radius, color, *, segments=10):
        self._cylinder(Mesh.cylinder_x, 0, center, length, radius, color, segments)

    def cylinder_y(self, center, length, radius, color, *, segments=8):
        self._cylinder(Mesh.cylinder_y, 1, center, length, radius, color, segments)

    def polygon(self, vertices, color, *, outline=True):
        if self._depth:
            return super().polygon(vertices, color, outline=outline)
        points = tuple(vertices)
        normal = _normal(points)
        if abs(normal[2]) >= .5:
            # Single-sided plates (wings, stabilizers, decks) face the camera.
            # Keep the authored fan order; only the sampled normal changes.
            face = Face(points, normal, color, outline)
            self.faces.append(face if normal[2] > 0 else _flip(face))
        else:
            self.sheet(points, color, .045, outline=outline)

    def sheet(self, points, color, thickness, *, outline=True):
        """Vertical fins/tails become thin solids with two outward sides."""
        normal = _normal(points)
        half = thickness / 2
        front = [tuple(p[i] + normal[i] * half for i in range(3)) for p in points]
        back = [tuple(p[i] - normal[i] * half for i in range(3)) for p in points]
        self._depth += 1
        try:
            self.polygon(front, color, outline=outline)
            self.polygon(tuple(reversed(back)), color, outline=outline)
            for i in range(len(points)):
                j = (i + 1) % len(points)
                quad = (back[i], back[j], front[j], front[i])
                self.polygon(quad, color, outline=False)
        finally:
            self._depth -= 1
        # Orient every rim quad away from the sheet center.
        center = tuple(sum(p[i] for p in points) / len(points) for i in range(3))
        for k in range(len(self.faces) - len(points), len(self.faces)):
            face = self.faces[k]
            if _dot(face.normal, [c - o for c, o in zip(_centroid(face), center)]) < 0:
                self.faces[k] = _flip(face)
        # Correct the two broad faces explicitly.
        k = len(self.faces) - len(points) - 2
        for index, sign in ((k, 1), (k + 1, -1)):
            face = self.faces[index]
            if _dot(face.normal, normal) * sign < 0:
                self.faces[index] = _flip(face)

    def plate(self, points, color, *, outline=True):
        points = tuple(points)
        face = Face(points, _normal(points), color, outline)
        self.faces.append(face if face.normal[2] >= 0 else _flip(face))

    def loft(self, lower, upper, side, top=None, bottom=None, *, outline=True):
        """Closed hull between two counter-clockwise (from above) rings."""
        self.loft_rings((lower, upper), (side,), top, bottom, outline=outline)

    def loft_rings(self, rings, sides, top=None, bottom=None, *, outline=True):
        """Closed solid through stacked CCW rings; one side color per band."""
        self._depth += 1
        try:
            self.polygon(tuple(reversed(rings[0])), bottom or sides[0], outline=outline)
            for lower, upper, side in zip(rings, rings[1:], sides):
                for i in range(len(lower)):
                    j = (i + 1) % len(lower)
                    self.polygon((lower[i], lower[j], upper[j], upper[i]), side, outline=outline)
            self.polygon(tuple(rings[-1]), top or sides[-1], outline=outline)
        finally:
            self._depth -= 1


@contextlib.contextmanager
def native_meshes():
    """Build shared Classic geometry with RA2's outward-normal primitives."""
    original = rs.Mesh
    rs.Mesh = RA2Mesh
    try:
        yield
    finally:
        rs.Mesh = original


def combine(*meshes):
    result = RA2Mesh()
    result.faces = [face for mesh in meshes for face in mesh.faces]
    return result


def transform(mesh, fn):
    """Apply a point transform, carrying each face's authored outward side."""
    result = RA2Mesh()
    for face in mesh.faces:
        vertices = tuple(fn(*v) for v in face.vertices)
        base = fn(*face.vertices[0])
        tip = fn(*(face.vertices[0][i] + face.normal[i] * .05 for i in range(3)))
        normal = _normal(vertices)
        if _dot(normal, [t - b for t, b in zip(tip, base)]) < 0:
            normal = tuple(-n for n in normal)
        result.faces.append(Face(vertices, normal, face.color, face.outline))
    return result


def shift(mesh, dx=0., dy=0., dz=0.):
    result = RA2Mesh()
    result.faces = [replace(face, vertices=tuple((x + dx, y + dy, z + dz) for x, y, z in face.vertices))
                    for face in mesh.faces]
    return result


def team_band(mesh, x0, x1, y0, y1, z0, z1, color=TEAM):
    mesh.box(x0, x1, y0, y1, z0, z1, color, outline=False)


# ----------------------------------------------------------------------------
# Saudi Arabia: expeditionary combined arms and layered naval defense.
# ----------------------------------------------------------------------------

def m1a2s():
    with native_meshes():
        hull, turret = rs._m1_hull(), rs._m1_turret()
    for side in (-1, 1):
        # Ownership stripe on the segmented skirts; front glacis marker.
        x = side * 1.39
        team_band(hull, min(x, x + side * .03), max(x, x + side * .03), -1.62, 1.30, .76, .90)
        team_band(turret, side * .90 - .03, side * .90 + .03, -.40, .45, 1.40, 1.52)
    team_band(turret, -.45, .45, .20, .70, 1.62, 1.66)
    team_band(hull, -.55, .55, -1.24, -1.10, 1.11, 1.17)
    return hull, turret


def sads():
    with native_meshes():
        hull, turret = rs._sads_hull(), rs._sads_turret()
    for side in (-1, 1):
        team_band(hull, side * .92 - .02, side * .92 + .02, .10, 1.35, .66, .84)
        team_band(turret, side * .62 - .02, side * .62 + .02, .05, .70, .96, 1.12)
    team_band(hull, -.55, .55, -1.46, -1.36, 1.30, 1.36)
    # Pivot the launcher about its own ring; rules place it over the rear deck.
    return hull, shift(turret, dy=-TURRET_POSITIONS["r2sads"][1])


def caesar():
    """Wheeled 155 mm howitzer: fixed rear gun, the chassis turns to fire."""
    mesh = RA2Mesh()
    for y in (-1.30, .55, 1.30):
        mesh.cylinder_x((0, y, .34), 2.18, .34, RUBBER, segments=10)
        mesh.cylinder_x((0, y, .34), 2.26, .14, SAND_DARK, segments=8)
    mesh.box(-.84, .84, -1.80, 1.82, .38, .60, SAND_DARK)
    mesh.tapered_box((-.96, .96, -1.98, -.74, .52), (-.84, .84, -1.82, -.96, 1.34), SAND)
    mesh.box(-.72, .72, -1.90, -1.84, .92, 1.24, GLASS)
    for side in (-1, 1):
        mesh.box(side * .90 - .03, side * .90 + .03, -1.70, -1.18, .92, 1.22, GLASS)
        team_band(mesh, side * .97 - .02, side * .97 + .02, -1.62, -1.02, .62, .86)
    mesh.box(-.94, .94, -.64, 1.84, .58, .82, SAND)
    for side in (-1, 1):
        mesh.box(side * .80 - .12, side * .80 + .12, -.55, .35, .82, 1.02, SAND_DARK)
    mesh.box(-.46, .46, .80, 1.58, .80, 1.26, SAND_DARK)
    for side in (-1, 1):
        mesh.box(side * .42 - .08, side * .42 + .08, .70, 1.30, 1.10, 1.46, STEEL)
    mesh.slanted_box_y(-.10, .10, 1.10, -2.38, 1.20, 1.52, .17, SAND_LIGHT)
    mesh.slanted_box_y(-.16, .16, .80, -.20, 1.14, 1.23, .20, SAND_DARK)
    mesh.box(-.15, .15, -2.60, -2.34, 1.40, 1.66, STEEL)
    mesh.box(-.72, .72, 1.80, 1.96, .18, .72, STEEL)
    team_band(mesh, -.52, .52, -1.70, -1.10, 1.34, 1.38)
    for x in (-.72, .58):
        mesh.box(x, x + .14, -2.00, -1.92, .60, .74, LAMP, outline=False)
    return (mesh,)


def bradley():
    hull = RA2Mesh()
    for x0, x1 in ((-1.24, -.86), (.86, 1.24)):
        hull.box(x0, x1, -1.86, 1.72, .12, .74, TRACK)
    for y in (-1.40, -.78, -.16, .46, 1.08, 1.52):
        hull.cylinder_x((0, y, .38), 2.56, .28, RUBBER, segments=10)
        hull.cylinder_x((0, y, .38), 2.64, .11, SAND_DARK, segments=8)
    hull.tapered_box((-1.00, 1.00, -1.84, 1.70, .54), (-.90, .90, -1.40, 1.64, 1.28), SAND)
    for side in (-1, 1):
        for y0 in (-1.50, -.78, -.06, .66):
            hull.box(side * 1.26 - .06, side * 1.26 + .06, y0, y0 + .66, .50, .96, SAND_LIGHT)
        team_band(hull, side * 1.33 - .02, side * 1.33 + .02, -1.40, 1.20, .70, .84)
    hull.box(-.62, .62, 1.62, 1.74, .52, 1.18, SAND_DARK)
    hull.box(-.55, .55, -1.36, -1.10, 1.26, 1.32, GRILLE)
    for x in (-.70, .56):
        hull.box(x, x + .14, -1.88, -1.78, .70, .84, LAMP, outline=False)
    turret = RA2Mesh()
    turret.cylinder_z((0, 0, 1.33), .12, .48, SAND_DARK, segments=10)
    turret.tapered_box((-.56, .56, -.52, .58, 1.30), (-.46, .46, -.40, .46, 1.70), SAND)
    turret.cylinder_y((.10, -1.12, 1.54), 1.24, .055, STEEL, segments=8)
    turret.cylinder_y((.10, -.52, 1.54), .28, .10, SAND_DARK, segments=8)
    turret.box(-.86, -.54, -.36, .50, 1.40, 1.70, SAND_DARK)
    turret.box(-.84, -.56, -.42, -.36, 1.44, 1.66, GRILLE)
    turret.box(.18, .40, -.38, -.18, 1.70, 1.84, GLASS)
    team_band(turret, -.40, .40, .05, .40, 1.70, 1.74)
    return hull, turret


def f15sa():
    with native_meshes():
        mesh = rs._f15sa_airframe()
    for side in (-1, 1):
        mesh.plate(((side * 1.30, .30, .56), (side * 2.10, .88, .56), (side * 1.86, 1.08, .56),
                    (side * 1.10, .55, .56)), TEAM)
    team_band(mesh, -.10, .10, -2.30, -1.90, .80, .84)
    return (mesh,)


def ah64sa():
    with native_meshes():
        mesh = rs._ah64sa_airframe()
    for side in (-1, 1):
        team_band(mesh, side * .62 - .02, side * .62 + .02, -.95, .10, .55, .90)
    team_band(mesh, -.25, .25, 2.00, 2.60, 1.02, 1.08)
    return mesh, rotor(2.75, SAND_DARK)


def rotor(radius, color):
    mesh = RA2Mesh()
    for angle in (0, 90):
        rad = math.radians(angle)
        c, s = math.cos(rad), math.sin(rad)
        # Chord .16: thin blades vanish between facing samples otherwise.
        corners = ((-radius, -.08), (radius, -.08), (radius, .08), (-radius, .08))
        lower = [(x * c - y * s, x * s + y * c, 1.62) for x, y in corners]
        upper = [(x, y, 1.68) for x, y, _ in lower]
        mesh.loft(lower, upper, color)
    mesh.cylinder_z((0, 0, 1.66), .12, .26, TEAM, segments=10)
    return mesh


def saudi_hull(length, beam, deck, *, bow_rise=.10, color=NAVAL):
    """Convex monohull loft with a raised, flared bow."""
    bow, stern = -length / 2, length / 2
    lower = [(0, bow + .30, 0), (beam * .62, bow + 1.00, 0), (beam * .82, 0, 0), (beam * .78, stern - .30, 0),
             (beam * .55, stern, 0), (-beam * .55, stern, 0), (-beam * .78, stern - .30, 0),
             (-beam * .82, 0, 0), (-beam * .62, bow + 1.00, 0)]
    upper = [(0, bow, deck + bow_rise), (beam * .80, bow + .95, deck + bow_rise * .4), (beam, 0, deck),
             (beam * .98, stern - .30, deck), (beam * .80, stern + .02, deck), (-beam * .80, stern + .02, deck),
             (-beam * .98, stern - .30, deck), (-beam, 0, deck), (-beam * .80, bow + .95, deck + bow_rise * .4)]
    def ring(t):
        return [tuple(a + (b - a) * t for a, b in zip(p, q)) for p, q in zip(lower, upper)]
    # A boot-top ownership band follows the flared hull exactly.
    t0, t1 = (deck - .17) / deck, (deck - .07) / deck
    mesh = RA2Mesh()
    mesh.loft_rings((lower, ring(t0), ring(t1), upper), (color, TEAM, color), DECK, NAVAL_DARK)
    return mesh


def riyadh():
    hull = saudi_hull(6.4, .95, .72)
    hull.tapered_box((-.66, .66, -1.05, 1.15, .72), (-.52, .52, -.86, .98, 1.56), NAVAL_LIGHT)
    hull.box(-.46, .46, -.94, -.86, 1.20, 1.42, GLASS)
    hull.tapered_box((-.20, .20, -.42, .08, 1.56), (-.09, .09, -.30, -.04, 2.56), STEEL)
    hull.box(-.30, .30, -.24, -.16, 2.12, 2.52, NAVAL_DARK)
    hull.box(-.24, .24, -.25, -.23, 2.18, 2.46, GLASS, outline=False)
    hull.tapered_box((-.24, .24, .42, .86, 1.56), (-.18, .18, .50, .78, 1.92), NAVAL_DARK)
    team_band(hull, -.19, .19, .49, .79, 1.80, 1.86)
    hull.box(-.58, .58, 1.15, 2.05, .72, 1.28, NAVAL_LIGHT)
    hull.cylinder_z((0, 1.72, 1.46), .30, .19, WHITE, segments=10)
    hull.cylinder_y((0, 1.46, 1.46), .28, .04, STEEL, segments=6)
    for y in (-1.70, -1.50, -1.30):
        for x in (-.26, 0, .26):
            hull.box(x - .09, x + .09, y - .08, y + .08, .72, .78, GRILLE, outline=False)
    hull.plate(((-.60, 2.18, .76), (.60, 2.18, .76), (.60, 3.05, .76), (-.60, 3.05, .76)), NAVAL_DARK)
    hull.box(-.34, .34, 2.52, 2.60, .76, .79, WHITE, outline=False)
    return hull, naval_gun(.30, .78)


def naval_gun(radius, barrel):
    """Pivot at the origin; rules place it with Turreted.Offset."""
    mesh = RA2Mesh()
    mesh.cylinder_z((0, 0, .80), .14, radius, NAVAL_DARK, segments=10)
    mesh.tapered_box((-radius, radius, -.28, .30, .82), (-radius * .66, radius * .66, -.20, .22, 1.14), NAVAL_LIGHT)
    mesh.cylinder_y((0, -.28 - barrel / 2, 1.00), barrel, .05, STEEL, segments=8)
    team_band(mesh, -radius * .5, radius * .5, -.05, .18, 1.14, 1.17)
    return mesh


def sadiq():
    hull = saudi_hull(4.2, .62, .60, bow_rise=.14)
    hull.tapered_box((-.42, .42, -.35, .75, .60), (-.32, .32, -.22, .62, 1.12), NAVAL_LIGHT)
    hull.box(-.30, .30, -.30, -.22, .86, 1.04, GLASS)
    hull.box(-.07, .07, .30, .40, 1.12, 1.62, STEEL)
    hull.box(-.20, .20, .32, .38, 1.46, 1.56, NAVAL_DARK)
    for side in (-1, 1):
        hull.box(side * .45 - .08, side * .45 + .08, 1.35, 1.95, .60, .74, NAVAL_DARK)
    return hull, naval_gun(.20, .56)


def jubail():
    hull = saudi_hull(6.9, 1.10, .74, bow_rise=.06)
    hull.tapered_box((-.82, .82, -2.55, -1.30, .74), (-.70, .70, -2.40, -1.42, 1.78), NAVAL_LIGHT)
    hull.box(-.62, .62, -2.46, -2.40, 1.38, 1.62, GLASS)
    hull.box(-.10, .10, -1.95, -1.80, 1.78, 2.55, STEEL)
    hull.box(-.34, .34, -1.93, -1.86, 2.28, 2.48, NAVAL_DARK)
    team_band(hull, -.71, .71, -2.38, -1.44, 1.78, 1.84)
    for y in (-.70, .50):
        hull.box(-.10, .10, y - .10, y + .10, .74, 2.05, NAVAL_DARK)
        hull.box(-.95, .95, y - .06, y + .06, 1.92, 2.04, NAVAL_DARK)
        for x in (-.85, .85):
            hull.box(x - .04, x + .04, y - .04, y + .04, 1.30, 1.92, STEEL)
    hull.box(-.62, .62, -.20, 1.95, .74, 1.12, SAND)
    hull.box(-.55, .55, -.10, 1.85, 1.12, 1.18, SAND_DARK)
    hull.slanted_box_y(.28, .40, 2.00, 2.90, 1.00, 1.86, .10, AMBER)
    hull.box(.20, .48, 1.90, 2.10, .74, 1.10, NAVAL_DARK)
    hull.plate(((-.80, 2.30, .78), (.10, 2.30, .78), (.10, 3.30, .78), (-.80, 3.30, .78)), DECK)
    return (hull,)


def saudi_fortification(actor, turret=False):
    mesh = RA2Mesh()
    if not turret:
        mesh.tapered_box((-1.12, 1.12, -1.12, 1.12, 0), (-.94, .94, -.94, .94, .30), CONCRETE)
        if actor == "r2saguard":
            mesh.box(-.70, .70, -.70, .70, .30, .92, SAND)
            for side in (-1, 1):
                mesh.box(side * .70 - .04, side * .70 + .04, -.72, .72, .92, 1.00, SAND_DARK)
                mesh.box(-.72, .72, side * .70 - .04, side * .70 + .04, .92, 1.00, SAND_DARK)
            mesh.box(-.32, .32, -.74, -.70, .52, .66, GRILLE)
        elif actor == "r2sapatriot":
            mesh.box(-.84, .84, -.60, .84, .30, .52, SAND_DARK)
            mesh.box(.40, .88, -.92, -.40, .30, .88, SAND)
            mesh.box(.44, .84, -.94, -.92, .52, .74, GLASS)
        else:
            mesh.tapered_box((-.84, .84, -.84, .84, .30), (-.62, .62, -.62, .62, .74), SAND)
            mesh.box(-.52, .52, -.64, -.60, .44, .58, GRILLE)
        mesh.box(-.94, -.84, -.86, .86, .31, .44, TEAM)
        mesh.box(.84, .94, -.86, .86, .31, .44, TEAM)
        return mesh
    mesh.cylinder_z((0, 0, .98 if actor != "r2sapatriot" else .64), .16, .42, STEEL, segments=12)
    if actor == "r2saguard":
        mesh.tapered_box((-.42, .42, -.38, .44, 1.00), (-.34, .34, -.30, .36, 1.34), SAND_LIGHT)
        for x in (-.15, .15):
            mesh.cylinder_y((x, -.78, 1.18), .80, .045, STEEL, segments=8)
        mesh.box(-.36, .36, -.46, -.38, 1.02, 1.30, SAND_DARK)
        mesh.box(.18, .32, -.30, -.12, 1.34, 1.46, GLASS)
        team_band(mesh, -.22, .22, .00, .30, 1.34, 1.38)
    elif actor == "r2sapatriot":
        mesh.box(-.62, .62, -.40, .66, .66, .92, SAND_DARK)
        for x in (-.44, -.15, .15, .44):
            mesh.slanted_box_y(x - .13, x + .13, .60, -.85, .92, 1.62, .24, SAND_LIGHT)
            mesh.box(x - .10, x + .10, -.95, -.86, 1.62, 1.84, GRILLE)
        team_band(mesh, -.60, .60, .54, .66, .70, .86)
    else:
        mesh.box(-.26, .26, -.30, .36, 1.00, 1.26, SAND_DARK)
        mesh.cylinder_y((-.12, -.42, 1.40), 1.10, .12, SAND_LIGHT, segments=10)
        mesh.cylinder_y((-.12, -.99, 1.40), .06, .14, GRILLE, segments=10)
        mesh.box(.18, .42, -.34, .02, 1.28, 1.52, GLASS)
        team_band(mesh, -.24, .24, .05, .34, 1.26, 1.30)
    return mesh


# ----------------------------------------------------------------------------
# Yemen: light, dispersed and concealed; coastal forces and one-way drones.
# ----------------------------------------------------------------------------

def technical_hull():
    with native_meshes():
        hull = rs._tech_hull()
    for side in (-1, 1):
        team_band(hull, side * .67 - .02, side * .67 + .02, -1.20, -.62, .52, .68)
    team_band(hull, -.50, .50, -1.22, -.66, .70, .72)
    return hull


def technical():
    with native_meshes():
        turret = rs._tech_turret()
    turret = shift(turret, dy=-TURRET_POSITIONS["r2technical"][1])
    team_band(turret, -.26, .26, -.20, .10, 1.41, 1.44)
    return technical_hull(), turret


def recoilless():
    turret = RA2Mesh()
    turret.cylinder_z((0, 0, .84), .12, .30, OLIVE_DARK, segments=10)
    turret.cylinder_z((0, 0, 1.08), .36, .08, METAL, segments=8)
    turret.cylinder_y((0, -.40, 1.32), 2.10, .085, OLIVE, segments=10)
    turret.cylinder_y((0, .78, 1.32), .30, .13, METAL, segments=10)
    turret.cylinder_y((0, -1.47, 1.32), .12, .11, GRILLE, segments=10)
    turret.box(.10, .26, -.40, -.10, 1.40, 1.54, GLASS)
    turret.box(-.22, .22, .10, .40, 1.06, 1.20, OLIVE_LIGHT)
    team_band(turret, -.20, .20, .12, .38, 1.20, 1.23)
    return technical_hull(), turret


def zu23():
    turret = RA2Mesh()
    turret.cylinder_z((0, 0, .84), .12, .40, OLIVE_DARK, segments=10)
    turret.box(-.40, .40, -.26, .34, .90, 1.10, OLIVE)
    turret.box(-.36, .36, -.34, -.28, 1.00, 1.38, OLIVE_LIGHT)
    for x in (-.16, .16):
        turret.slanted_box_y(x - .045, x + .045, -.25, -1.45, 1.20, 1.62, .07, STEEL)
        turret.box(x - .07, x + .07, -1.52, -1.42, 1.58, 1.72, GRILLE)
    turret.box(-.12, .12, .06, .30, 1.10, 1.34, OLIVE_DARK)
    team_band(turret, -.38, .38, -.33, -.29, 1.28, 1.36)
    return technical_hull(), turret


def ymlr(loaded):
    """Classic 6x6 launcher truck with an RA2 erector: nose high over the cab.

    The Classic sprite rack rises toward the rear. RA2 fires this launcher
    forward from a turning chassis, so the erector pivots at the rear and the
    loaded missile's nose points up over the cab. The empty rack is the visible
    reload state, as in Classic.
    """
    mesh = RA2Mesh()
    for y in (-1.44, .18, 1.35):
        mesh.cylinder_x((0, y, .34), 2.18, .32, RUBBER, segments=10)
        mesh.cylinder_x((0, y, .34), 2.26, .14, OLIVE_DARK, segments=8)
    mesh.box(-.86, .86, -1.69, 1.68, .39, .62, OLIVE_DARK)
    mesh.tapered_box((-.84, .84, -1.61, -.37, .56), (-.72, .72, -1.43, -.49, 1.24), OLIVE)
    mesh.box(-.58, .58, -1.66, -1.60, .84, 1.12, GLASS)
    for side in (-1, 1):
        mesh.box(side * .74 - .03, side * .74 + .03, -1.30, -.80, .82, 1.10, GLASS)
        team_band(mesh, side * .85 - .02, side * .85 + .02, -1.45, -.55, .60, .80)
    mesh.box(-.80, .80, -.29, 1.62, .58, .81, OLIVE)
    mesh.box(-.60, .60, 1.30, 1.64, .81, 1.02, OLIVE_DARK)
    for side in (-1, 1):
        mesh.slanted_box_y(side * .43 - .06, side * .43 + .06, 1.52, -.20, .82, 1.30, .12, STEEL)
    mesh.slanted_box_y(-.38, .38, 1.10, .95, .84, .96, .10, METAL)
    team_band(mesh, -.62, .62, .10, 1.10, .81, .84)
    if loaded:
        mesh.slanted_box_y(-.21, .21, 1.56, -.55, 1.02, 1.62, .36, OLIVE_LIGHT)
        mesh.slanted_box_y(-.13, .13, -.55, -.95, 1.66, 1.76, .22, (168, 58, 38))
        mesh.box(-.26, .26, 1.52, 1.64, .96, 1.34, GRILLE)
        for side in (-1, 1):
            mesh.slanted_box_y(side * .22 - .03, side * .22 + .03, 1.40, 1.05, 1.06, 1.18, .30, OLIVE_DARK)
    for x in (-.66, .52):
        mesh.box(x, x + .14, -1.70, -1.60, .57, .70, LAMP, outline=False)
    return (mesh,)


def samad():
    with native_meshes():
        mesh = rs._samad_airframe()
    for side in (-1, 1):
        mesh.plate(((side * .90, -.20, .36), (side * 1.50, -.20, .36), (side * 1.22, .24, .36),
                    (side * .80, .24, .36)), TEAM)
    return (mesh,)


def yemen_hull(length, beam, deck, color=OLIVE_DARK):
    mesh = saudi_hull(length, beam, deck, bow_rise=.12, color=color)
    return mesh


def hodeidah():
    hull = yemen_hull(4.6, .70, .60, (96, 104, 96))
    hull.tapered_box((-.48, .48, -.40, .80, .60), (-.36, .36, -.28, .66, 1.18), (140, 144, 132))
    hull.box(-.34, .34, -.36, -.28, .90, 1.08, GLASS)
    hull.box(-.07, .07, .26, .36, 1.18, 1.70, STEEL)
    for side in (-1, 1):
        # Fixed forward launchers: the hull turns to fire.
        for x in (.22, .46):
            hull.slanted_box_y(side * x - .10, side * x + .10, 1.80, .95, .62, .82, .20, (140, 144, 132))
            hull.box(side * x - .08, side * x + .08, .88, .96, .78, .96, GRILLE)
    team_band(hull, -.37, .37, -.26, .64, 1.18, 1.22)
    return (hull,)


def sahaab():
    hull = yemen_hull(3.0, .44, .40, (74, 80, 74))
    hull.tapered_box((-.24, .24, .00, .70, .40), (-.16, .16, .10, .56, .66), (74, 80, 74))
    hull.cylinder_z((0, .30, .76), .18, .12, WHITE, segments=10)
    hull.box(-.20, .20, -1.20, -.70, .40, .48, AMBER)
    team_band(hull, -.12, .12, .15, .50, .66, .69)
    return (hull,)


def mokha():
    hull = yemen_hull(4.3, .70, .60, (104, 112, 104))
    hull.tapered_box((-.50, .50, -.50, .95, .60), (-.40, .40, -.36, .82, 1.24), (150, 154, 142))
    hull.box(-.36, .36, -.46, -.36, .96, 1.14, GLASS)
    hull.box(-.07, .07, .20, .34, 1.24, 2.20, STEEL)
    hull.box(-.40, .40, .22, .32, 1.86, 2.18, NAVAL_DARK)
    hull.box(-.34, .34, .21, .23, 1.90, 2.14, TEAL, outline=False)
    hull.cylinder_z((0, .90, 1.34), .20, .14, WHITE, segments=10)
    team_band(hull, -.41, .41, -.30, .80, 1.24, 1.28)
    return hull, naval_gun(.18, .46)


def yemen_fortification(actor, turret=False):
    mesh = RA2Mesh()
    if not turret:
        if actor == "r2ybunker":
            mesh.tapered_box((-1.12, 1.12, -1.12, 1.12, 0), (-.92, .92, -.92, .92, .24), STONE_DARK)
            # Dry-stone courses, stepped inward, with a firing slit at the front.
            for z, w in ((.24, .96), (.46, .86)):
                mesh.box(-w, -w + .16, -w, w, z, z + .22, STONE)
                mesh.box(w - .16, w, -w, w, z, z + .22, STONE)
                mesh.box(-w, w, w - .16, w, z, z + .22, STONE)
                mesh.box(-w, -.24, -w, -w + .16, z, z + .22, STONE)
                mesh.box(.24, w, -w, -w + .16, z, z + .22, STONE)
            mesh.box(-.24, .24, -.95, -.80, .24, .40, STONE)
            mesh.box(-.24, .24, -.84, -.80, .40, .60, GRILLE)
            mesh.box(-.70, .70, -.70, .70, .24, .64, STONE_DARK)
            mesh.plate(((-.95, -.95, .70), (.95, -.95, .70), (.95, .95, .70), (-.95, .95, .70)), NET)
        elif actor == "r2yzunest":
            mesh.tapered_box((-1.10, 1.10, -1.10, 1.10, 0), (-.94, .94, -.94, .94, .20), STONE_DARK)
            for i in range(10):
                a = i * math.tau / 10
                mesh.box(math.cos(a) * .78 - .16, math.cos(a) * .78 + .16, math.sin(a) * .78 - .16,
                         math.sin(a) * .78 + .16, .20, .48, NET)
        else:
            mesh.tapered_box((-1.12, 1.12, -1.12, 1.12, 0), (-.96, .96, -.96, .96, .22), STONE_DARK)
            mesh.box(-.84, .84, -.30, .90, .22, .52, OLIVE_DARK)
            mesh.plate(((-1.0, -.10, .56), (1.0, -.10, .56), (1.0, 1.0, .56), (-1.0, 1.0, .56)), NET)
        mesh.box(-.93, -.83, -.80, .80, .21, .33, TEAM)
        mesh.box(.83, .93, -.80, .80, .21, .33, TEAM)
        return mesh
    if actor == "r2ybunker":
        mesh.cylinder_z((0, 0, .72), .14, .32, METAL, segments=10)
        mesh.box(-.30, .30, -.26, .34, .78, .96, OLIVE)
        mesh.cylinder_y((0, -.68, .90), .82, .05, STEEL, segments=8)
        mesh.box(-.26, .26, -.34, -.28, .80, 1.06, OLIVE_DARK)
        team_band(mesh, -.20, .20, .04, .30, .96, .99)
    elif actor == "r2yzunest":
        mesh.cylinder_z((0, 0, .56), .12, .42, METAL, segments=10)
        mesh.box(-.44, .44, -.26, .36, .62, .84, OLIVE)
        mesh.box(-.40, .40, -.34, -.28, .74, 1.12, OLIVE_LIGHT)
        for x in (-.18, .18):
            mesh.slanted_box_y(x - .05, x + .05, -.25, -1.35, .96, 1.46, .08, STEEL)
            mesh.box(x - .07, x + .07, -1.44, -1.32, 1.40, 1.56, GRILLE)
        team_band(mesh, -.42, .42, -.33, -.29, 1.02, 1.10)
    else:
        mesh.cylinder_z((0, 0, .62), .14, .34, METAL, segments=10)
        mesh.box(-.52, .52, -.30, .50, .66, .86, OLIVE_DARK)
        for x in (-.26, .26):
            mesh.slanted_box_y(x - .20, x + .20, .60, -1.10, .86, 1.34, .30, OLIVE)
            mesh.box(x - .16, x + .16, -1.18, -1.08, 1.30, 1.58, GRILLE)
        team_band(mesh, -.50, .50, .40, .50, .70, .84)
    return mesh


# ----------------------------------------------------------------------------
# Articulated infantry. Roles follow docs/custom-infantry-identities.md.
# ----------------------------------------------------------------------------

UNIFORMS = {
    # cloth, dark cloth, gear/armor, accent, headwrap
    "r2sang": ((166, 142, 91), (82, 76, 53), (105, 100, 63), (203, 179, 105), None),
    "r2saat": ((153, 130, 82), (73, 68, 48), (92, 90, 58), (176, 143, 52), None),
    "r2sajtac": ((176, 151, 100), (83, 75, 52), (101, 96, 62), TEAL, None),
    "r2falcon": ((70, 67, 58), (34, 36, 34), (70, 66, 52), (81, 132, 116), None),
    "r2ymr": ((116, 100, 73), (62, 55, 43), (92, 80, 57), (161, 124, 66), (161, 124, 66)),
    "r2yrpg": ((113, 98, 67), (57, 53, 39), (85, 75, 51), (150, 105, 51), (150, 105, 51)),
    "r2yspot": ((96, 90, 70), (49, 50, 42), (79, 77, 57), TEAL, (132, 122, 92)),
    "r2wadighost": ((62, 58, 50), (30, 31, 29), (65, 58, 49), AMBER, (30, 31, 29)),
}


def soldier(actor, phase=0., action="stand"):
    cloth, dark, gear, accent, wrap = UNIFORMS[actor]
    saudi = actor in SAUDI_INFANTRY
    mesh = RA2Mesh()
    bulk = {"r2sang": 1.10, "r2saat": 1.08, "r2ymr": .94}.get(actor, 1.0)
    swing = math.sin(phase * math.tau) * .25 if action == "run" else 0
    for side in (-1, 1):
        x, y = side * .16, side * swing
        mesh.slanted_box_y(x - .08, x + .08, -.03, y + .05, .62, .13, .14, dark)
        mesh.box(x - .09, x + .09, y - .17, y + .08, .02, .14, RUBBER)
    w = .27 * bulk
    mesh.tapered_box((-.22 * bulk, .22 * bulk, -.14, .17, .57), (-w, w, -.15, .15, 1.14), cloth)
    mesh.box(-.20, .20, -.21, -.14, .66, 1.06, gear)
    mesh.cylinder_z((0, 0, 1.27), .26, .155, SKIN, segments=8)
    for side in (-1, 1):
        mesh.slanted_box_y(side * .28 - .05, side * .28 + .05, -.04, -.42, .96, .85, .10, cloth)
        # Shoulder ownership patches visible from every facing.
        mesh.box(side * (w + .02) - .06, side * (w + .02) + .06, -.11, .11, .96, 1.08, TEAM)
    recoil = .04 * math.sin(phase * math.pi) if action == "shoot" else 0
    if saudi:
        # Helmets: heavy for the Guard, optic helmet for ATGM, cap for Falcon.
        if actor == "r2falcon":
            mesh.cylinder_z((0, .01, 1.40), .10, .165, dark, segments=10)
            mesh.box(-.17, .17, -.26, -.12, 1.38, 1.42, dark)
        else:
            radius = .215 if actor == "r2sang" else .20
            mesh.cylinder_z((0, .01, 1.42), .17, radius, gear, segments=10)
            mesh.box(-radius, radius, -.19, -.14, 1.34, 1.40, dark)
        mesh.box(-.16, .16, .16, .34, .66, 1.08, gear)
    else:
        # Headwraps with a trailing tail, scarves across the lower face.
        mesh.cylinder_z((0, .01, 1.42), .16, .175, wrap, segments=10)
        mesh.slanted_box_y(-.06, .06, .10, .30, 1.44, 1.10, .08, wrap)
        mesh.box(-.15, .15, -.16, -.13, 1.18, 1.27, accent)
        mesh.box(-.20, .20, .15, .30, .70, 1.00, gear)
    if actor == "r2wadighost":
        mesh.tapered_box((-.24, .24, -.14, .24, 1.26), (-.12, .12, -.02, .16, 1.62), dark)
    # Weapons by role.
    if actor in ("r2saat",):
        mesh.cylinder_y((.24, -.35 + recoil, 1.12), 1.40, .14, OLIVE_DARK, segments=10)
        mesh.cylinder_y((.24, -1.06 + recoil, 1.12), .08, .17, METAL, segments=10)
        mesh.box(.36, .52, -.54, -.30, 1.10, 1.30, GLASS)
        for side in (-1, 1):
            mesh.slanted_box_y(side * .30 - .03, side * .30 + .03, .10, .40, .70, .05, .05, METAL)
    elif actor == "r2yrpg":
        mesh.cylinder_y((.22, -.30 + recoil, 1.10), 1.10, .07, OLIVE_DARK, segments=8)
        mesh.tapered_box((.14, .30, -1.05, -.85, 1.02), (.20, .24, -1.25, -1.20, 1.10), OLIVE_LIGHT)
        for x in (-.12, .04, .20):
            mesh.cylinder_z((x, .30, 1.10), .44, .05, OLIVE_LIGHT, segments=6)
    elif actor in ("r2falcon", "r2wadighost"):
        length = 1.00 if actor == "r2falcon" else .70
        mesh.box(-.06, .06, -.28 - length + recoil, -.28 + recoil, .88, .96, METAL)
        mesh.cylinder_y((0, -.40 - length + recoil, .92), .30, .06, GRILLE, segments=8)
        if actor == "r2falcon":
            mesh.box(-.05, .05, -.70, -.46, .96, 1.04, GLASS)
        mesh.box(-.30, -.14, -.05, .20, .70, .92, accent)
    else:
        mesh.box(-.06, .06, -.92 + recoil, -.26 + recoil, .86, .95, METAL)
        mesh.box(-.07, .07, -.40, -.26, .76, .89, (98, 72, 48) if not saudi else gear)
    if actor == "r2sajtac":
        mesh.box(-.25, .25, .16, .44, .72, 1.20, dark)
        mesh.cylinder_z((.18, .30, 1.56), .80, .022, METAL, segments=6)
        mesh.box(.16, .34, -.62, -.34, 1.02, 1.18, (40, 44, 42))
        mesh.box(.20, .30, -.64, -.62, 1.06, 1.14, TEAM_DARK)
    elif actor == "r2yspot":
        mesh.box(-.22, .22, .16, .36, .72, 1.12, dark)
        for x in (-.14, .14):
            mesh.cylinder_z((x, .28, 1.50), .84, .02, METAL, segments=6)
        mesh.box(-.20, .20, -.52, -.40, .86, 1.04, (33, 39, 38))
        mesh.box(-.16, .16, -.53, -.52, .90, 1.00, accent, outline=False)
    elif actor == "r2sang":
        for x in (-.18, .02):
            mesh.box(x, x + .13, -.25, -.19, .72, .88, accent)
    elif actor == "r2ymr":
        mesh.box(.18, .34, -.06, .22, .66, .88, gear)
    if action == "die":
        angle = phase * math.pi / 2
        mesh = transform(mesh, lambda x, y, z: (x, y * math.cos(angle) + z * math.sin(angle),
                                                max(.025, z * math.cos(angle) - y * math.sin(angle))))
    return mesh


# ----------------------------------------------------------------------------
# Rosters.
# ----------------------------------------------------------------------------

SAUDI_INFANTRY = ("r2sang", "r2saat", "r2sajtac", "r2falcon")
SAUDI_DEFENSES = ("r2saguard", "r2sapatriot", "r2satow")
SAUDI_UNITS = SAUDI_INFANTRY + ("r2m1a2s", "r2sads", "r2caesar", "r2bradley", "r2f15sa", "r2ah64sa",
                                "r2sadiq", "r2riyadh", "r2jubail")
YEMEN_INFANTRY = ("r2ymr", "r2yrpg", "r2yspot", "r2wadighost")
YEMEN_DEFENSES = ("r2ybunker", "r2yzunest", "r2ycoastal")
YEMEN_UNITS = YEMEN_INFANTRY + ("r2technical", "r2ytechrr", "r2yzu", "r2ymlr", "r2samad", "r2hodeidah",
                                "r2sahaab", "r2mokha")
LABELS = dict(zip(SAUDI_UNITS + SAUDI_DEFENSES, (
    "NATIONAL GUARD", "ATGM TEAM", "JTAC", "FALCON ONE", "M1A2S", "SADS", "CAESAR", "BRADLEY", "F-15SA",
    "AH-64E", "AL SADIQ", "AL RIYADH", "AL JUBAIL", "GUARD TOWER", "PATRIOT", "TOW POST")))
LABELS.update(zip(YEMEN_UNITS + YEMEN_DEFENSES, (
    "MOUNTAIN RIFLE", "RPG HUNTER", "SPOTTER", "WADI GHOST", "TECHNICAL", "RECOILLESS", "ZU-23",
    "MISSILE TRUCK", "SAMAD", "HODEIDAH", "SAHAAB USV", "MOKHA", "BUNKER", "ZU-23 NEST", "COAST BATTERY")))

FACTIONS = {
    "saudi": {
        "folder": "saudi-art", "infantry": SAUDI_INFANTRY, "defenses": SAUDI_DEFENSES, "units": SAUDI_UNITS,
        "fortification": saudi_fortification, "title": "SAUDI ARABIA / EXPEDITIONARY ARMS",
        "footer": "13 UNITS + 3 DEFENSES / SHARED ALLIED ECONOMY", "background": (26, 26, 20),
        "gradient": (24, 26, 18), "text": (236, 228, 204), "materials": (
            (166, 142, 91), (82, 76, 53), (105, 100, 63), (203, 179, 105), (176, 151, 100), (70, 67, 58),
            SKIN, METAL, RUBBER, (40, 44, 42), TEAL, CONCRETE, SAND, OLIVE_DARK),
    },
    "yemen": {
        "folder": "yemen-art", "infantry": YEMEN_INFANTRY, "defenses": YEMEN_DEFENSES, "units": YEMEN_UNITS,
        "fortification": yemen_fortification, "title": "YEMEN / DISPERSED COASTAL DEFENSE",
        "footer": "12 UNITS + 3 DEFENSES / SHARED SOVIET ECONOMY", "background": (27, 24, 19),
        "gradient": (26, 22, 16), "text": (234, 222, 196), "materials": (
            (116, 100, 73), (62, 55, 43), (92, 80, 57), (161, 124, 66), (150, 105, 51), (62, 58, 50),
            SKIN, METAL, RUBBER, (33, 39, 38), TEAL, STONE, NET, OLIVE),
    },
}


def models():
    """Actor -> voxel parts. ``r2ymlrempty`` is the reloading-state body."""
    return {
        "r2m1a2s": m1a2s(), "r2sads": sads(), "r2caesar": caesar(), "r2bradley": bradley(),
        "r2f15sa": f15sa(), "r2ah64sa": ah64sa(), "r2sadiq": sadiq(), "r2riyadh": riyadh(), "r2jubail": jubail(),
        "r2technical": technical(), "r2ytechrr": recoilless(), "r2yzu": zu23(), "r2ymlr": ymlr(True),
        "r2ymlrempty": ymlr(False), "r2samad": samad(), "r2hodeidah": hodeidah(), "r2sahaab": sahaab(),
        "r2mokha": mokha(),
    }


def country_of(actor):
    return "saudi" if actor in SAUDI_UNITS + ("r2f15strike",) else "yemen"


ROTORS = ("r2ah64satur",)
SHIPS = ("r2sadiq", "r2riyadh", "r2jubail", "r2hodeidah", "r2sahaab", "r2mokha")
SHIP_SCALE, VEHICLE_SCALE = 22, 15.2


def world_units(mesh_units, scale=VEHICLE_SCALE):
    """Authored mesh units -> WDist at a RenderVoxels scale (see module doc)."""
    # One voxel is Scale/12 pixels; a 60px isometric tile spans 1448 units.
    return round(mesh_units * 10 * scale / 12 * 1448 / 60)


def turret_offsets():
    """Turreted.Offset (forward WDist) for turrets pivoting off-center."""
    return {actor: world_units(-y, SHIP_SCALE if actor in SHIPS else VEHICLE_SCALE)
            for actor, (_, y) in TURRET_POSITIONS.items()}


def assembled(actor, parts):
    """Hull plus turret at its authored deck position (portraits, reviews)."""
    if len(parts) == 2 and actor in TURRET_POSITIONS and actor not in ROTOR_ACTORS:
        x, y = TURRET_POSITIONS[actor]
        return combine(parts[0], shift(parts[1], dx=x, dy=y))
    return combine(*parts)


# ----------------------------------------------------------------------------
# Native voxel export (per-country palettes keep existing packs byte-identical).
# ----------------------------------------------------------------------------

def voxel_palette(meshes):
    colors = sorted({face.color for parts in meshes.values() for mesh in parts for face in mesh.faces}
                    - VOXEL_TEAM.keys())
    if len(colors) > 224:
        raise ValueError("Material palette exceeds the non-remap slots")
    result = [(0, 0, 0)] * 256
    for i in range(16):
        result[16 + i] = (max(24, 252 - 14 * i), 0, 0)
    indexes = {color: i + 32 for i, color in enumerate(colors)}
    indexes.update(VOXEL_TEAM)
    for color in colors:
        # RA2 relights voxels dynamically, so authored materials are stored
        # lighter, as in the other modern packs. Desert sand is already light:
        # damp its saturation so it reads as painted armor, not yellow plastic.
        gray = sum(color) / 3
        muted = tuple(gray + (channel - gray) * .72 for channel in color)
        result[indexes[color]] = tuple(min(236, round(channel * 1.12 + 8)) for channel in muted)
    return bytes(channel // 4 for color in result for channel in color), indexes


def voxelize(mesh, colors, normals):
    points = [vx.coordinates(vertex) for face in mesh.faces for vertex in face.vertices]
    lower = tuple(math.floor(min(p[i] for p in points) * vx.VOXELS_PER_UNIT) - 1 for i in range(3))
    upper = tuple(math.ceil(max(p[i] for p in points) * vx.VOXELS_PER_UNIT) + 1 for i in range(3))
    size = tuple(upper[i] - lower[i] + 1 for i in range(3))
    if max(size) > 255:
        raise ValueError("VXL dimensions exceed the byte-sized native grid")
    voxels = {}
    for face in mesh.faces:
        normal = vx.coordinates(face.normal)
        normal_index = max(range(len(normals)), key=lambda i: _dot(normals[i], normal))
        vertices = [tuple(p * vx.VOXELS_PER_UNIT for p in vx.coordinates(v)) for v in face.vertices]
        index = colors[face.color]
        a = vertices[0]
        for b, c in zip(vertices[1:-1], vertices[2:]):
            steps = max(1, math.ceil(max(math.dist(a, b), math.dist(a, c), math.dist(b, c)) * 2))
            for j in range(steps + 1):
                for k in range(steps - j + 1):
                    p = tuple(a[d] + (b[d] - a[d]) * j / steps + (c[d] - a[d]) * k / steps for d in range(3))
                    voxels[tuple(math.floor(p[d] + .5) - lower[d] for d in range(3))] = (index, normal_index)
    return size, lower, voxels


def export_voxels(output=OUTPUT):
    all_models = models()
    normals = vx.normal_table()
    destination = output / "voxels"
    destination.mkdir(parents=True, exist_ok=True)
    report = {"format": "VXL/HVA", "normals": "RedAlert2", "remap_indices": list(range(16, 32)),
              "geometry_sources": ["scripts/red_sea_directional_vehicle.py", "scripts/ra2_red_sea_assets.py"],
              "palettes": {}, "models": {}}
    for country in FACTIONS:
        meshes = {actor: parts for actor, parts in all_models.items() if country_of(actor.removesuffix("empty")) == country}
        pal, colors = voxel_palette(meshes)
        palette_name = country + "-art/" + country + "-voxels.pal"
        (output / (country + "-art")).mkdir(parents=True, exist_ok=True)
        (output / palette_name).write_bytes(pal)
        report["palettes"][country] = {"file": palette_name, "sha256": hashlib.sha256(pal).hexdigest()}
        for actor, parts in meshes.items():
            for part, mesh in enumerate(parts):
                name = actor + ("tur" if part else "")
                size, lower, voxels = voxelize(mesh, colors, normals)
                data = vx.encode_vxl(size, lower, voxels, pal)
                (destination / (name + ".vxl")).write_bytes(data)
                matrices = [vx.IDENTITY]
                if name in ROTORS:
                    matrices = []
                    for i in range(8):
                        a = i * math.pi / 16
                        c, s = math.cos(a), math.sin(a)
                        matrices.append((c, -s, 0., 0., s, c, 0., 0., 0., 0., 1., 0.))
                hva = bytes(16) + struct.pack("<2I", len(matrices), 1) + b"body".ljust(16, b"\0")
                hva += b"".join(struct.pack("<12f", *matrix) for matrix in matrices)
                (destination / (name + ".hva")).write_bytes(hva)
                report["models"][name] = {
                    "country": country, "size": size, "origin": lower, "occupied_voxels": len(voxels),
                    "remap_voxels": sum(16 <= value[0] <= 31 for value in voxels.values()),
                    "animation_frames": len(matrices), "sha256": hashlib.sha256(data).hexdigest()}
                print(name, size, len(voxels), flush=True)
    (output / "red-sea-voxel-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


# ----------------------------------------------------------------------------
# Indexed SHP sprites with per-country material ramps.
# ----------------------------------------------------------------------------

def sprite_palette(country):
    colors = [(0, 0, 0)] * 256
    for i in range(16):
        colors[16 + i] = (252 - i * 14, 0, 0)
    for i, material in enumerate(FACTIONS[country]["materials"]):
        for j in range(16):
            colors[32 + i * 16 + j] = tuple(min(252, round(v * (.4 + j * .065) + 5)) for v in material)
    return colors


@lru_cache(maxsize=None)
def _palette(country):
    return tuple(sprite_palette(country))


@lru_cache(maxsize=65536)
def color_index(country, r, g, b):
    palette = _palette(country)
    return min(range(32, 256), key=lambda i: (r - palette[i][0]) ** 2 + (g - palette[i][1]) ** 2 + (b - palette[i][2]) ** 2)


def indexed(image, country):
    data = bytearray()
    raw = image.tobytes()
    for i in range(0, len(raw), 4):
        r, g, b, a = raw[i:i + 4]
        if a < 96:
            data.append(0)
        elif r > 35 and r > 2.5 * g and r > 2.5 * b:
            data.append(16 + max(0, min(15, round((252 - r) / 14))))
        else:
            data.append(color_index(country, r, g, b))
    return bytes(data)


def encode_shp(frames, country):
    w, h = frames[0].size
    header = struct.pack("<4H", 0, w, h, len(frames))
    offset = 8 + 24 * len(frames)
    headers, data = bytearray(), bytearray()
    for frame in frames:
        assert frame.size == (w, h)
        headers += struct.pack("<4HB11xI", 0, 0, w, h, 1, offset + len(data))
        data += indexed(frame, country)
    return header + headers + data


def render(mesh, facing, size, scale, anchor=None, remap=False):
    """Screen X = rotated X, screen Y = Y/2 - Z; the fixed RA2 camera."""
    ss = 4
    image = Image.new("RGBA", (size[0] * ss, size[1] * ss))
    draw = ImageDraw.Draw(image)
    a = -facing * math.tau / 1024
    c, s = math.cos(a), math.sin(a)
    anchor = anchor or (size[0] / 2, size[1] / 2)
    projected = []
    for face in mesh.faces:
        vs = [(x * c - y * s, x * s + y * c, z) for x, y, z in face.vertices]
        normal = (face.normal[0] * c - face.normal[1] * s, face.normal[0] * s + face.normal[1] * c, face.normal[2])
        light = max(.48, min(1.18, .78 + normal[0] * -.20 + normal[1] * -.23 + normal[2] * .29))
        if face.color in VOXEL_TEAM:
            base = 200 if face.color == TEAM else 150
            color = (max(40, min(252, round(base * light))), 0, 0) if remap else \
                tuple(min(244, round(v * light * 1.1)) for v in (176, 48, 42))
        else:
            color = tuple(min(244, round(v * light * 1.20 + 8)) for v in face.color)
        screen = [((anchor[0] + x * scale) * ss, (anchor[1] + (y * .5 - z) * scale) * ss) for x, y, z in vs]
        projected.append((sum(y + z * .5 for _, y, z in vs) / len(vs), screen, color))
    for _, points, color in sorted(projected, key=lambda v: v[0]):
        draw.polygon(points, fill=(*color, 255))
    return image.resize(size, Image.Resampling.LANCZOS)


def infantry_frames(actor):
    frames = []
    # 8 stand, 8x6 run, 8x4 shoot, 8 death, 2x8 idle frames.
    for action, count in (("stand", 1), ("run", 6), ("shoot", 4)):
        for facing in range(8):
            for i in range(count):
                frames.append(render(soldier(actor, i / count, action), facing * 128, (48, 48), 15, (24, 35), True))
    for i in range(8):
        frames.append(render(soldier(actor, i / 7, "die"), 640, (48, 48), 15, (24, 35), True))
    for i in range(16):
        frames.append(render(soldier(actor, i / 16), 640, (48, 48), 15, (24, 35), True))
    return frames


def defense_frames(country, actor):
    build_mesh = FACTIONS[country]["fortification"]
    body, turret = build_mesh(actor), build_mesh(actor, True)
    frames = [render(body, 0, (96, 96), 20, (48, 67), True)]
    frames.extend(render(turret, i * 32, (96, 96), 20, (48, 67), True) for i in range(32))
    for i in range(8):
        frames.append(render(combine(body, transform(turret, lambda x, y, z: (x, y, z * (i + 1) / 8))),
                             640, (96, 96), 20, (48, 67), True))
    return frames


def fit(image, size=(240, 192), margin=.07):
    """Crop to the rendered silhouette and scale it into a cameo frame."""
    box = image.getchannel("A").getbbox()
    subject = image.crop(box)
    inner = (round(size[0] * (1 - 2 * margin)), round(size[1] * (1 - 2 * margin)))
    subject = ImageOps.contain(subject, inner, Image.Resampling.LANCZOS)
    result = Image.new("RGBA", size)
    result.alpha_composite(subject, ((size[0] - subject.width) // 2, (size[1] - subject.height) // 2))
    return result


def portrait(actor, parts):
    return fit(render(assembled(actor, parts), 640, (480, 384), 48, (240, 230)))


def build(output=OUTPUT):
    export_voxels(output)
    (output / "icons").mkdir(exist_ok=True)
    (output / "previews").mkdir(exist_ok=True)
    all_models = models()
    font = ImageFont.truetype(str(ROOT / "engine/openra/mods/common/FreeSansBold.ttf"), 12)
    heading = ImageFont.truetype(str(ROOT / "engine/openra/mods/common/FreeSansBold.ttf"), 23)
    for country, spec in FACTIONS.items():
        folder = output / spec["folder"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (country + ".pal")).write_bytes(bytes(v // 4 for rgb in sprite_palette(country) for v in rgb))
        manifest, portraits = {}, {}
        for actor in spec["infantry"]:
            frames = infantry_frames(actor)
            data = encode_shp(frames, country)
            (folder / (actor + ".shp")).write_bytes(data)
            manifest[actor] = {"frames": len(frames), "size": [48, 48], "sha256": hashlib.sha256(data).hexdigest()}
            portraits[actor] = fit(render(soldier(actor), 640, (240, 192), 95, (120, 180)), margin=.04)
            sheet = Image.new("RGBA", (8 * 48, 4 * 48), (*spec["background"], 255))
            for row, start in enumerate((0, 8, 56, 88)):
                for col in range(8):
                    sheet.alpha_composite(frames[start + col], (48 * col, 48 * row))
            sheet.save(folder / (actor + "-review.png"))
        for actor in spec["defenses"]:
            frames = defense_frames(country, actor)
            data = encode_shp(frames, country)
            (folder / (actor + ".shp")).write_bytes(data)
            manifest[actor] = {"frames": len(frames), "size": [96, 96], "sha256": hashlib.sha256(data).hexdigest()}
            build_mesh = spec["fortification"]
            portraits[actor] = fit(render(combine(build_mesh(actor), build_mesh(actor, True)), 640, (480, 384), 90, (240, 290)))
        for actor in spec["units"]:
            if actor not in portraits:
                portraits[actor] = portrait(actor, all_models[actor])
        for actor in spec["units"] + spec["defenses"]:
            art = portraits[actor]
            background = Image.new("RGBA", art.size, (*spec["gradient"], 255))
            draw = ImageDraw.Draw(background)
            r, g, b = spec["gradient"]
            for y in range(art.height):
                draw.line((0, y, art.width, y), fill=(r + y // 9, g + y // 11, b + y // 16, 255))
            background.alpha_composite(art)
            background.convert("RGB").resize((60, 48), Image.Resampling.LANCZOS).save(output / "icons" / (actor + ".png"))
        preview = Image.new("RGB", (512, 512), spec["background"])
        draw = ImageDraw.Draw(preview)
        draw.text((18, 12), spec["title"], font=heading, fill=spec["text"])
        for i, actor in enumerate(spec["units"] + spec["defenses"]):
            x, y = 16 + i % 4 * 124, 52 + i // 4 * 86
            tile = ImageOps.contain(portraits[actor], (116, 65))
            preview.paste(tile, (x + (116 - tile.width) // 2, y), tile)
            draw.text((x + 2, y + 65), LABELS[actor], font=font, fill=spec["text"])
        draw.text((18, 490), spec["footer"], font=font, fill=(172, 164, 138))
        preview.save(output / "previews" / (country + ".png"))
        preview.save(folder / "source-art-review.png")
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    build()
