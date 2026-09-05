"""Authored Iran models and animated sprites for RA2's native camera.

Reuse the established Iranian vehicle designs, articulated infantry and native
indexed SHP pipeline. No rotated sprite sheets or proprietary artwork inputs.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

import iran_directional_assets as ir
import ra2_turkey_assets as native
from red_sea_directional_vehicle import Mesh

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps/installer/ra2/modern-factions"
INFANTRY = ("r2basij", "r2toophan", "r2dronecontrol", "r2shadowone")
DEFENSES = ("r2irbunker", "r2iraasite", "r2ircoast")
EXTRA_MODELS = ("r2coast", "r2toufan", "r2azar", "r2loiter", "r2peykaap", "r2ghadir")
UNITS = INFANTRY + ("r2karrar", "r2raad", "r2fajr", "r2coast", "r2mohajer", "r2toufan", "r2azar", "r2loiter", "r2peykaap", "r2ghadir")
LABELS = dict(zip(UNITS + DEFENSES, ("BASIJ", "TOOPHAN", "COORDINATOR", "SHADOW ONE", "KARRAR", "RAAD", "FAJR", "COAST LAUNCHER", "MOHAJER", "TOUFAN", "AZAR", "LOITER", "PEYKAAP", "GHADIR", "GUN BUNKER", "RAAD AA SITE", "DENIAL BATTERY")))


def rotor():
    mesh = Mesh()
    mesh.box(-2.7, 2.7, -.09, .09, 1.25, 1.40, ir.METAL)
    mesh.box(-.09, .09, -2.7, 2.7, 1.25, 1.40, ir.METAL)
    mesh.box(-.24, .24, -.16, .16, 1.38, 1.53, ir.RED)
    return mesh


def flight_surfaces(mesh):
    """Thin authored wings need upward normals for native voxel lighting.

    Their source sprite painter lit both sides. Native VXL stores one sampled
    normal per voxel; downward winding otherwise makes the visible wing black.
    Preserve vertical fins and deep fuselage surfaces.
    """
    result=Mesh()
    for face in mesh.faces:
        if face.normal[2]<-.5 and max(v[2] for v in face.vertices)-min(v[2] for v in face.vertices)<.40:
            face=replace(face,normal=tuple(-axis for axis in face.normal))
        result.faces.append(face)
    return result


def ghadir_hull():
    """Correct the closed hull's inward source-cylinder normals for VXL.

    Keep the shared RA1 geometry helper untouched. Recognize the radial hull
    and end caps by their authored cylinder boundary, leaving fins/tower alone.
    """
    mesh=ir._ghadir_hull()
    faces=[]
    for face in mesh.faces:
        on_hull=all(abs(abs(y)-2.28)<1e-6 and abs(math.hypot(x,z-.34)-.55)<1e-6 for x,y,z in face.vertices)
        if on_hull:
            center=tuple(sum(v[i] for v in face.vertices)/len(face.vertices)-(0,0,.34)[i] for i in range(3))
            if sum(a*b for a,b in zip(face.normal,center))<0:
                face=replace(face,normal=tuple(-axis for axis in face.normal))
        faces.append(face)
    mesh.faces=faces
    return mesh


def extra_models():
    return {
        "r2coast": (ir._truck_hull(), ir._coast_turret()),
        "r2toufan": (ir._toufan_airframe(), rotor()),
        "r2azar": (flight_surfaces(ir._azar_airframe()),),
        "r2loiter": (flight_surfaces(ir._loiter_airframe()),),
        "r2peykaap": (ir._peykaap_hull(), ir._peykaap_turret()),
        "r2ghadir": (ghadir_hull(),),
    }


def sprite_mesh(mesh):
    """Translate geometry's ownership markers into the native SHP remap key."""
    result = Mesh()
    neutral = {ir.TEAM_LIGHT: ir.SAND_LIGHT, ir.TEAM_MID: ir.SAND,
               ir.TEAM_DARK: ir.SAND_DARK, ir.TEAM_DEEP: ir.GREEN_DARK}
    for face in mesh.faces:
        color = native.tr.RED if face.color == ir.RED else neutral.get(face.color, face.color)
        result.faces.append(replace(face,color=color))
    return result


