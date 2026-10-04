#!/usr/bin/env python3
"""CPU-only authored mesh and animation packages; no EA image inputs.

Native RA2 VXL/HVA and independently projected Classic SHP frames share authored
geometry. The contact sheets are source renders, not native gameplay evidence.
"""
from __future__ import annotations
from dataclasses import replace
from functools import lru_cache
import hashlib, json, math, re, runpy, struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
import ra2_turkey_assets as art
import ra2_faction_voxels as vxl
import red_sea_directional_vehicle as geometry
import red_sea_infantry as infantry

DEFINITIONS=runpy.run_path(str(Path(__file__).with_name('build-levant-factions.py')))
ROOT=DEFINITIONS['ROOT']; MOD=DEFINITIONS['MOD']; RA=DEFINITIONS['RA']; PACK=DEFINITIONS['PACK']
write=DEFINITIONS['write']; units_by_faction=DEFINITIONS['FACTIONS']
TEAM=(224,0,0)
COLORS={
 'israel': {'paint':(108,115,90),'edge':(156,165,133),'dark':(58,66,56),'glass':(92,171,204),'stone':(139,146,140),'accent':(89,139,184)},
 'hezbollah': {'paint':(103,99,62),'edge':(147,146,105),'dark':(55,57,40),'glass':(113,157,148),'stone':(142,133,110),'accent':(170,162,99)},
}
FONT=ROOT/'OpenRA/mods/common/FreeSansBold.ttf'
REPORT={ 'evidence':'measured', 'source':'CPU authored geometry; no original game assets', 'paidSpend':0,'actors':{} }

def materials(faction):
 c=COLORS[faction]
 return [c['paint'],c['edge'],c['dark'],c['glass'],c['stone'],c['accent'],(34,39,39),(92,102,107),(181,193,190),(157,117,83),(72,56,43),(230,136,53),(219,208,169),(95,120,125)]

def palette(faction):
 colors=[(0,0,0)]*256
 colors[1]=(12,15,12)
 for i in range(16): colors[16+i]=(252-i*14,0,0)
 for i,color in enumerate(materials(faction)):
  for j in range(16): colors[32+i*16+j]=tuple(min(252,round(v*(.40+j*.065)+4)) for v in color)
 return colors

