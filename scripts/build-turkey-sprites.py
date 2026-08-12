"""Generate all Turkey faction sprite frames deterministically."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from red_sea_directional_vehicle import render_air_impact_frames, render_air_muzzle_frames
from turkey_directional_assets import render_air, render_ground, render_rotor, render_ship, render_spinner


ROOT = Path(__file__).resolve().parents[1]
FRAME_ROOT = ROOT / "generated" / "turkey-sprites"
FONT = ROOT / "engine" / "openra" / "mods" / "common" / "FreeSansBold.ttf"

_red_sea_spec = importlib.util.spec_from_file_location("red_sea_sprite_builder", ROOT / "scripts" / "build-red-sea-sprites.py")
if _red_sea_spec is None or _red_sea_spec.loader is None:
	raise RuntimeError("unable to load Red Sea sprite utilities")
_red_sea = importlib.util.module_from_spec(_red_sea_spec)
_red_sea_spec.loader.exec_module(_red_sea)
quantize_icon_to_reference = _red_sea.quantize_icon_to_reference
quantize_to_reference = _red_sea.quantize_to_reference
wreck_frame = _red_sea.wreck_frame

LIVE = {
	"bozkir": ("ground", 44), "aras8": ("ground", 42), "yildirim": ("ground", 46),
	"gokkalkan": ("ground", 44), "sancak": ("ground", 44), "denizkaplan": ("ground", 44),
	"kuzgunm": ("air", 56), "turnaah": ("air", 60), "sahinx": ("air", 64),
	"marmara": ("ship", 64), "ege": ("ship", 56), "poyraz": ("ship", 48),
}

INFANTRY = {
	"trrifle": ("RIFLEMAN", (91, 105, 67)),
	"trat": ("AT SPECIALIST", (82, 94, 61)),
	"trdroneop": ("DRONE OPERATOR", (74, 96, 72)),
	"greywolf": ("GREY WOLF", (43, 49, 44)),
}

LABELS = {
	"bozkir": "BOZKIR", "aras8": "ARAS-8", "yildirim": "YILDIRIM",
	"gokkalkan": "GOKKALKAN", "sancak": "SANCAK", "denizkaplan": "DENIZ KAPLAN",
	"kuzgunm": "KUZGUN-M", "turnaah": "TURNA-AH", "sahinx": "SAHIN-X",
	"marmara": "MARMARA", "ege": "EGE", "poyraz": "POYRAZ",
}


def clear(name: str) -> Path:
	output = FRAME_ROOT / name
	output.mkdir(parents=True, exist_ok=True)
	for path in output.glob(f"{name}-[0-9][0-9][0-9][0-9].png"):
		path.unlink()
	return output


def save(name: str, frames: list[Image.Image], palette: Image.Image) -> None:
	output = clear(name)
	for index, frame in enumerate(frames):
		quantize_to_reference(frame, palette).save(output / f"{name}-{index:04d}.png", transparency=0)
	cols = min(8, len(frames))
	rows = math.ceil(len(frames) / cols)
	size = frames[0].size[0]
	sheet = Image.new("RGBA", (cols * size, rows * size), (35, 39, 35, 255))
	for index, frame in enumerate(frames):
		sheet.alpha_composite(frame, ((index % cols) * size, (index // cols) * size))
	sheet.save(FRAME_ROOT / f"{name}-contact-sheet.png")
	print(f"{name}: {len(frames)} authored frames; {len({hashlib.sha256(f.tobytes()).hexdigest() for f in frames})} unique")


def live_frames(name: str) -> list[Image.Image]:
	kind, size = LIVE[name]
	if kind == "ground":
		frames = render_ground(name, size)
		return frames
	if kind == "air":
		return render_air(name, size)
	return render_ship(name, size)


def corpse_frames(name: str, live: list[Image.Image]) -> list[Image.Image]:
	kind, _ = LIVE[name]
	if kind == "ground":
		count = 64
		return [wreck_frame(frame, index % 32, turret=index >= 32) for index, frame in enumerate(live[:count])]
	count = 32 if name == "turnaah" else 16
	return [wreck_frame(frame, index, turret=False) for index, frame in enumerate(live[:count])]


def infantry_pose(role: str, facing: int, phase: float, action: str, color: tuple[int, int, int], size: int = 24) -> Image.Image:
	# Draw every facing directly from orientation vectors; no rotated raster master.
	scale = 4
	canvas = Image.new("RGBA", (size*scale, size*scale), (0,0,0,0))
	draw = ImageDraw.Draw(canvas)
	cx, cy = size*2, size*2+8
	a = facing * math.tau / 8 - math.pi/2
	dx, dy = math.cos(a), math.sin(a) * .48
	sx, sy = -math.sin(a), math.cos(a) * .48
	prone = action.startswith("prone") or action in {"liedown", "standup"}
	bob = 0 if prone else math.sin(phase * math.tau) * 2.2
	if action.startswith("die"):
		progress = phase
		cx += progress * 9
		cy += progress * 7
		prone = progress > .42
	shadow_w = 23 if prone else 14
	draw.ellipse((cx-shadow_w, cy+18, cx+shadow_w, cy+27), fill=(0,0,0,75))
	if prone:
		body_end = (cx-dx*21, cy-dy*21)
		draw.line((cx,cy,body_end[0],body_end[1]), fill=(*color,255), width=12)
		head = (cx+dx*8, cy+dy*8-4)
	else:
		leg_swing = math.sin(phase*math.tau) * (8 if action == "run" else 2)
		for side in (-1,1):
			hip=(cx+sx*side*4,cy+9+bob)
			foot=(cx+sx*side*(5+leg_swing*side*.25)-dx*leg_swing,cy+25)
			draw.line((hip[0],hip[1],foot[0],foot[1]),fill=(32,38,33,255),width=6)
		draw.rounded_rectangle((cx-9,cy-10+bob,cx+9,cy+11+bob),3,fill=(*color,255),outline=(25,31,26,255),width=2)
		head=(cx+dx*3,cy-18+bob+dy*3)
		draw.ellipse((head[0]-7,head[1]-7,head[0]+7,head[1]+7),fill=(58,66,51,255),outline=(22,27,23,255),width=2)
		draw.line((head[0]-sx*5,head[1]+1,head[0]+sx*5,head[1]+1),fill=(32,48,47,255),width=3)
	# Distinct equipment and role silhouettes.
	weapon_len = 25 if role != "trat" else 31
	if action in {"shoot", "prone-shoot"}:
		weapon_len += math.sin(phase*math.pi) * 3
	root=(cx+dx*3-sx*3,cy-2 if prone else cy-4+bob)
	tip=(root[0]+dx*weapon_len,root[1]+dy*weapon_len)
	draw.line((root[0],root[1],tip[0],tip[1]),fill=(31,34,32,255),width=5 if role != "trat" else 9)
	if role == "trat":
		draw.ellipse((tip[0]-5,tip[1]-5,tip[0]+5,tip[1]+5),fill=(69,76,57,255))
	elif role == "trdroneop":
		draw.rectangle((cx-12,cy+2,cx+12,cy+10),fill=(35,47,45,255),outline=(120,146,110,255),width=2)
		draw.line((cx+9,cy+2,cx+14,cy-16),fill=(52,55,52,255),width=2)
	elif role == "greywolf":
		draw.polygon(((head[0]-8,head[1]-4),(head[0],head[1]-13),(head[0]+8,head[1]-4)),fill=(34,39,35,255))
		draw.line((cx-8,cy-3,cx+8,cy+10),fill=(168,43,43,255),width=2)
	else:
		draw.rectangle((cx-11,cy-6,cx-6,cy+7),fill=(49,58,40,255))
	if action == "shoot" and int(phase*8) in (1,2):
		draw.ellipse((tip[0]-3,tip[1]-3,tip[0]+5,tip[1]+5),fill=(255,198,76,230))
	return canvas.resize((size,size),Image.Resampling.LANCZOS)


def build_infantry(role: str, color: tuple[int,int,int]) -> list[Image.Image]:
	frames=[]
	# Facing-major native layout through frame 255.
	for facing in range(8): frames.append(infantry_pose(role,facing,0,"stand",color))
	for facing in range(8): frames.append(infantry_pose(role,facing,.35,"stand",color))
	for facing in range(8):
		for phase in range(6): frames.append(infantry_pose(role,facing,phase/6,"run",color))
	for facing in range(8):
		for phase in range(8): frames.append(infantry_pose(role,facing,phase/8,"shoot",color))
	for facing in range(8):
		for phase in range(2): frames.append(infantry_pose(role,facing,phase,"liedown",color))
	for facing in range(8):
		for phase in range(4): frames.append(infantry_pose(role,facing,phase/4,"prone-run",color))
	for facing in range(8):
		for phase in range(2): frames.append(infantry_pose(role,facing,1-phase,"standup",color))
	for facing in range(8):
		for phase in range(8): frames.append(infantry_pose(role,facing,phase/8,"prone-shoot",color))
	# Two full idle animations.
	for phase in range(16): frames.append(infantry_pose(role,4,phase/16,"stand",color))
	for phase in range(16): frames.append(infantry_pose(role,4,(phase+5)/16,"stand",color))
	for length, variant in ((8,0),(8,1),(8,2),(12,3),(18,4)):
		for phase in range(length): frames.append(infantry_pose(role,(variant*2)%8,phase/max(1,length-1),"die",color))
	# Native soldier layout reserves 35 unused frames before parachute frame 377.
	while len(frames) < 377:
		phase=(len(frames)-342)/35
		frames.append(infantry_pose(role,4,phase,"stand",color))
	frames.append(infantry_pose(role,4,0,"stand",color))
	assert len(frames)==378
	return frames


def icon_frame(name: str, art: Image.Image, label: str) -> Image.Image:
	background=Image.new("RGBA",(64,48),(25,31,29,255))
	for y in range(48):
		ImageDraw.Draw(background).line((0,y,63,y),fill=(25+y//4,31+y//5,29+y//6,255))
	copy=art.copy()
	bbox=copy.getchannel("A").getbbox()
	if bbox:
		copy=copy.crop(bbox)
		ratio=min(58/copy.width,35/copy.height)
		copy=copy.resize((max(1,round(copy.width*ratio)),max(1,round(copy.height*ratio))),Image.Resampling.LANCZOS)
		background.alpha_composite(copy,((64-copy.width)//2,1+(34-copy.height)//2))
	shade=Image.new("RGBA",(64,14),(0,0,0,180)); background.alpha_composite(shade,(0,34))
	font_size=9
	while font_size>6:
		font=ImageFont.truetype(FONT,font_size)
		box=ImageDraw.Draw(background).textbbox((0,0),label,font=font,stroke_width=1)
		if box[2]-box[0] <= 60: break
		font_size-=1
	draw=ImageDraw.Draw(background); box=draw.textbbox((0,0),label,font=font,stroke_width=1)
	draw.text(((64-(box[2]-box[0]))//2,36),label,font=font,fill=(245,245,235),stroke_width=1,stroke_fill=(10,10,10))
	return background


def save_icon(name: str, art: Image.Image, label: str, palette: Image.Image) -> None:
	icon=icon_frame(name,art,label)
	output=clear(name+"icon")
	quantize_icon_to_reference(icon,palette).save(output/f"{name}icon-0000.png")
	icon.save(FRAME_ROOT/f"{name}icon-review.png")


def explosion_frames(size: int, count: int, tint: tuple[int,int,int]) -> list[Image.Image]:
	frames=[]
	for phase in range(count):
		progress=phase/max(1,count-1); canvas=Image.new("RGBA",(size*3,size*3),(0,0,0,0)); draw=ImageDraw.Draw(canvas); c=size*1.5
		r=(4+size*.33*math.sin(progress*math.pi*.88))*3; alpha=round(255*(1-progress*.84))
		draw.ellipse((c-r,c-r*.70,c+r,c+r*.70),fill=(*tint,max(12,alpha//2)))
		fire=r*(.72-progress*.33); draw.ellipse((c-fire,c-fire,c+fire,c+fire),fill=(247,94+phase*7,28,alpha))
		core=max(2,fire*.4); draw.ellipse((c-core,c-core,c+core,c+core),fill=(255,231,137,max(15,alpha-20)))
		if phase>2:
			smoke=r*.45; draw.ellipse((c-smoke,c-phase*3-smoke,c+smoke,c-phase*3+smoke),fill=(48,53,50,max(8,alpha//2)))
		frames.append(canvas.filter(ImageFilter.GaussianBlur(1.0)).resize((size,size),Image.Resampling.LANCZOS))
	return frames


def designator_frames(size: int=32) -> list[Image.Image]:
	frames=[]
	for phase in range(8):
		canvas=Image.new("RGBA",(size,size),(0,0,0,0)); draw=ImageDraw.Draw(canvas); c=size//2; r=5+phase
		draw.ellipse((c-r,c-r,c+r,c+r),outline=(90,255,168,240-phase*18),width=2)
		for a in range(0,360,90):
			dx,dy=math.cos(math.radians(a)),math.sin(math.radians(a)); draw.line((c+dx*(r+2),c+dy*(r+2),c+dx*(r+6),c+dy*(r+6)),fill=(215,255,226,220-phase*15),width=1)
		frames.append(canvas)
	return frames


def wake_frames(size: int=32) -> list[Image.Image]:
	frames=[]
	for phase in range(8):
		canvas=Image.new("RGBA",(size,size),(0,0,0,0)); draw=ImageDraw.Draw(canvas); alpha=210-phase*20
		for side in (-1,1):
			draw.arc((size*.15,size*.35+phase*.5,size*.85,size*.72+phase),200 if side<0 else 160,340 if side<0 else 20,fill=(210,231,229,alpha),width=2)
		frames.append(canvas)
	return frames


def sink_frames(name: str, bodies: list[Image.Image]) -> list[Image.Image]:
	frames=[]
	for facing, body in enumerate(bodies[:16]):
		for phase in range(6):
			progress=phase/5; damaged=wreck_frame(body,facing,turret=False); damaged=ImageEnhance.Brightness(damaged).enhance(1-progress*.55)
			canvas=Image.new("RGBA",body.size,(0,0,0,0)); y=round(progress*body.height*.32); canvas.alpha_composite(damaged,(0,y))
			mask=Image.new("L",body.size,255); ImageDraw.Draw(mask).rectangle((0,round(body.height*(.82-progress*.28)),body.width,body.height),fill=0); canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"),mask))
			frames.append(canvas)
	return frames


def main() -> int:
	parser=argparse.ArgumentParser(); parser.add_argument("--palette",type=Path,required=True); args=parser.parse_args()
	palette=Image.open(args.palette)
	if palette.mode!="P": raise ValueError("palette reference must be indexed")
	FRAME_ROOT.mkdir(parents=True,exist_ok=True)
	cache={}
	for name in LIVE:
		frames=live_frames(name); cache[name]=frames; save(name,frames,palette)
		kind,_=LIVE[name]
		if kind in {"ground","air"}:
			husk_name=name+"husk"; save(husk_name,corpse_frames(name,frames),palette)
		else:
			save(name+"sink",sink_frames(name,frames),palette)
		save_icon(name,frames[0],LABELS[name],palette)
	for role,(label,color) in INFANTRY.items():
		frames=build_infantry(role,color); save(role,frames,palette); save_icon(role,frames[0],label,palette)
	save("turnaahrotor",render_rotor(60),palette)
	save("turkey-ground-muzzle",render_air_muzzle_frames(48),palette)
	save("turkey-air-muzzle",render_air_muzzle_frames(48),palette)
	save("turkey-designator",designator_frames(),palette)
	save("turkey-wake",wake_frames(),palette)
	for name,size,count,tint in (("turkey-at-impact",48,9,(95,86,62)),("turkey-heavy-impact",64,11,(95,78,54)),("turkey-artillery-impact",64,12,(104,91,71)),("turkey-air-impact",56,9,(80,88,86)),("turkey-naval-impact",64,11,(77,100,105))):
		save(name,explosion_frames(size,count,tint),palette)
	return 0


if __name__=="__main__":
	raise SystemExit(main())