def soldier(role, phase=0., action="stand"):
    mesh = Mesh()
    uniform = ir.GREEN_DARK if role == "r2shadowone" else ir.SAND
    legs = ir.GREEN_DARK if role == "r2shadowone" else ir.GREEN
    swing = math.sin(phase * math.tau) * .25 if action == "run" else 0
    for side in (-1, 1):
        x, y = side * .15, side * swing
        mesh.slanted_box_y(x-.08, x+.08, -.02, y+.06, .62, .13, .14, legs)
        mesh.box(x-.09, x+.09, y-.16, y+.07, .02, .14, ir.RUBBER)
    mesh.tapered_box((-.21, .21, -.14, .17, .57), (-.28, .28, -.15, .14, 1.14), uniform)
    mesh.box(-.21, .21, -.21, -.15, .65, 1.06, ir.GREEN_DARK)
    for x in (-.17, .04):
        mesh.box(x, x+.12, -.25, -.20, .71, .90, ir.SAND_DARK)
    mesh.cylinder_z((0, 0, 1.27), .27, .16, (176, 139, 100), segments=8)
    mesh.cylinder_z((0, .01, 1.42), .15, .21, legs, segments=10)
    mesh.box(-.19, .19, -.17, -.14, 1.38, 1.44, ir.RED)
    mesh.box(-.15, .15, .16, .19, 1.39, 1.44, ir.RED)
    for side in (-1, 1):
        mesh.box(side*.29-.065, side*.29+.065, -.11, .10, .97, 1.08, ir.RED)
        mesh.slanted_box_y(side*.28-.05, side*.28+.05, -.04, -.41, .96, .84, .10, uniform)
    mesh.box(-.18, .18, .16, .32, .69, 1.08, legs)
    recoil = .04 * math.sin(phase * math.pi) if action == "shoot" else 0
    mesh.box(-.06, .06, -.92+recoil, -.28+recoil, .86, .94, ir.METAL)
    mesh.box(-.07, .07, -.40, -.27, .75, .89, ir.SAND_DARK)
    if role == "r2toophan":
        mesh.cylinder_y((.23, -.35, 1.07), 1.30, .13, ir.GREEN_DARK, segments=10)
        mesh.cylinder_y((.23, -1.01, 1.07), .06, .16, ir.METAL, segments=10)
        mesh.box(.15, .31, -.50, -.31, 1.18, 1.34, ir.GLASS)
    elif role == "r2dronecontrol":
        mesh.box(-.20, .20, -.47, -.35, .82, 1.03, ir.METAL)
        mesh.box(-.15, .15, -.475, -.47, .87, .98, (70, 164, 151))
        mesh.cylinder_z((.15, .28, 1.18), .92, .025, ir.METAL, segments=6)
    elif role == "r2shadowone":
        mesh.box(-.16, .16, -.17, -.145, 1.21, 1.32, ir.GREEN_DARK)
        mesh.cylinder_y((0, -1.01, .90), .25, .05, ir.METAL, segments=8)
        mesh.box(-.06, .06, -.50, -.31, .96, 1.04, ir.GLASS)
        mesh.box(-.27, -.18, .04, .17, .51, .74, ir.SAND_DARK)
    if action == "die":
        angle = phase * math.pi / 2
        mesh = native.transform(mesh, lambda x,y,z: (x,y*math.cos(angle)+z*math.sin(angle), max(.025,z*math.cos(angle)-y*math.sin(angle))))
    return sprite_mesh(mesh)


def fortification(role, turret=False):
    mesh = Mesh()
    if not turret:
        mesh.tapered_box((-1.14, 1.14, -1.14, 1.14, 0), (-.92, .92, -.92, .92, .26), (124,122,105))
        if role == "r2irbunker":
            for z in (.30, .48):
                for side in (-1, 1):
                    mesh.box(side*.86-.12, side*.86+.12, -.83, .83, z, z+.18, ir.SAND_DARK)
                mesh.box(-.82,.82,.72,.95,z,z+.18,ir.SAND)
            mesh.box(-.50,.50,-.80,.63,.31,.66,ir.GREEN_DARK)
        else:
            mesh.cylinder_z((0,0,.31),.35,.72,ir.GREEN_DARK,segments=8)
            mesh.box(-.75,.75,.42,.83,.33,.61,ir.SAND_DARK)
        mesh.box(-.44,.44,-.91,-.87,.28,.39,ir.RED)
        return sprite_mesh(mesh)
    mesh.cylinder_z((0,0,.73),.12,.48,ir.METAL,segments=12)
    if role == "r2irbunker":
        mesh.tapered_box((-.55,.55,-.48,.40,.70),(-.48,.48,-.44,.37,1.02),ir.SAND)
        mesh.box(-.45,.45,-.51,-.45,.76,.90,ir.GREEN_DARK)
        mesh.cylinder_y((0,-.87,.84),.82,.05,ir.METAL,segments=8)
    elif role == "r2iraasite":
        mesh.box(-.64,.64,-.27,.60,.80,1.09,ir.SAND)
        for x in (-.43,0,.43):
            mesh.slanted_box_y(x-.13,x+.13,-1.01,.45,1.64,1.09,.20,ir.SAND_LIGHT)
        mesh.box(-.05,.05,.64,.74,1.0,1.82,ir.METAL)
        mesh.box(-.49,.49,.65,.76,1.60,1.94,ir.GLASS)
    else:
        mesh.box(-.62,.62,-.18,.56,.80,1.05,ir.GREEN)
        for x in (-.35,.35):
            mesh.slanted_box_y(x-.20,x+.20,-1.20,.80,1.49,1.06,.32,ir.SAND)
            mesh.box(x-.16,x+.16,-1.30,-1.19,1.47,1.75,ir.METAL)
    mesh.box(-.19,.19,.04,.31,1.05,1.11,ir.RED)
    return sprite_mesh(mesh)


