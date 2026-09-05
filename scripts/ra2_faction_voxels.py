"""Export the project's authored faction meshes to native RA2 VXL/HVA models.

RA1 sprite frames are deliberately not reused: RA2 owns projection, smooth
rotation, voxel lighting and terrain shadows. No EA art is read by this builder.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import struct

import china_directional_assets as cn
import iran_directional_assets as ir
import turkey_directional_assets as tr
from ra2_turkey_assets import extra_models
from ra2_china_assets import extra_models as china_models
from ra2_iran_assets import extra_models as iran_models

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps/installer/ra2/modern-factions"
IDENTITY = (1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0.)
VOXELS_PER_UNIT = 10


def models():
    return {
        "r2qilin": (cn._qilin_hull(), cn._qilin_turret()),
        "r2lynx": (cn._lynx_hull(), cn._lynx_turret()),
        "r2mantis": (cn._mantis_hull(), cn._mantis_turret()),
        "r2cloud": (cn._plane_mesh(drone=True),),
        "r2karrar": (ir._karrar_hull(), ir._karrar_turret()),
        "r2raad": (ir._truck_hull(), ir._raad_turret()),
        "r2fajr": (ir._truck_hull(), ir._fajr_turret(loaded=True)),
        "r2mohajer": (mohajer(),),
        "r2bozkir": (tr._tracked_hull(), tr._turret("bozkir")),
        "r2yildirim": (tr._wheeled_hull(4), tr._turret("yildirim")),
        "r2sancak": (tr._wheeled_hull(3, ew=True), tr._turret("sancak")),
        "r2kuzgun": (tr._airframe("kuzgunm"),),
        **extra_models(),
        **china_models(),
        **iran_models(),
    }


def mohajer():
    # Retain the authored Iranian fuselage/sensor materials, but give this RA2
    # version the twin-boom silhouette shown in its new sidebar portrait.
    mesh = ir._mohajer_airframe()
    mesh.faces = [face for face in mesh.faces if face.color not in (ir.TEAM_LIGHT, ir.TEAM_DARK)]
    mesh.tapered_box((-2.30, 2.30, -0.35, 0.20, 0.20), (-2.22, 2.22, -0.25, 0.16, 0.29), ir.TEAM_LIGHT)
    for x in (-0.85, 0.85):
        mesh.box(x - 0.07, x + 0.07, 0.10, 1.80, 0.18, 0.30, ir.METAL)
        mesh.polygon(((x, 1.20, 0.25), (x, 1.84, 0.25), (x, 1.78, 0.85), (x, 1.47, 0.74)), ir.TEAM_DARK)
    mesh.box(-0.90, 0.90, 1.50, 1.75, 0.28, 0.36, ir.TEAM_DARK)
    return mesh


def coordinates(point):
    # Authored mesh: x right, negative y forward. VXL: x forward, y right.
    return (-point[1], point[0], point[2])


def normal_table():
    source = (ROOT / "engine/openra/OpenRA.Mods.Cnc/Traits/World/VoxelNormalsPalette.cs").read_text()
    raw = source.split("float[] RA2Normals =", 1)[1].split("];", 1)[0]
    values = [float(x) for x in re.findall(r"(-?\d+\.\d+)f", raw)]
    return list(zip(values[::3], values[1::3], values[2::3]))


def palette(meshes):
    # Reserve RA2's exact remap ramp, not RA1's 80..95 indices. Restrict
    # ownership tint to armor highlights/stripes, preserving neutral silhouettes.
    team = {cn.RED: 24, tr.RED: 24}
    colors = sorted({face.color for parts in meshes.values() for mesh in parts for face in mesh.faces} - team.keys())
    if len(colors) > 224:
        raise ValueError("Material palette exceeds the non-remap slots")
    result = [(0, 0, 0)] * 256
    for i in range(16):
        result[16 + i] = (max(24, 252 - 14 * i), 0, 0)
    indexes = {color: i + 32 for i, color in enumerate(colors)}
    indexes.update(team)
    for color in colors:
        # Match RA2's bright, neutral armor with localized ownership panels.
        # The old sprite renderer baked lighting into these darker materials;
        # native voxels receive the RA2 world light dynamically.
        neutral = {ir.TEAM_LIGHT: (177, 168, 120), ir.TEAM_MID: (142, 136, 97),
                   ir.TEAM_DARK: (105, 101, 75), ir.TEAM_DEEP: (67, 66, 53)}.get(color, color)
        result[indexes[color]] = tuple(min(240, round(channel * 1.30 + 12)) for channel in neutral)
    return bytes(channel // 4 for color in result for channel in color), indexes


def voxelize(mesh, colors, normals):
    points = [coordinates(vertex) for face in mesh.faces for vertex in face.vertices]
    lower = tuple(math.floor(min(p[i] for p in points) * VOXELS_PER_UNIT) - 1 for i in range(3))
    upper = tuple(math.ceil(max(p[i] for p in points) * VOXELS_PER_UNIT) + 1 for i in range(3))
    size = tuple(upper[i] - lower[i] + 1 for i in range(3))
    if max(size) > 255:
        raise ValueError("VXL dimensions exceed the byte-sized native grid")
    voxels = {}
    for face in mesh.faces:
        normal = coordinates(face.normal)
        normal_index = max(range(len(normals)), key=lambda i: sum(a * b for a, b in zip(normals[i], normal)))
        vertices = [tuple(p * VOXELS_PER_UNIT for p in coordinates(v)) for v in face.vertices]
        armor = face.color in {cn.GREEN, cn.GREEN_LIGHT, tr.OLIVE, tr.OLIVE_LIGHT, *ir.TEAM_MARKERS}
        air = face.color in {cn.SLATE, cn.SLATE_LIGHT, tr.AIR, tr.AIR_LIGHT, *ir.TEAM_MARKERS}
        a = vertices[0]
        for b, c in zip(vertices[1:-1], vertices[2:]):
            # Subvoxel triangle sampling preserves thin barrels, antennas and
            # wing planes; unlike image rotation it samples real 3D surfaces.
            steps = max(1, math.ceil(max(math.dist(a, b), math.dist(a, c), math.dist(b, c)) * 2))
            for j in range(steps + 1):
                for k in range(steps - j + 1):
                    p = tuple(a[d] + (b[d] - a[d]) * j / steps + (c[d] - a[d]) * k / steps for d in range(3))
                    key = tuple(math.floor(p[d] + 0.5) - lower[d] for d in range(3))
                    # Crisp ownership strips/panels are sampled on geometry,
                    # never painted over a rendered frame. Keep neutral armor,
                    # optics and track detail readable at the game's normal zoom.
                    side_panel = armor and abs(face.normal[0]) > 0.7
                    roof_strip = armor and face.normal[2] > 0.5 and abs(p[1]) < 0.8
                    wing_strip = air and face.normal[2] > 0.5 and 7.5 < abs(p[1]) < 10.5
                    index = 23 if side_panel or roof_strip or wing_strip else colors[face.color]
                    voxels[key] = (index, normal_index)
    return size, lower, voxels


def encode_vxl(size, lower, voxels, pal):
    sx, sy, sz = size
    starts, ends, spans = [], [], bytearray()
    for y in range(sy):
        for x in range(sx):
            if not any((x, y, z) in voxels for z in range(sz)):
                starts.append(-1)
                ends.append(-1)
                continue
            starts.append(len(spans))
            z = 0
            while z < sz:
                start = z
                while z < sz and (x, y, z) not in voxels:
                    z += 1
                skip = z - start
                start = z
                while z < sz and (x, y, z) in voxels:
                    z += 1
                count = z - start
                spans.extend((skip, count))
                for h in range(start, z):
                    spans.extend(voxels[x, y, h])
                spans.append(count)
            ends.append(len(spans) - 1)
    body = struct.pack(f"<{len(starts)}i", *starts) + struct.pack(f"<{len(ends)}i", *ends) + spans
    header = b"Voxel Animation\0" + struct.pack("<4I", 1, 1, 1, len(body)) + bytes((16, 31)) + pal
    limb = b"body".ljust(16, b"\0") + struct.pack("<3I", 0, 1, 0)
    bounds = (*lower, *(lower[i] + size[i] for i in range(3)))
    footer = struct.pack("<3If12f6f4B", 0, sx * sy * 4, sx * sy * 8, 1. / 12., *IDENTITY, *bounds, *size, 4)
    return header + limb + body + footer


def build(output=OUTPUT):
    meshes = models()
    pal, colors = palette(meshes)
    normals = normal_table()
    destination = output / "voxels"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "modern.pal").write_bytes(pal)
    report = {"format": "VXL/HVA", "normals": "RedAlert2", "remap_indices": list(range(16, 32)),
              "geometry_sources": ["scripts/china_directional_assets.py", "scripts/iran_directional_assets.py", "scripts/turkey_directional_assets.py"],
              "models": {}}
    for actor, parts in meshes.items():
        for part, mesh in enumerate(parts):
            name = actor + ("tur" if part else "")
            size, lower, voxels = voxelize(mesh, colors, normals)
            data = encode_vxl(size, lower, voxels, pal)
            (destination / (name + ".vxl")).write_bytes(data)
            matrices = [IDENTITY]
            if name in ("r2turnatur", "r2cranetur", "r2toufantur"):
                matrices = []
                for i in range(8):
                    a = i * math.pi / 16
                    c, s = math.cos(a), math.sin(a)
                    matrices.append((c, -s, 0., 0., s, c, 0., 0., 0., 0., 1., 0.))
            hva = bytes(16) + struct.pack("<2I", len(matrices), 1) + b"body".ljust(16, b"\0")
            hva += b"".join(struct.pack("<12f", *matrix) for matrix in matrices)
            (destination / (name + ".hva")).write_bytes(hva)
            report["models"][name] = {"size": size, "origin": lower, "occupied_voxels": len(voxels),
                "remap_voxels": sum(16 <= value[0] <= 31 for value in voxels.values()), "animation_frames": len(matrices),
                "sha256": hashlib.sha256(data).hexdigest()}
            print(name, size, len(voxels), flush=True)
    (output / "voxel-manifest.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    build()