def body(faction, kind, actor=''):
 c=COLORS[faction]; mesh=geometry.Mesh(); heavy=kind in ('main-battle-tank','transport')
 if actor=='r2ilgunship':
  mesh.tapered_box((-.46,.46,-2.05,.68,.45),(-.35,.35,-1.83,.48,1.26),c['paint'])
  mesh.tapered_box((-.29,.29,-2.17,-.60,.75),(-.22,.22,-1.76,-.60,1.26),c['glass'])
  mesh.tapered_box((-.25,.25,.50,2.25,.76),(-.10,.10,.64,2.30,1.01),c['edge'])
  mesh.box(-.03,.03,2.08,2.52,.91,1.57,c['dark'])
  mesh.box(-.69,.69,1.82,2.14,.96,1.05,c['edge'])
  for sign in (-1,1):
   mesh.box(sign*.70-.22,sign*.70+.22,-.13,.66,.51,.59,c['edge'])
   mesh.cylinder_y((sign*.68,-.18,.49),1.32,.15,c['dark'],segments=8)
   mesh.cylinder_y((sign*.22,.09,1.19),1.15,.18,c['dark'],segments=10)
   mesh.box(sign*.40-.055,sign*.40+.055,-1.25,.42,.10,.18,c['dark'])
  mesh.box(-.24,.24,.10,.49,1.36,1.49,c['paint'])
  mesh.box(-.22,.22,-.20,.08,1.40,1.44,TEAM)
  mesh.cylinder_y((0,-1.60,.44),.78,.055,c['dark'],segments=8)
  return mesh
 if kind in ('interceptor','strike-aircraft'):
  jet=kind=='interceptor'; drone=faction=='hezbollah'
  length=3.0 if jet else 1.8
  mesh.tapered_box((-.38,.38,-length,1.7,.40),(-.24,.24,-length+.25,1.4,.91),c['paint'])
  for sign in (-1,1):
   mesh.polygon(((0,-.7,.58),(sign*(2.5 if jet else 2.0),.7,.52),(sign*2.1,1.2,.48),(0,.6,.62)),c['edge'])
   mesh.box(sign*.70-.10,sign*.70+.10,.65,1.65,.53,.64,c['dark'])
  mesh.tapered_box((-.24,.24,-1.1,-.3,.85),(-.17,.17,-.9,-.3,1.20),c['glass'])
  mesh.polygon(((0,.85,.6),(0,1.4,1.55),(0,1.85,.65)),c['edge'])
  mesh.box(-.20,.20,1.3,1.8,.66,.72,TEAM)
  if not jet and not drone:
   mesh.box(-.045,.045,-.12,.12,.91,1.56,c['dark'])
  return mesh
 if kind in ('ship','frigate','tender'):
  length=3.8 if kind in ('frigate','tender') else 2.4
  width=.94 if length>3 else .63
  deck=[(-width,-length+.8,.5),(0,-length,.5),(width,-length+.8,.5),(width,length,.5),(-width,length,.5)]
  mesh.polygon(deck,c['stone']); lower=[(x*.80,y*.85,.05) for x,y,_ in deck]
  for i in range(5): mesh.polygon((lower[i],lower[(i+1)%5],deck[(i+1)%5],deck[i]),c['dark'])
  mesh.box(-width*.68,width*.68,-.1,1.5,.5,1.03,c['paint'])
  mesh.box(-.38,.38,-.08,.08,.88,1.15,c['glass'])
  mesh.box(-.04,.04,.65,.74,1.03,2.15,c['dark'])
  mesh.box(-.48,.48,.65,.79,1.75,1.90,c['edge'])
  mesh.box(-width,width,1.6,1.8,.5,.58,TEAM)
  # Distinct working decks, missile canisters and an unmanned payload skiff.
  if actor=='r2hzmissileboat':
   for sign in (-1,1):
    mesh.box(sign*.48-.12,sign*.48+.12,-1.95,-.72,.56,.83,c['edge'])
    mesh.box(sign*.48-.085,sign*.48+.085,-2.03,-1.95,.61,.78,c['dark'])
  if actor=='r2hzskiff':
   mesh=geometry.Mesh()
   mesh.polygon(((-.52,-1.22,.30),(0,-1.93,.30),(.52,-1.22,.30),(.52,1.45,.30),(-.52,1.45,.30)),c['dark'])
   mesh.box(-.37,.37,-.95,.86,.31,.66,c['paint'])
   mesh.box(-.27,.27,-.48,.57,.67,.76,c['edge'])
   mesh.box(-.20,.20,1.08,1.62,.29,.63,c['dark'])
   mesh.box(-.16,.16,.64,.82,.68,.72,TEAM)
   mesh.box(-.02,.02,.85,.90,.76,1.23,c['dark'])
  if kind=='tender':
   for x in (-.65,.1): mesh.box(x,x+.55,-2.2,-.5,.54,1.10,c['edge'])
   mesh.box(-.07,.07,.82,.91,1.04,2.10,c['edge'])
   mesh.box(-.07,.85,.82,.91,2.01,2.10,c['edge'])
  if kind=='frigate':
   for sign in (-1,1):
    mesh.box(sign*.58-.19,sign*.58+.19,-2.25,-1.13,.53,.76,c['edge'])
    for i in range(4):mesh.box(sign*.58-.15,sign*.58+.15,-2.21+i*.25,-2.09+i*.25,.77,.80,c['dark'])
  return mesh
 if faction=='israel':
  w=1.12 if heavy else .88; length=2.08 if heavy else 1.88
  for x in (-w,w):
   mesh.box(x-.16,x+.16,-length,length,.12,.52,(34,39,39))
   for y in (-1.4,-.8,-.2,.4,1.0,1.5): mesh.cylinder_x((x,y,.28),.38,.21,(92,102,107),segments=8)
  mesh.tapered_box((-w,w,-length,length,.45),(-w+.13,w-.13,-length+.36,length-.20,.93),c['paint'])
  for sign in (-1,1):
   for y in (-1.2,-.2,.8): mesh.box(sign*w-.16,sign*w+.16,y,y+.78,.53,.94,c['edge'])
  mesh.box(-.35,.35,-length+.33,-length+.45,.75,.95,c['glass'])
  mesh.box(-.5,.5,1.24,1.80,.94,.99,c['dark'])
  for i in range(6):mesh.box(-.42,.42,1.27+i*.075,1.30+i*.075,1.0,1.02,c['edge'])
  for sign in (-1,1):
   for y in (-1.08,.08,1.24):mesh.box(sign*w-.04,sign*w+.04,y,y+.07,.77,.84,c['dark'])
  mesh.box(-.14,.14,-1.58,-.95,.97,1.0,TEAM)
  if kind=='transport':
   mesh.box(-.72,.72,-.30,1.25,.92,1.25,c['paint'])
   mesh.box(-.60,.60,1.18,1.32,.94,1.38,c['dark'])
 else:
  for x in (-.82,.82):
   for y in (-1.25,1.0): mesh.cylinder_x((x,y,.29),.26,.32,(34,39,39),segments=10)
  mesh.box(-.76,.76,-1.95,1.6,.30,.58,c['paint'])
  mesh.box(-.68,.68,-1.76,-.26,.56,1.20,c['paint'])
  mesh.box(-.63,.63,-1.80,-1.71,.94,1.16,c['glass'])
  mesh.box(-.60,.60,-.18,1.45,.57,.62,c['dark'])
  for x in (-.71,.63): mesh.box(x,x+.08,-.2,1.5,.62,.92,c['edge'])
  mesh.box(-.22,.22,-1.65,-1.0,1.22,1.25,TEAM)
  mesh.box(-.29,.29,1.50,1.56,.61,.87,(34,39,39))
 return mesh

