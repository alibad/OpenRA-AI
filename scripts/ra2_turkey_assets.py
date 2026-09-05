"""Original Turkey art in RA2's native projection, palette and animation formats.

Vehicles reuse our authored Turkey meshes. Infantry and fortifications are
articulated meshes rendered at a fixed 2:1 camera, never rotated bitmaps.
The indexed TS SHP writer preserves transparency and ownership remap (16..31).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path
import struct
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

from red_sea_directional_vehicle import Mesh
import turkey_directional_assets as tr

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps/installer/ra2/modern-factions"
INFANTRY = ("r2trrifle", "r2trat", "r2trdroneop", "r2greywolf")
DEFENSES = ("r2hisar", "r2siper", "r2boran")
EXTRA_MODELS = ("r2aras", "r2gokkalkan", "r2deniz", "r2turna", "r2sahin", "r2marmara", "r2ege", "r2poyraz")
TURKEY_UNITS = INFANTRY + ("r2bozkir", "r2aras", "r2yildirim", "r2gokkalkan", "r2sancak", "r2deniz", "r2kuzgun", "r2turna", "r2sahin", "r2marmara", "r2ege", "r2poyraz")
LABELS = dict(zip(INFANTRY + DEFENSES + EXTRA_MODELS,
    ("RIFLEMAN", "AT SPECIALIST", "DRONE OPERATOR", "GREY WOLF", "HISAR", "SIPER", "BORAN",
     "ARAS-8", "GOKKALKAN", "DENIZ KAPLAN", "TURNA-AH", "SAHIN-X", "MARMARA", "EGE", "POYRAZ")))
LABELS.update(r2bozkir="BOZKIR", r2yildirim="YILDIRIM", r2sancak="SANCAK", r2kuzgun="KUZGUN")


def combine(*meshes):
    result = Mesh()
    result.faces = [face for mesh in meshes for face in mesh.faces]
    return result


def transform(mesh, fn):
    result = Mesh()
    for face in mesh.faces:
        result.polygon(tuple(fn(*v) for v in face.vertices), face.color, outline=face.outline)
    return result


def rotor():
    mesh = Mesh()
    mesh.box(-2.7, 2.7, -.08, .08, 1.59, 1.64, tr.CHARCOAL)
    mesh.box(-.08, .08, -2.7, 2.7, 1.59, 1.64, tr.CHARCOAL)
    mesh.box(-.30, .30, -.15, .15, 1.63, 1.69, tr.RED)
    return mesh


def naval_hull(name):
    """Order the original deck perimeter for native triangle/normal sampling.

    The classic painter tolerated the bow/left/right vertex ordering, but VXL
    triangulation crosses the deck and points its normal downward. Preserve all
    five authored vertices and materials, changing only their perimeter order.
    Leave the shared classic-art source untouched.
    """
    mesh=tr._ship_hull(name)
    deck=mesh.faces[5]
    corrected=Mesh()
    corrected.polygon(tuple(deck.vertices[i] for i in (0,2,3,4,1)),deck.color,outline=deck.outline)
    mesh.faces[5]=corrected.faces[0]
    return mesh


def sahin_airframe():
    """Keep the authored jet shape with outward fuselage/upward wing normals."""
    mesh=tr._airframe("sahinx")
    faces=[]
    for face in mesh.faces:
        on_fuselage=all(abs(abs(y+.15)-2.6)<1e-6 and abs(math.hypot(x,z-.55)-.30)<1e-6
                        for x,y,z in face.vertices)
        center=tuple(sum(v[i] for v in face.vertices)/len(face.vertices)-(0,-.15,.55)[i]
                     for i in range(3))
        inward_fuselage=on_fuselage and sum(a*b for a,b in zip(face.normal,center))<0
        downward_wing=(len(face.vertices) in (5,7) and face.normal[2]<-.5
                       and max(v[2] for v in face.vertices)-min(v[2] for v in face.vertices)<.2)
        if inward_fuselage or downward_wing:
            face=replace(face,normal=tuple(-axis for axis in face.normal))
        faces.append(face)
    mesh.faces=faces
    return mesh


def extra_models():
    ships = {}
    for name in ("marmara", "ege", "poyraz"):
        body = naval_hull(name)
        body.box(-.40, .40, .80, 1.12, 1.43 if name != "poyraz" else 1.09,
                 1.49 if name != "poyraz" else 1.15, tr.RED)
        ships["r2" + name] = (body, tr._ship_turret(name))
    return {
        "r2aras": (tr._wheeled_hull(4), tr._turret("remote")),
        "r2gokkalkan": (tr._wheeled_hull(4), tr._turret("gokkalkan")),
        "r2deniz": (tr._wheeled_hull(4, amphibious=True), tr._turret("remote")),
        "r2turna": (tr._airframe("turnaah"), rotor()),
        "r2sahin": (sahin_airframe(),),
        **ships,
    }


def soldier(role, phase=0., action="stand"):
    mesh = Mesh()
    uniform = tr.CHARCOAL if role == "r2greywolf" else tr.OLIVE
    swing = math.sin(phase * math.tau) * .24 if action == "run" else 0
    for side in (-1, 1):
        x, y = side * .16, side * swing
        mesh.slanted_box_y(x-.075, x+.075, -.05, y+.05, .63, .13, .15, uniform)
        mesh.box(x-.095, x+.095, y-.17, y+.09, .02, .14, tr.RUBBER)
    mesh.tapered_box((-.23, .23, -.15, .18, .57), (-.27, .27, -.14, .15, 1.15), uniform)
    mesh.box(-.20, .20, -.20, -.12, .69, 1.07, tr.OLIVE_DARK)
    for x in (-.14, .05):
        mesh.box(x, x+.09, -.24, -.19, .72, .90, tr.OLIVE_LIGHT)
    mesh.cylinder_z((0, 0, 1.29), .27, .16, (176, 139, 100), segments=8)
    mesh.cylinder_z((0, .01, 1.44), .15, .205, uniform, segments=10)
    mesh.box(-.15, .15, -.17, -.145, 1.27, 1.34, tr.GLASS)
    # Ownership shoulder panels are visible across all eight directions.
    for side in (-1, 1):
        mesh.box(side*.28-.06, side*.28+.06, -.12, .12, .96, 1.09, tr.RED)
        mesh.slanted_box_y(side*.28-.055, side*.28+.055, -.05, -.44, .92, .86, .11, uniform)
    mesh.box(-.15, .15, .18, .32, .69, 1.06, tr.OLIVE_DARK)
    recoil = .045 * math.sin(phase*math.pi) if action == "shoot" else 0
    mesh.box(-.06, .06, -.94+recoil, -.25+recoil, .88, .96, tr.STEEL)
    if role == "r2trat":
        mesh.cylinder_y((.20, -.26, 1.12), 1.10, .115, tr.OLIVE_DARK, segments=10)
        mesh.cylinder_y((.20, -.79, 1.12), .06, .14, tr.CHARCOAL, segments=10)
    elif role == "r2trdroneop":
        mesh.box(-.23, .23, -.48, -.34, .82, 1.03, tr.CHARCOAL)
        mesh.box(-.18, .18, -.485, -.48, .87, .99, (70, 164, 151))
        mesh.cylinder_z((.18, .25, 1.34), .75, .025, tr.STEEL, segments=6)
    elif role == "r2greywolf":
        mesh.cylinder_y((0, -1.03, .93), .25, .05, tr.CHARCOAL, segments=8)
        mesh.box(-.07, .07, -.57, -.37, 1.0, 1.08, tr.GLASS)
    if action == "die":
        angle = phase * math.pi / 2
        mesh = transform(mesh, lambda x,y,z: (x, y*math.cos(angle)+z*math.sin(angle),
                                               max(.025, z*math.cos(angle)-y*math.sin(angle))))
    return mesh


def fortification(name, turret=False):
    mesh = Mesh()
    if not turret:
        mesh.tapered_box((-1.1, 1.1, -1.1, 1.1, 0), (-.85, .85, -.85, .85, .36), (124, 122, 105))
        mesh.box(-.75, .75, -.75, .75, .35, .72, tr.OLIVE_DARK)
        for x in (-.83, .63):
            mesh.box(x, x+.20, -.80, .80, .37, .52, tr.RED)
        mesh.box(-.26, .26, -.80, -.75, .46, .65, tr.CHARCOAL)
        return mesh
    mesh.cylinder_z((0, 0, .77), .15, .48, tr.STEEL, segments=12)
    mesh.tapered_box((-.55, .55, -.55, .48, .82), (-.39, .39, -.39, .34, 1.35), tr.OLIVE)
    mesh.box(-.27, .27, .05, .28, 1.36, 1.42, tr.RED)
    if name == "r2siper":
        for x in (-.42, -.14, .14, .42):
            mesh.slanted_box_y(x-.10, x+.10, -1.0, .45, 1.70, 1.17, .18, tr.OLIVE_LIGHT)
        mesh.box(-.40, .40, .45, .55, 1.35, 2.0, tr.GLASS)
    elif name == "r2boran":
        mesh.cylinder_y((0, -1.2, 1.12), 1.8, .12, tr.STEEL, segments=10)
        mesh.cylinder_y((0, -2.08, 1.12), .20, .17, tr.CHARCOAL, segments=10)
    else:
        for x in (-.17, .17):
            mesh.cylinder_y((x, -.91, 1.20), 1.1, .045, tr.CHARCOAL, segments=8)
        mesh.box(.21, .38, -.43, -.26, 1.30, 1.49, tr.GLASS)
    return mesh


def render(mesh, facing, size, scale, anchor=None, remap=False):
    """Screen X = rotated X, screen Y = Y/2 - Z; true fixed RA2 camera."""
    ss = 4
    image = Image.new("RGBA", (size[0]*ss, size[1]*ss))
    draw = ImageDraw.Draw(image)
    # Native facing 0 points up, 256 left, 512 down, 768 right.
    a = -facing * math.tau / 1024
    c, s = math.cos(a), math.sin(a)
    anchor = anchor or (size[0]/2, size[1]/2)
    projected = []
    for face in mesh.faces:
        vs = [(x*c-y*s, x*s+y*c, z) for x,y,z in face.vertices]
        normal = (face.normal[0]*c-face.normal[1]*s, face.normal[0]*s+face.normal[1]*c, face.normal[2])
        light = max(.48, min(1.18, .78 + normal[0]*-.20 + normal[1]*-.23 + normal[2]*.29))
        color = tuple(min(244, round(v*light*1.20+8)) for v in face.color)
        if face.color == tr.RED and remap:
            color = (max(40, min(252, round(200*light))), 0, 0)
        screen = [((anchor[0]+x*scale)*ss, (anchor[1]+(y*.5-z)*scale)*ss) for x,y,z in vs]
        projected.append((sum(y+z*.5 for _,y,z in vs)/len(vs), screen, color))
    for _, points, color in sorted(projected, key=lambda v:v[0]):
        draw.polygon(points, fill=(*color, 255))
    return image.resize(size, Image.Resampling.LANCZOS)


def sprite_palette():
    colors = [(0,0,0)]*256
    for i in range(16): colors[16+i] = (252-i*14,0,0)
    # Material ramps preserve subtle armor/concrete shading at native scale;
    # a coarse RGB cube posterizes these tiny soldiers and defense emplacements.
    materials=(tr.OLIVE,tr.OLIVE_LIGHT,tr.OLIVE_DARK,tr.CHARCOAL,tr.STEEL,tr.RUBBER,
               tr.GLASS,tr.WHITE,tr.NAVAL,tr.AIR,(176,139,100),(70,164,151),(124,122,105),tr.LAMP)
    for i,material in enumerate(materials):
        for j in range(16):
            colors[32+i*16+j]=tuple(min(252,round(v*(.4+j*.065)+5)) for v in material)
    return colors


@lru_cache(maxsize=32768)
def color_index(r,g,b):
    return min(range(32,256), key=lambda i: sum((a-c)**2 for a,c in zip((r,g,b),_PALETTE[i])))


_PALETTE=sprite_palette()


def indexed(image):
    data = bytearray()
    for r,g,b,a in image.getdata():
        if a < 96: data.append(0)
        elif r > 35 and r > 2.5*g and r > 2.5*b:
            data.append(16 + max(0, min(15, round((252-r)/14))))
        else:
            data.append(color_index(r,g,b))
    return bytes(data)


def encode_shp(frames):
    w,h = frames[0].size
    header = struct.pack("<4H", 0,w,h,len(frames))
    offset = 8+24*len(frames)
    headers, data = bytearray(), bytearray()
    for frame in frames:
        assert frame.size == (w,h)
        pixels = indexed(frame)
        headers += struct.pack("<4HB11xI", 0,0,w,h,1,offset+len(data))
        data += pixels
    return header + headers + data


def build(output=OUTPUT):
    folder = output / "turkey-art"
    folder.mkdir(parents=True, exist_ok=True)
    (output/"icons").mkdir(exist_ok=True)
    pal = sprite_palette()
    (folder/"turkey.pal").write_bytes(bytes(v//4 for rgb in pal for v in rgb))
    manifest, portraits = {}, {}
    for actor in INFANTRY:
        frames = []
        # 8 stand, 8x6 run, 8x4 shoot, 8 death, 2x8 idle frames.
        for action, count in (("stand",1),("run",6),("shoot",4)):
            for facing in range(8):
                for i in range(count):
                    frames.append(render(soldier(actor,i/count,action), facing*128, (48,48), 15, (24,35), True))
        for i in range(8): frames.append(render(soldier(actor,i/7,"die"),640,(48,48),15,(24,35),True))
        for i in range(16): frames.append(render(soldier(actor,i/16),640,(48,48),15,(24,35),True))
        data = encode_shp(frames)
        (folder/(actor+".shp")).write_bytes(data)
        manifest[actor] = {"frames":len(frames),"size":[48,48],"sha256":hashlib.sha256(data).hexdigest()}
        portraits[actor] = render(soldier(actor),640,(240,192),95,(120,180))
        sheet=Image.new("RGBA",(8*48,4*48),(35,41,34))
        for row, start in enumerate((0,8,56,88)):
            for col in range(8): sheet.alpha_composite(frames[start+col],(48*col,48*row))
        sheet.save(folder/(actor+"-review.png"))
    for actor in DEFENSES:
        body, turret = fortification(actor), fortification(actor, True)
        frames=[render(body,0,(96,96),20,(48,67),True)]
        for i in range(32): frames.append(render(turret,i*32,(96,96),20,(48,67),True))
        for i in range(8):
            mesh=combine(body,transform(turret,lambda x,y,z:(x,y,z*(i+1)/8)))
            frames.append(render(mesh,640,(96,96),20,(48,67),True))
        data=encode_shp(frames)
        (folder/(actor+".shp")).write_bytes(data)
        manifest[actor]={"frames":len(frames),"size":[96,96],"sha256":hashlib.sha256(data).hexdigest()}
        portraits[actor]=render(combine(body,turret),640,(240,192),50,(120,153))
    for actor, parts in extra_models().items():
        portraits[actor]=render(combine(*parts),640,(240,192),29 if actor.startswith("r2marm") else 32,(120,117))
    for actor, art in portraits.items():
        background=Image.new("RGBA",art.size,(15,24,27,255))
        draw=ImageDraw.Draw(background)
        for y in range(art.height): draw.line((0,y,art.width,y),fill=(15+y//10,24+y//12,27+y//15,255))
        background.alpha_composite(art)
        background.convert("RGB").resize((60,48),Image.Resampling.LANCZOS).save(output/"icons"/(actor+".png"))
    # Review contact sheet depicts source renders, explicitly not a game capture.
    sheet=Image.new("RGB",(600,math.ceil(len(portraits)/5)*145),(17,24,25))
    font=ImageFont.truetype(str(ROOT/"engine/openra/mods/common/FreeSansBold.ttf"),12)
    for i,(actor,art) in enumerate(portraits.items()):
        tile=ImageOps.contain(art,(120,118))
        x,y=(i%5)*120,(i//5)*145
        sheet.paste(tile,(x,y),tile)
        ImageDraw.Draw(sheet).text((x+3,y+122),LABELS[actor],font=font,fill=(230,235,215))
    sheet.save(folder/"source-art-review.png")
    # The in-game faction preview must show the entire roster, not just the
    # original four vehicles. Use the same authored models as the actual units.
    from ra2_faction_voxels import models
    all_models = models()
    for actor in TURKEY_UNITS:
        if actor not in portraits:
            portraits[actor] = render(combine(*all_models[actor]),640,(240,192),32,(120,117))
    preview=Image.new("RGB",(512,512),(17,24,25))
    draw=ImageDraw.Draw(preview)
    title_font=ImageFont.truetype(str(ROOT/"engine/openra/mods/common/FreeSansBold.ttf"),23)
    draw.text((18,12),"TURKEY / COMBINED ARMS",font=title_font,fill=(236,241,226))
    for i,actor in enumerate(TURKEY_UNITS+DEFENSES):
        x,y=16+(i%4)*124,52+(i//4)*86
        tile=ImageOps.contain(portraits[actor],(116,65))
        preview.paste(tile,(x+(116-tile.width)//2,y),tile)
        draw.text((x+2,y+65),LABELS[actor],font=font,fill=(215,224,202))
    draw.text((18,490),"16 UNITS + 3 DEFENSES / SHARED ALLIED ECONOMY",font=font,fill=(145,165,148))
    (output/"previews").mkdir(exist_ok=True)
    preview.save(output/"previews/turkey.png")
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")


if __name__ == "__main__":
    build()
