"""China's authored combined-arms meshes adapted to native RA2 art formats.

China infantry retain their original helmet, relay pack, shoulder launcher and
Red Spear command cape silhouettes. Shared helpers only provide projection and
the indexed SHP encoder; no original-game graphics or rotated bitmaps are used.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
import china_directional_assets as cn
import ra2_turkey_assets as art
from red_sea_directional_vehicle import Mesh

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps/installer/ra2/modern-factions"
INFANTRY = ("r2cnrifle", "r2cnportable", "r2cnnetwork", "r2redspear")
DEFENSES = ("r2bastion", "r2skyshield", "r2spectrum")
EXTRA_MODELS = ("r2zbd", "r2phl", "r2skyspear", "r2crane", "r2luyang", "r2haiwang", "r2haiying", "r2kunlun", "r2jiaolong")
CHINA_UNITS = INFANTRY + ("r2qilin", "r2lynx", "r2mantis", "r2zbd", "r2phl", "r2cloud", "r2skyspear", "r2crane", "r2luyang", "r2haiwang", "r2haiying", "r2kunlun", "r2jiaolong")
LABELS = dict(zip(CHINA_UNITS + DEFENSES, ("RIFLEMAN", "MISSILE TEAM", "NETWORK", "RED SPEAR", "QILIN", "LYNX UGV", "MANTIS", "SEA DRAGON", "LONGBOW", "CLOUD UAV", "SKYSPEAR", "CRANE", "LUYANG", "HAIWANG", "HAIYING", "KUNLUN", "JIAOLONG", "BASTION", "SKYSHIELD", "SPECTRUM")))


def rotor():
    mesh = Mesh()
    mesh.box(-2.65, 2.65, -.065, .065, 1.42, 1.49, cn.SLATE_DARK)
    mesh.box(-.065, .065, -2.65, 2.65, 1.42, 1.49, cn.SLATE_DARK)
    mesh.box(-.23, .23, -.15, .15, 1.49, 1.55, cn.RED)
    return mesh


def extra_models():
    # PHL's pod is a fixed elevated rack. Its native chassis turns to fire.
    result = {"r2zbd": (cn._zbd_hull(), cn._zbd_turret()),
              "r2phl": (cn._phl(loaded=True),),
              "r2skyspear": (cn._plane_mesh(),),
              "r2crane": (cn._crane(), rotor())}
    for name in ("luyang", "haiwang", "haiying", "kunlun", "jiaolong"):
        body = cn._ship_hull("cn" + name)
        if name=="jiaolong":
            # The classic authored Y-cylinder has inward-facing normals. Native
            # voxel lighting exposes this as a black upper hull; correct winding
            # of those cylinder faces without changing the submarine silhouette.
            corrected=Mesh()
            for face in body.faces:
                center=tuple(sum(v[i] for v in face.vertices)/len(face.vertices) for i in range(3))
                radial=(center[0],center[1]+.08,center[2]-.43)
                inward=sum(n*r for n,r in zip(face.normal,radial))<0
                vertices=tuple(reversed(face.vertices)) if face.color==cn.SLATE and inward else face.vertices
                corrected.polygon(vertices,face.color,outline=face.outline)
            body=corrected
        body.box(-.26, .26, .26, .50, 1.29, 1.35, cn.RED)
        result["r2" + name] = (body, cn._ship_turret("cn"+name)) if name in ("luyang", "haiying") else (body,)
    return result


def soldier(role, phase=0., action="stand"):
    mesh = Mesh()
    heroic = role == "r2redspear"
    uniform, dark = (cn.SLATE, cn.SLATE_DARK) if heroic else (cn.GREEN, cn.GREEN_DARK)
    stride = math.sin(phase*math.tau)*.28 if action == "run" else 0
    for side in (-1, 1):
        x, y = side*.17, side*stride
        mesh.slanted_box_y(x-.07, x+.07, 0, y, .70, .18, .15, dark)
        mesh.box(x-.10, x+.10, y-.19, y+.09, .02, .17, cn.RUBBER)
    mesh.tapered_box((-.26, .26, -.14, .17, .61), (-.29, .29, -.16, .19, 1.20), uniform)
    mesh.box(-.20, .20, -.22, -.16, .78, 1.12, dark)
    for x in (-.19, -.04, .11):
        mesh.box(x, x+.085, -.26, -.21, .80, .97, cn.GREEN_LIGHT)
    mesh.cylinder_z((0, -.02, 1.36), .22, .15, (180,135,96), segments=8)
    mesh.cylinder_z((0, .0, 1.49), .14, .235, dark if heroic else cn.GREEN_LIGHT, segments=10)
    mesh.box(-.23, .23, -.20, -.13, 1.47, 1.51, cn.RED)
    for side in (-1, 1):
        mesh.slanted_box_y(side*.30-.06, side*.30+.06, -.06, -.47, 1.04, .92, .13, uniform)
        mesh.box(side*.30-.065, side*.30+.065, -.06, .10, 1.06, 1.19, cn.RED)
    recoil = .035*math.sin(phase*math.pi) if action == "shoot" else 0
    mesh.box(-.08, .08, -.90+recoil, -.27+recoil, .96, 1.04, cn.STEEL)
    mesh.cylinder_y((0,-1.03+recoil,1.0),.28,.045,cn.SLATE_DARK,segments=8)
    if role == "r2cnportable":
        mesh.cylinder_y((.22,-.28,1.30),1.15,.11,cn.SLATE_DARK,segments=10)
        mesh.cylinder_y((.22,-.88,1.30),.08,.13,cn.RED,segments=10)
    elif role == "r2cnnetwork":
        mesh.box(-.26,.26,.19,.39,.80,1.22,cn.SLATE_DARK)
        mesh.cylinder_z((.20,.29,1.50),.95,.02,cn.STEEL,segments=6)
        mesh.box(-.18,.18,-.49,-.39,1.0,1.18,cn.GLASS)
    elif heroic:
        mesh.polygon(((-.27,.21,1.16),(.27,.21,1.16),(.44,.48,.28),(-.44,.48,.28)),cn.RED)
        mesh.box(-.06,.06,-.55,-.32,1.06,1.14,cn.GLASS)
    if action == "die":
        angle = phase*math.pi/2
        mesh = art.transform(mesh, lambda x,y,z:(x,y*math.cos(angle)+z*math.sin(angle),max(.025,z*math.cos(angle)-y*math.sin(angle))))
    return mesh


def faction_render(mesh, *args, **kwargs):
    # Shared renderer recognizes one authored remap material. Preserve geometry,
    # and map only China's red ownership panels to that marker.
    mapped = Mesh()
    for face in mesh.faces:
        mapped.polygon(face.vertices, art.tr.RED if face.color == cn.RED else face.color, outline=face.outline)
    return art.render(mapped, *args, **kwargs)


def fortification(actor, turret=False):
    """Retain the authored silhouette, articulate construction at RA2 scale."""
    kind="cn"+actor[2:]
    mesh=cn._defense_top(kind) if turret else cn._defense_base(kind)
    if not turret:
        # Concrete plinth, inset steel access doors and open cooling louvers
        # distinguish construction materials across the broad visible faces.
        concrete=(124,122,105)
        mesh.box(-.98,.98,-.98,.98,.0,.10,concrete)
        for side in (-1,1):
            x=side*.925
            mesh.box(x-.025,x+.025,-.65,.65,.13,.29,cn.SLATE_DARK)
            for y in (-.54,-.27,0,.27,.54):
                mesh.box(x-.035,x+.035,y-.025,y+.025,.15,.27,cn.SLATE_LIGHT)
        mesh.box(-.62,.62,-.935,-.918,.12,.29,cn.SLATE_DARK)
        for x in (-.45,0,.45):
            mesh.box(x-.035,x+.035,-.945,-.915,.14,.27,cn.STEEL)
        mesh.box(-.62,.62,.918,.945,.12,.29,cn.SLATE_DARK)
        for x in (-.48,-.24,0,.24,.48):
            mesh.box(x-.035,x+.035,.945,.960,.15,.27,cn.SLATE_LIGHT)
        mesh.box(-.22,.22,.615,.657,.36,.61,cn.SLATE_DARK)
        mesh.box(-.16,.16,.657,.674,.39,.57,cn.SLATE_LIGHT)
        mesh.box(.08,.12,.674,.69,.44,.51,cn.STEEL)
        mesh.box(-.22,.22,-.645,-.615,.36,.61,cn.SLATE_DARK)
        mesh.box(-.16,.16,-.657,-.643,.39,.57,cn.SLATE_LIGHT)
        mesh.box(.08,.12,-.671,-.655,.44,.51,cn.STEEL)
        for x in (-.71,.61):
            mesh.box(x,x+.10,-.76,.76,.325,.355,cn.RED)
    elif actor=="r2bastion":
        for x in (-.13,.13):
            mesh.cylinder_y((x,-.96,.94),.32,.07,cn.SLATE_LIGHT,segments=8)
            mesh.cylinder_y((x,-1.15,.94),.08,.08,cn.SLATE_DARK,segments=8)
        mesh.box(-.32,.32,.29,.41,.83,1.03,cn.SLATE_DARK)
        for x in (-.22,0,.22):
            mesh.box(x-.035,x+.035,.415,.435,.86,.99,cn.SLATE_LIGHT)
    elif actor=="r2skyshield":
        for x in (-.46,.24):
            mesh.box(x,x+.22,-.435,-.415,.78,1.10,cn.GREEN_LIGHT)
        mesh.box(-.16,.16,.20,.24,1.11,1.49,cn.STEEL)
    else:
        for x in (-.43,-.21,0,.21,.43):
            mesh.box(x-.008,x+.008,-.088,-.077,1.51,1.69,cn.SLATE_LIGHT)
        mesh.box(-.58,.58,-.09,.09,1.43,1.48,cn.STEEL)
    return mesh


def build(output=OUTPUT):
    folder = output/"china-art"
    folder.mkdir(parents=True, exist_ok=True)
    (output/"icons").mkdir(exist_ok=True)
    (folder/"china.pal").write_bytes(bytes(v//4 for rgb in art.sprite_palette() for v in rgb))
    manifest, portraits = {}, {}
    for actor in INFANTRY:
        frames=[]
        for action,count in (("stand",1),("run",6),("shoot",4)):
            for facing in range(8):
                for i in range(count):
                    frames.append(faction_render(soldier(actor,i/count,action),facing*128,(48,48),14,(24,35),True))
        for i in range(8):
            frames.append(faction_render(soldier(actor,i/7,"die"),640,(48,48),14,(24,35),True))
        for i in range(16):
            frames.append(faction_render(soldier(actor,i/16),640,(48,48),14,(24,35),True))
        data=art.encode_shp(frames)
        (folder/(actor+".shp")).write_bytes(data)
        manifest[actor]={"frames":len(frames),"size":[48,48],"sha256":hashlib.sha256(data).hexdigest()}
        portraits[actor]=faction_render(soldier(actor),640,(240,192),90,(120,180))
    for actor in DEFENSES:
        body=fortification(actor)
        turret=fortification(actor,True)
        frames=[faction_render(body,0,(96,96),20,(48,67),True)]
        frames.extend(faction_render(turret,i*32,(96,96),20,(48,67),True) for i in range(32))
        for i in range(8):
            mesh=art.combine(body,art.transform(turret,lambda x,y,z:(x,y,z*(i+1)/8)))
            frames.append(faction_render(mesh,640,(96,96),20,(48,67),True))
        data=art.encode_shp(frames)
        (folder/(actor+".shp")).write_bytes(data)
        manifest[actor]={"frames":len(frames),"size":[96,96],"sha256":hashlib.sha256(data).hexdigest()}
        portraits[actor]=faction_render(art.combine(body,turret),640,(240,192),55,(120,160))
    original={"r2qilin":(cn._qilin_hull(),cn._qilin_turret()),"r2lynx":(cn._lynx_hull(),cn._lynx_turret()),"r2mantis":(cn._mantis_hull(),cn._mantis_turret()),"r2cloud":(cn._plane_mesh(drone=True),)}
    for actor,parts in {**extra_models(),**original}.items():
        portraits[actor]=faction_render(art.combine(*parts),640,(240,192),26 if actor in ("r2haiwang","r2kunlun") else 32,(120,130))
    for actor,portrait in portraits.items():
        if actor in original:
            continue # Preserve the previously approved original four cameos.
        background=Image.new("RGBA",portrait.size,(20,29,31,255))
        background.alpha_composite(portrait)
        background.convert("RGB").resize((60,48),Image.Resampling.LANCZOS).save(output/"icons"/(actor+".png"))
    font=ImageFont.truetype(str(ROOT/"engine/openra/mods/common/FreeSansBold.ttf"),12)
    titlefont=ImageFont.truetype(str(ROOT/"engine/openra/mods/common/FreeSansBold.ttf"),23)
    sheet=Image.new("RGB",(512,512),(17,24,25))
    draw=ImageDraw.Draw(sheet)
    draw.text((18,12),"CHINA / NETWORKED ARMS",font=titlefont,fill=(236,241,226))
    for i,actor in enumerate(CHINA_UNITS+DEFENSES):
        x,y=16+(i%4)*124,52+(i//4)*86
        tile=ImageOps.contain(portraits[actor],(116,65))
        sheet.paste(tile,(x+(116-tile.width)//2,y),tile)
        draw.text((x+2,y+65),LABELS[actor],font=font,fill=(215,224,202))
    draw.text((18,490),"17 UNITS + 3 DEFENSES / SHARED ALLIED ECONOMY",font=font,fill=(145,165,148))
    (output/"previews").mkdir(exist_ok=True)
    sheet.save(output/"previews/china.png")
    sheet.save(folder/"source-art-review.png")
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")


if __name__ == "__main__":
    build()