def weapon(faction, kind, *, loaded=True):
 c=COLORS[faction]; mesh=geometry.Mesh(); z=1.22 if faction=='israel' else .91
 mesh.cylinder_z((0,0,z),.18,.42,(92,102,107),segments=12)
 if faction=='israel' and kind=='artillery':
  mesh.box(-.60,.60,-.18,.88,z,z+.51,c['paint'])
  mesh.cylinder_y((0,-1.54,z+.33),2.64,.11,c['dark'],segments=12)
  mesh.box(-.17,.17,-2.94,-2.69,z+.21,z+.45,c['edge'])
  mesh.box(-.28,.28,.22,.54,z+.52,z+.57,TEAM)
  return mesh
 if kind in ('anti-air','anti-armor','artillery'):
  tubes=4 if kind=='anti-air' else 6 if kind=='artillery' else 2
  for i in range(tubes):
   x=(i-(tubes-1)/2)*.20
   mesh.box(x-.085,x+.085,-1.04,.66,z+.15,z+.40,c['edge'])
   if loaded: mesh.box(x-.06,x+.06,-1.11,-1.04,z+.20,z+.32,(34,39,39))
  if kind=='anti-air':
   mesh.box(-.05,.05,.39,.47,z+.41,z+1.01,c['dark'])
   mesh.box(-.41,.41,.39,.49,z+.80,z+1.11,c['glass'])
 else:
  heavy=kind=='main-battle-tank'
  mesh.tapered_box((-.71,.71,-.85,.81,z),(-.52,.52,-.67,.62,z+.43),c['paint'])
  mesh.cylinder_y((0,-1.45,z+.27),2.2 if heavy else 1.35,.09 if heavy else .065,(92,102,107),segments=10)
  mesh.box(-.36,.36,.24,.72,z+.43,z+.48,TEAM)
  mesh.box(.33,.48,-.59,-.47,z+.38,z+.57,c['glass'])
 return mesh