def build(output=OUTPUT):
    folder=output/"iran-art"
    folder.mkdir(parents=True,exist_ok=True)
    (output/"icons").mkdir(exist_ok=True)
    # The shared renderer's full material ramps keep the three faction sprite
    # palettes binary-compatible, with independently registered actor palettes.
    (folder/"iran.pal").write_bytes(bytes(v//4 for rgb in native.sprite_palette() for v in rgb))
    manifest,portraits={},{}
    for actor in INFANTRY:
        frames=[]
        for action,count in (("stand",1),("run",6),("shoot",4)):
            for facing in range(8):
                for i in range(count):
                    frames.append(native.render(soldier(actor,i/count,action),facing*128,(48,48),15,(24,35),True))
        for i in range(8): frames.append(native.render(soldier(actor,i/7,"die"),640,(48,48),15,(24,35),True))
        for i in range(16): frames.append(native.render(soldier(actor,i/16),640,(48,48),15,(24,35),True))
        data=native.encode_shp(frames)
        (folder/(actor+".shp")).write_bytes(data)
        manifest[actor]={"frames":len(frames),"size":[48,48],"sha256":hashlib.sha256(data).hexdigest()}
        portraits[actor]=native.render(soldier(actor),640,(240,192),95,(120,180))
        review=Image.new("RGBA",(384,192),(38,36,28))
        for row,start in enumerate((0,8,56,88)):
            for col in range(8): review.alpha_composite(frames[start+col],(col*48,row*48))
        review.save(folder/(actor+"-review.png"))
    for actor in DEFENSES:
        body,turret=fortification(actor),fortification(actor,True)
        frames=[native.render(body,0,(96,96),20,(48,67),True)]
        for i in range(32): frames.append(native.render(turret,i*32,(96,96),20,(48,67),True))
        for i in range(8): frames.append(native.render(native.combine(body,native.transform(turret,lambda x,y,z:(x,y,z*(i+1)/8))),640,(96,96),20,(48,67),True))
        data=native.encode_shp(frames)
        (folder/(actor+".shp")).write_bytes(data)
        manifest[actor]={"frames":len(frames),"size":[96,96],"sha256":hashlib.sha256(data).hexdigest()}
        portraits[actor]=native.render(native.combine(body,turret),640,(240,192),50,(120,153))
    # The existing RA2 Mohajer has a twin-boom adaptation. Read the canonical
    # voxel models so the full-roster preview matches the actual game silhouette.
    from ra2_faction_voxels import models
    all_models={actor:parts for actor,parts in models().items() if actor in UNITS}
    for actor,parts in all_models.items():
        # Small expendable airframes need a larger portrait crop so their wing,
        # sensor nose and ownership panel remain legible at native 60x48 size.
        portraits[actor]=native.render(sprite_mesh(native.combine(*parts)),640,(240,192),46 if actor=="r2loiter" else 32,(120,117))
    for actor in INFANTRY+DEFENSES+EXTRA_MODELS:
        art=portraits[actor]
        bg=Image.new("RGBA",art.size,(31,29,20,255))
        draw=ImageDraw.Draw(bg)
        for y in range(art.height): draw.line((0,y,art.width,y),fill=(25+y//9,26+y//12,20+y//17,255))
        bg.alpha_composite(art)
        bg.convert("RGB").resize((60,48),Image.Resampling.LANCZOS).save(output/"icons"/(actor+".png"))
    font=ImageFont.truetype(str(ROOT/"engine/openra/mods/common/FreeSansBold.ttf"),12)
    preview=Image.new("RGB",(512,512),(28,28,22))
    draw=ImageDraw.Draw(preview)
    heading=ImageFont.truetype(str(ROOT/"engine/openra/mods/common/FreeSansBold.ttf"),23)
    draw.text((18,12),"IRAN / LAYERED DENIAL",font=heading,fill=(239,228,199))
    for i,actor in enumerate(UNITS+DEFENSES):
        x,y=16+i%4*124,52+i//4*86
        tile=ImageOps.contain(portraits[actor],(116,65))
        preview.paste(tile,(x+(116-tile.width)//2,y),tile)
        draw.text((x+2,y+65),LABELS[actor],font=font,fill=(224,215,189))
    draw.text((18,490),"14 UNITS + 3 DEFENSES / SHARED SOVIET ECONOMY",font=font,fill=(171,167,140))
    (output/"previews").mkdir(exist_ok=True)
    preview.save(output/"previews/iran.png")
    preview.save(folder/"source-art-review.png")
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")


if __name__ == "__main__":
    build()