def structure(faction, role, turret=False):
 c=COLORS[faction]; mesh=geometry.Mesh()
 if turret: return weapon(faction,role)
 mesh.tapered_box((-1.08,1.08,-1.08,1.08,0),(-.90,.90,-.90,.90,.32),c['stone'])
 mesh.box(-.78,.78,-.78,.78,.32,.76,c['paint'])
 mesh.box(-.33,.33,-.80,-.77,.42,.70,c['dark'])
 for x in (-.75,.60): mesh.box(x,x+.15,-.78,.78,.54,.72,TEAM)
 if role=='relay':
  mesh.box(-.34,.34,-.30,.30,.76,1.00,c['edge'])
  mesh.box(-.06,.06,-.06,.06,1.,2.52,c['dark'])
  mesh.box(-.67,.67,-.12,.12,1.94,2.34,c['glass'])
  mesh.box(-.09,.09,-.09,.09,2.53,2.65,c['accent'])
 elif role=='workshop':
  mesh.box(-.63,.63,-.42,.42,.76,1.16,c['edge'])
  mesh.box(-.07,.07,-.78,.78,1.16,1.25,TEAM)
  mesh.box(-.58,-.48,.54,.64,.76,1.94,c['dark'])
  mesh.box(-.58,.55,.54,.64,1.84,1.94,c['edge'])
 return mesh

def save_ts(path, frames):
 path.parent.mkdir(parents=True,exist_ok=True)
 data=art.encode_shp(frames); path.write_bytes(data)
 return hashlib.sha256(data).hexdigest()

def sequences(actor, faction, kind, *, classic=False, bodyparts=1, turret=True, air=False, reload=False):
 image=actor[2:] if classic else actor
 file=f'ra|bits/levant/{image}.shp' if classic else f'ra2|modern-factions/{faction}-art/{image}.shp'
 icon=f'ra|bits/levant/{image}icon.shp' if classic else f'ra2|modern-factions/icons/{image}.png'
 s=f'{image}:\n'
 if not classic: s+='\tInherits@MC: ^MindControllable\n'
 s+=f'\tDefaults:\n\t\tFilename: {file}\n'
 if not classic: s+=f'\t\tOffset: {"0, -11, 16" if kind=="infantry" else "0, -19, 19"}\n'
 def seq(name,start=0,length=1,facings=None, classicFacing=False):
  nonlocal s
  s+=f'\t{name}:\n'
  if start:s+=f'\t\tStart: {start}\n'
  if length>1:s+=f'\t\tLength: {length}\n\t\tTick: 80\n'
  if facings:s+=f'\t\tFacings: {facings}\n'
  if classicFacing:s+='\t\tUseClassicFacings: True\n'
 if kind=='infantry':
  for name,start,length,facings in [('stand',0,1,8),('stand2',8,1,8),('run',16,6,8),('shoot',64,8,8),('prone-stand',128,1,8),('prone-stand2',128,1,8),('prone-run',136,4,8),('liedown',168,2,8),('standup',184,2,8),('prone-shoot',200,8,8),('idle1',264,8,None),('idle2',272,8,None),('die1',280,8,8),('die2',344,8,8),('die3',408,8,8),('die4',472,12,8),('die5',568,18,8),('die6',568,18,8),('die-crushed',711,1,None),('parachute',712,1,None)]:seq(name,start,length,facings)
  if classic: s+='\tgarrison-muzzle:\n\t\tFilename: minigun.shp\n\t\tLength: 6\n\t\tFacings: 8\n'
  else:
   s+='\tgarrison-muzzle:\n\t\tLength: 6\n\t\tFacings: 8\n\t\tCombine:\n'
   for i,direction in enumerate(['n','nw','w','sw','s','se','e','ne']): s+=f'\t\t\t{i}:\n\t\t\t\tFilename: mgun-{direction}.shp\n\t\t\t\tLength: 6\n\t\t\t\tOffset: 0, 0\n'
 elif kind=='structure':
  seq('idle');seq('damaged-idle',41);seq('make',33,8)
  if turret:seq('turret',1,1,32,classic);seq('damaged-turret',1,1,32,classic);seq('recoil',1,1,32,classic)
  if classic:s+='\tmuzzle:\n\t\tFilename: gunfire2.shp\n\t\tLength: 2\n'
 else:
  facings=16 if air else 32;seq('idle',0,1,facings,classic and not air)
  if turret: seq('turret',facings,1,facings,classic and not air)
  if reload:seq('empty',32,1,32,classic);seq('empty-idle',32,1,32,classic)
  if kind=='ship':seq('sink',64,8,32,classic)
  if air:seq('rotor',32,4);seq('slow-rotor',32,4)
  s+='\tmuzzle:\n\t\tFilename: gunfire2.shp\n\t\tLength: 2\n\tair-muzzle:\n\t\tFilename: redsea-air-muzzle.shp\n\t\tLength: 6\n\t\tFacings: 8\n'
 s+=f'\ticon:\n\t\tFilename: {icon}\n'
 if not classic:s+='\t\tOffset: 0, 0\n'
 if actor=='r2ilrecon' and not classic:s+='\tstrike:\n\t\tFilename: ra2|modern-factions/icons/r2ilfalcon.png\n\t\tOffset: 0, 0\n'
 return s

def native_normals():
 source=(ROOT/'RTSAI-Mod/engine/OpenRA.Mods.Cnc/Traits/World/VoxelNormalsPalette.cs').read_text(encoding='utf-8')
 raw=source.split('float[] RA2Normals =',1)[1].split('];',1)[0]
 values=[float(x) for x in re.findall(r'(-?\d+\.\d+)f',raw)]
 return list(zip(values[::3],values[1::3],values[2::3]))

def build(faction, units):
 pal=palette(faction); art._PALETTE=pal; art.color_index.cache_clear()
 blob=bytes(v//4 for rgb in pal for v in rgb)
 owned=PACK/f'{faction}-art'; (RA/'bits/levant').mkdir(parents=True,exist_ok=True)
 (owned/f'{faction}.pal').write_bytes(blob);(owned/f'{faction}-voxels.pal').write_bytes(blob);(RA/f'bits/levant/{faction}.pal').write_bytes(blob)
 unitseq='';classseq='';portraits={};modelpack={};normals=native_normals()
 team=tuple(pal[i] for i in (18,21,24,27))
 for idx,(source,actor,base,name,role,desc) in enumerate(units):
  old=actor[2:]; air=role in ('interceptor','strike-aircraft'); naval=idx in (range(10,13) if faction=='israel' else range(9,12)); defense=idx>=(13 if faction=='israel' else 12)
  if idx<4:
   c=COLORS[faction]; infantryrole=('rifle','atgm','jtac','commando') if faction=='israel' else ('rifle','rpg','spotter','ghost')
   style=infantry.InfantryStyle(infantryrole[idx],c['paint'],c['dark'],c['edge'],(157,117,83),(34,39,39),c['glass'],1.10 if faction=='israel' else .96,hood=idx==3 and faction=='hezbollah',scarf=faction=='hezbollah')
   frames=[]
   for action,length in [('stand',1),('stand',1),('run',6),('shoot',8),('prone',1),('prone',4),('transition',2),('transition',2),('prone-shoot',8)]:
    for facing in range(8):
     for phase in range(length):frames.append(infantry._frame(style,team,action,facing,phase,length))
   for variant in (0,1):frames.extend(infantry._frame(style,team,'idle',0,p,8,variant) for p in range(8))
   for variant,length in enumerate((8,8,8,12,18)):
    for facing in range(8):frames.extend(infantry._frame(style,team,'directional-die',facing,p,length,variant) for p in range(length))
   chute=frames[0].copy();draw=ImageDraw.Draw(chute);draw.arc((14,0,36,15),180,360,fill=(*c['edge'],255),width=2);draw.line((14,8,25,16,36,8),fill=(*c['dark'],255));frames.append(chute)
   assert len(frames)==713,len(frames)
   digest=save_ts(owned/f'{actor}.shp',frames);save_ts(RA/f'bits/levant/{old}.shp',frames)
   portrait=ImageOps.contain(frames[3].crop((12,0,39,31)),(140,166),Image.Resampling.NEAREST)
   unitseq+=sequences(actor,faction,'infantry');classseq+=sequences(actor,faction,'infantry',classic=True)
   REPORT['actors'][actor]={'format':'SHP','frames':len(frames),'canvas':[50,39],'sha256':digest}
   contact=Image.new('RGBA',(400,195),(20,28,27))
   for row,start in enumerate((0,16,64,128,280)):
    for col in range(8):contact.alpha_composite(frames[start+col*(1 if row in (0,3) else 6 if row==1 else 8)],(50*col,39*row))
   contact.save(owned/f'{actor}-animations.png')
  elif defense:
   hull=structure(faction,role);tur=structure(faction,role,True)
   frames=[art.render(hull,0,(96,96),20,(48,67),True)]+[art.render(tur,i*32,(96,96),20,(48,67),True) for i in range(32)]
   frames += [art.render(art.combine(hull,art.transform(tur,lambda x,y,z:(x,y,z*(i+1)/8))),640,(96,96),20,(48,67),True) for i in range(8)]
   damaged=art.render(hull,0,(96,96),20,(48,67),True)
   alpha=damaged.getchannel('A');damaged=ImageOps.colorize(ImageOps.grayscale(damaged),(20,25,25),COLORS[faction]['dark']).convert('RGBA');damaged.putalpha(alpha);frames.append(damaged)
   digest=save_ts(owned/f'{actor}.shp',frames);save_ts(RA/f'bits/levant/{old}.shp',frames)
   unitseq+=sequences(actor,faction,'structure');classseq+=sequences(actor,faction,'structure',classic=True)
   portrait=art.render(art.combine(hull,tur),640,(240,192),50,(120,153))
   REPORT['actors'][actor]={'format':'SHP','frames':len(frames),'canvas':[96,96],'sha256':digest}
  else:
   kind=('frigate' if role=='anti-submarine' else 'tender' if role=='support' else 'ship') if naval else role
   hull=body(faction,kind,actor); parts=[hull]; turret=not air and not(role=='support' and naval) and not (faction=='hezbollah' and actor in ('r2hzmissileboat','r2hzskiff'))
   if turret:parts.append(weapon(faction,role))
   if actor=='r2ilgunship':
    rotor=geometry.Mesh();rotor.box(-2.8,2.8,-.08,.08,1.56,1.60,(34,39,39));rotor.box(-.08,.08,-2.8,2.8,1.56,1.60,(34,39,39));parts.append(rotor)
   modelpack[actor]=parts
   portrait=art.render(art.combine(*parts),640,(240,192),32 if not naval else 22,(120,134))
   facings=16 if air else 32; angles=geometry._angles(facings,classic=not air)
   size=56 if air else 64 if naval else 40
   span=8.8 if naval else 7.4 if air else 6.3
   classic_hull=art.combine(hull,weapon(faction,role)) if actor=='r2ilhowitzer' else hull
   classicframes=[geometry._render(classic_hull,a,size,shadow=True,model_span=span,flat_colors=frozenset([TEAM])) for a in angles]
   if turret:classicframes += [geometry._render(parts[1],a,size,shadow=False,model_span=span,flat_colors=frozenset([TEAM])) for a in angles]
   if actor=='r2hzrockets':
    # Artillery is a single voxel body with loaded/empty geometry, not a turret trait.
    modelpack[actor]=[art.combine(hull,weapon(faction,role))]
    modelpack[actor+'empty']=[art.combine(hull,weapon(faction,role,loaded=False))]
    classicframes=[geometry._render(modelpack[actor][0],a,size,shadow=True,model_span=span,flat_colors=frozenset([TEAM])) for a in angles]+[geometry._render(modelpack[actor+'empty'][0],a,size,shadow=True,model_span=span,flat_colors=frozenset([TEAM])) for a in angles]
   if actor=='r2ilhowitzer':modelpack[actor]=[art.combine(hull,weapon(faction,role))]
   if naval:
    if len(classicframes)==32:classicframes+= [Image.new('RGBA',(size,size)) for _ in range(32)]
    for i in range(32):
     for t in range(8):
      frame=classicframes[i].copy();frame.putalpha(frame.getchannel('A').point(lambda v:v*(7-t)//8));classicframes.append(frame)
   if air:
    while len(classicframes)<32:classicframes.append(Image.new('RGBA',(size,size)))
    classicframes += [geometry._render(parts[-1] if len(parts)>1 else geometry.Mesh(),-i*45,size,shadow=False,model_span=span) for i in range(4)]
   save_ts(RA/f'bits/levant/{old}.shp',classicframes)
   classseq+=sequences(actor,faction,'ship' if naval else 'vehicle',classic=True,turret=turret,air=air,reload=actor=='r2hzrockets')
   if actor in ('r2hzmissileboat','r2hzsurvey') and not turret:classseq+='\tturret:\n\t\tStart: 0\n\t\tFacings: 32\n\t\tUseClassicFacings: True\n'
  portraits[actor]=portrait
  cameo=Image.new('RGBA',(240,192),(21,30,35));cameo.alpha_composite(portrait,((240-portrait.width)//2,(192-portrait.height)//2))
  cameo.convert('RGB').resize((60,48),Image.Resampling.LANCZOS).save(PACK/f'icons/{actor}.png')
  # Indexed production icons have their own authored palette, never EA bytes.
  icon=cameo.resize((64,48),Image.Resampling.LANCZOS);draw=ImageDraw.Draw(icon);draw.rectangle((0,0,63,47),outline=(139,148,130));draw.rectangle((1,38,62,46),fill=(17,23,23));draw.text((3,38),name.split()[0][:10].upper(),font=ImageFont.truetype(str(FONT),7),fill=(226,230,212));save_ts(RA/f'bits/levant/{old}icon.shp',[icon])
 for suffix in ('relay','workshop'):
  actor=('r2il' if faction=='israel' else 'r2hz')+suffix;old=actor[2:];mesh=structure(faction,suffix)
  frames=[art.render(mesh,0,(96,96),20,(48,67),True)]
  frames+=[Image.new('RGBA',(96,96)) for _ in range(32)]
  frames += [art.render(art.transform(mesh,lambda x,y,z:(x,y,z*(i+1)/8)),640,(96,96),20,(48,67),True) for i in range(8)]
  damaged=art.render(mesh,0,(96,96),20,(48,67),True);damaged=ImageOps.colorize(ImageOps.grayscale(damaged),(20,25,25),COLORS[faction]['dark']).convert('RGBA');damaged.putalpha(frames[0].getchannel('A'));frames.append(damaged)
  digest=save_ts(owned/f'{actor}.shp',frames);save_ts(RA/f'bits/levant/{old}.shp',frames)
  unitseq+=sequences(actor,faction,'structure',turret=False);classseq+=sequences(actor,faction,'structure',classic=True,turret=False)
  portrait=art.render(mesh,640,(240,192),47,(120,153));portraits[actor]=portrait
  cameo=Image.new('RGBA',(240,192),(21,30,35));cameo.alpha_composite(portrait);cameo.convert('RGB').resize((60,48),Image.Resampling.LANCZOS).save(PACK/f'icons/{actor}.png');save_ts(RA/f'bits/levant/{old}icon.shp',[cameo.resize((64,48),Image.Resampling.LANCZOS)])
  REPORT['actors'][actor]={'format':'SHP','frames':len(frames),'canvas':[96,96],'sha256':digest}
 # Native VXL palette indexes are sampled from the same handcrafted material ramps.
 materialindexes={color:art.color_index(*color) for parts in modelpack.values() for mesh in parts for face in mesh.faces for color in [face.color]};materialindexes[TEAM]=23
 for actor,parts in modelpack.items():
  for idx,mesh in enumerate(parts):
   name=actor+('tur' if idx else '')
   size,lower,voxels=vxl.voxelize(mesh,materialindexes,normals);data=vxl.encode_vxl(size,lower,voxels,blob);(PACK/f'voxels/{name}.vxl').write_bytes(data)
   matrices=[vxl.IDENTITY]
   if actor=='r2ilgunship' and idx==1:
    matrices=[]
    for i in range(8):
     a=i*math.pi/16;c,s=math.cos(a),math.sin(a);matrices.append((c,-s,0.,0.,s,c,0.,0.,0.,0.,1.,0.))
   hva=bytes(16)+struct.pack('<2I',len(matrices),1)+b'body'.ljust(16,b'\0')+b''.join(struct.pack('<12f',*m) for m in matrices);(PACK/f'voxels/{name}.hva').write_bytes(hva)
   REPORT['actors'][name]={'format':'VXL/HVA','size':size,'origin':lower,'occupiedVoxels':len(voxels),'remapVoxels':sum(16<=p[0]<=31 for p in voxels.values()),'sha256':hashlib.sha256(data).hexdigest()}
 # Keep only owned RA2 sprite definitions; voxel body icons remain in separate sequence file.
 write(PACK/f'{faction}-roster-sequences.yaml',unitseq)
 write(RA/f'sequences/{faction}.yaml',classseq)
 # Bind custom palette/animation to Classic actors independently of native stock palettes.
 rules=DEFINITIONS['read'](RA/f'rules/{faction}.yaml')
 for _,actor,*_ in units:
  key=actor[2:].upper();rules=rules.replace(f'{key}:\n',f'{key}:\n\tRenderSprites:\n\t\tPlayerPalette: {faction}player\n',1)
  if actor in portraits and actor in [u[1] for u in units[:4]]:
   rules=rules.replace(f'{key}:\n',f'{key}:\n\tWithDeathAnimation:\n\t\tDeathSequencePalette: {faction}player\n\t\tDeathPaletteIsPlayerPalette: true\n',1)
 for suffix in ('RELAY','WORKSHOP'):
  key=('IL' if faction=='israel' else 'HZ')+suffix;rules=rules.replace(f'{key}:\n',f'{key}:\n\tRenderSprites:\n\t\tPlayerPalette: {faction}player\n',1)
 write(RA/f'rules/{faction}.yaml',DEFINITIONS['normalized'](rules))
 columns=5;sheet=Image.new('RGB',(1000,100+math.ceil(len(portraits)/columns)*190),(16,24,24));d=ImageDraw.Draw(sheet)
 source_media=ROOT/'RTSAI-Art/rebuild/levant-media';source_media.mkdir(parents=True,exist_ok=True)
 for actor,picture in portraits.items():
  view=Image.new('RGBA',(240,192),(21,30,35));view.alpha_composite(picture,((240-picture.width)//2,(192-picture.height)//2));view.convert('RGB').save(source_media/f'{actor}.png')
 d.text((20,18),f'{faction.upper()} / FICTIONAL RTS ROSTER',font=ImageFont.truetype(str(FONT),24),fill=(233,239,225));d.text((20,53),'MEASURED: AUTHORED SOURCE RENDERS  |  IN-GAME ART APPROVAL PENDING',font=ImageFont.truetype(str(FONT),13),fill=(159,177,163))
 names={u[1]:u[3] for u in units}
 for i,(actor,picture) in enumerate(portraits.items()):
  x=(i%columns)*200;y=100+(i//columns)*190;tile=ImageOps.contain(picture,(190,150),Image.Resampling.LANCZOS);sheet.paste(tile,(x+(200-tile.width)//2,y),tile);d.text((x+9,y+157),names.get(actor,'Coordination Relay' if actor.endswith('relay') and faction=='israel' else 'Signal Post' if actor.endswith('relay') else 'Field Service Station' if faction=='israel' else 'Field Workshop'),font=ImageFont.truetype(str(FONT),12),fill=(220,228,209))
 sheet.save(owned/'source-art-review.png');(RA/'uibits/faction-previews').mkdir(exist_ok=True);sheet.resize((512,512),Image.Resampling.LANCZOS).save(RA/f'uibits/faction-previews/{faction}.png');(PACK/'previews').mkdir(exist_ok=True);sheet.resize((512,512),Image.Resampling.LANCZOS).save(PACK/f'previews/{faction}.png')
 print(f'{faction}: {len(portraits)} authored actors',flush=True)

def main():
 for faction,(_,units,*_) in units_by_faction.items():build(faction,units)
 write(PACK/'levant-art-provenance.json',json.dumps(REPORT,indent=2))
 common=DEFINITIONS['read'](RA/'rules/levant-common.yaml')
 common+='\n^Palettes:\n'
 for faction in units_by_faction:
  common+=f'\tPaletteFromFile@{faction}:\n\t\tName: {faction}-art\n\t\tFilename: ra|bits/levant/{faction}.pal\n\tPlayerColorPalette@{faction}:\n\t\tBasePalette: {faction}-art\n\t\tBaseName: {faction}player\n\t\tRemapIndex: '+', '.join(str(i) for i in range(16,32))+'\n'
 write(RA/'rules/levant-common.yaml',DEFINITIONS['normalized'](common))

if __name__=='__main__':main()
