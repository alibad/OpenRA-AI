"""Build the United States (`usa`) Checkpoint B concept and silhouette boards.

Roadmap gate 2 ("Concept and silhouette review") in
``OpenRA/docs/modern-faction-roadmap.md`` requires one review board showing
every U.S. roster actor at approximately in-game scale on the snow, temperate
and desert palettes, with intentional player-colour regions, a silhouette
check, and the two comparisons mandated by ``faction-spec-usa.md`` §8.1/§8.3.

Everything U.S. on the boards is rendered by ``usa_concept_actors`` from
original project geometry and quantized into indexed Red Alert sprites before
it is drawn, so what the reviewer sees is what a shipping SHP frame would
contain.  Reference art is handled in two ways:

* Project-generated modern-faction art (``M1A2S``, ``ARAS8`` and the other
  overlap-matrix neighbours in ``mods/ra/bits``) is shown in full colour.
* Westwood-derived art (stock Red Alert content and the upstream sprites that
  edit it) is shown only as a flat "scale ghost" or a black silhouette, so the
  committed boards do not redistribute that artwork.

Terrain backgrounds are synthesized from each theatre's clear-ground index
histogram and drawn through that theatre's terrain palette; no terrain tile is
copied onto the board.  Units always use the temperate "player" palette, as in
the running game.

Usage::

    python scripts/build-usa-concept-board.py \
        --engine <OpenRA checkout with bin/OpenRA.Utility.exe> \
        --support-dir <directory containing Content/ra/v2> \
        --output <engine>/docs/concept/usa
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
	sys.path.insert(0, str(SCRIPT_ROOT))

import usa_concept_actors as actors  # noqa: E402
import usa_concept_models as models  # noqa: E402
import usa_concept_render as board_render  # noqa: E402
from usa_concept_render import PlayerColor  # noqa: E402


BOARD_VERSION = "usa-concept-board/1"

PLAYER_A = PlayerColor("blue", "2F86F2")
PLAYER_B = PlayerColor("red", "F50606")
ZONE_COLORS = (PLAYER_A, PLAYER_B, PlayerColor("green", "06F739"), PlayerColor("gold", "F2BC18"), PlayerColor("maroon", "391D1D"))

THEATRES = (
	("SNOW", "snow", "sno"),
	("TEMPERATE", "temperat", "tem"),
	("DESERT", "desert", "des"),
)

INK = (238, 234, 222, 255)
INK_DIM = (176, 172, 160, 255)
PANEL = (30, 33, 34, 255)
PANEL_LIGHT = (44, 48, 50, 255)
SILHOUETTE_BG = (206, 204, 196, 255)
GHOST_FILL = (182, 188, 196, 150)
GHOST_EDGE = (236, 240, 244, 230)
FLAT_GROUND = (60, 76, 52, 255)
FLAT_WATER = (84, 112, 150, 255)

# Stock Red Alert (content) sprites used only as scale ghosts / silhouettes.
STOCK_REFERENCES = ("e1", "e3", "e7", "spy", "2tnk", "3tnk", "apc", "arty", "v2rl", "mig", "u2", "tran", "badr",
					"dd", "ca", "ss", "msub", "lst", "dome", "sam", "agun")
# Upstream sprites in mods/ra/bits that edit Westwood art: ghost/silhouette only.
UPSTREAM_BITS = ("heli", "yak", "ftrk", "gap", "mgg", "mh60")

# Role-paired native reference for each domain on the boards.
DOMAIN_REFERENCE = {
	"infantry": ("E1", "e1", "infantry"),
	"vehicle": ("2TNK", "2tnk", "vehicle"),
	"aircraft": ("MIG", "mig", "plane"),
	"helicopter": ("TRAN", "tran", "heli"),
	"ship": ("DD", "dd", "ship"),
	"structure": ("DOME", "dome", "structure"),
}

# Overlap-matrix neighbours from faction-spec-usa.md §7.1 and §7.2, plus the
# upstream MH60 Black Hawk that the matrix does not list (see README).
NEIGHBOURS = {
	"USRIFLE": ("E1", "CNRIFLE", "IRBAS", "TRRIFLE", "SANG", "YMR"),
	"USJAV": ("E3", "IRATGM", "TRAT", "SAAT", "YRPG", "CNPORTABLE"),
	"USJTAC": ("SPY", "MGG", "SAJTAC", "YSPOT", "TRDRONEOP", "IRDC", "CNNETWORK"),
	"TALONSIX": ("E7", "REDSPEAR", "SHADOWONE", "FALCON1", "WADIGHOST", "GREYWOLF"),
	"USMBT": ("3TNK", "M1A2S", "BOZKIR", "CNQILIN", "IRKARR"),
	"USIFV": ("APC", "CNZBD", "DENIZKAPLAN"),
	"USICV": ("APC", "ARAS8"),
	"USHIMARS": ("ARTY", "V2RL", "CNPHL", "YMLR", "IRFAJR"),
	"USSHORAD": ("FTRK", "GOKKALKAN", "SADS", "CNMANTIS", "IRRAAD"),
	"USRECOV": (),
	"USF35": ("MIG", "YAK", "SAHINX", "F15SA", "CNSKYSPEAR", "IRAZAR", "KUZGUNM"),
	"USMQ9": ("U2", "IRMOHAJER", "IRLOITER", "CNCLOUD", "KUZGUNM", "SAMAD"),
	"USUH60": ("TRAN", "HELI", "MH60", "AH64SA", "TURNAAH", "IRTOUFAN", "CNCRANE"),
	"USAC130": ("BADR",),
	"USDDG": ("DD", "CA", "SA_FRGT", "MARMARA", "CNLUYANG"),
	"USSSN": ("SS", "MSUB", "IRGHADIR", "CNJIAOLONG"),
	"USLPD": ("LST", "SA_FSS", "CNKUNLUN"),
	"USTOC": ("DOME", "CNSPECTRUM"),
	"USIAMD": ("SAM", "AGUN", "CNSKYSHIELD"),
	"USCUAS": ("AGUN", "CNBASTION"),
	"USNODE": ("GAP", "CNSPECTRUM"),
}

# Sprite layout of every neighbour: file stem, kind, optional turret/overlay stem.
NEIGHBOUR_SPRITES = {
	"E1": ("e1", "infantry", None), "E3": ("e3", "infantry", None), "E7": ("e7", "infantry", None),
	"SPY": ("spy", "infantry", None), "MGG": ("mgg", "vehicle", None),
	"2TNK": ("2tnk", "vehicle", "self"), "3TNK": ("3tnk", "vehicle", "self"), "APC": ("apc", "vehicle", None), "ARTY": ("arty", "vehicle", None),
	"V2RL": ("v2rl", "vehicle", None), "FTRK": ("ftrk", "vehicle", "self"),
	"MIG": ("mig", "plane", None), "YAK": ("yak", "plane", None), "U2": ("u2", "plane", None),
	"BADR": ("badr", "plane", None), "TRAN": ("tran", "heli", None), "HELI": ("heli", "heli", None),
	"MH60": ("mh60", "heli", None),
	"DD": ("dd", "ship", None), "CA": ("ca", "ship", None), "SS": ("ss", "ship", None),
	"MSUB": ("msub", "ship", None), "LST": ("lst", "structure", None),
	"DOME": ("dome", "structure", None), "SAM": ("sam", "structure", None), "AGUN": ("agun", "structure", None),
	"GAP": ("gap", "structure", None),
}
for _name in ("CNRIFLE", "IRBAS", "TRRIFLE", "SANG", "YMR", "IRATGM", "TRAT", "SAAT", "YRPG", "CNPORTABLE", "SAJTAC",
			  "YSPOT", "TRDRONEOP", "IRDC", "CNNETWORK", "REDSPEAR", "SHADOWONE", "FALCON1", "WADIGHOST", "GREYWOLF"):
	NEIGHBOUR_SPRITES[_name] = (_name.lower(), "infantry", None)
for _name in ("M1A2S", "BOZKIR", "CNQILIN", "IRKARR", "CNZBD", "DENIZKAPLAN", "ARAS8", "CNPHL", "YMLR", "IRFAJR",
			  "GOKKALKAN", "SADS", "CNMANTIS", "IRRAAD"):
	NEIGHBOUR_SPRITES[_name] = (_name.lower(), "vehicle", "self")
for _name in ("SAHINX", "F15SA", "CNSKYSPEAR", "IRAZAR", "KUZGUNM", "IRMOHAJER", "IRLOITER", "CNCLOUD", "SAMAD"):
	NEIGHBOUR_SPRITES[_name] = (_name.lower(), "plane", None)
for _name in ("AH64SA", "TURNAAH", "IRTOUFAN", "CNCRANE"):
	NEIGHBOUR_SPRITES[_name] = (_name.lower(), "heli", None)
NEIGHBOUR_SPRITES.update({
	"SA_FRGT": ("sa_frgt", "ship", "sa_frgt_turret"), "MARMARA": ("marmara", "ship", None),
	"CNLUYANG": ("cnluyang", "ship", "cnluyangturret"), "IRGHADIR": ("irghadir", "ship", None),
	"CNJIAOLONG": ("cnjiaolong", "ship", None), "SA_FSS": ("sa_fss", "ship", None),
	"CNKUNLUN": ("cnkunlun", "ship", "cnkunlunturret"),
	"CNSPECTRUM": ("cnspectrum", "structure", "cnspectrumtop"), "CNSKYSHIELD": ("cnskyshield", "structure", "cnskyshieldtop"),
	"CNBASTION": ("cnbastion", "structure", "cnbastiontop"),
})


# ---------------------------------------------------------------------------
# OpenRA.Utility access
# ---------------------------------------------------------------------------


@dataclass
class Toolchain:
	engine: Path
	support: Path
	work: Path

	@property
	def utility(self) -> Path:
		for name in ("OpenRA.Utility.exe", "OpenRA.Utility"):
			candidate = self.engine / "bin" / name
			if candidate.is_file():
				return candidate
		raise FileNotFoundError(f"OpenRA.Utility was not found under {self.engine / 'bin'}; build the engine first")

	def run(self, cwd: Path, *args: str) -> None:
		env = os.environ.copy()
		env["ENGINE_DIR"] = str(self.engine)
		env["SUPPORT_DIR"] = str(self.support) + os.sep
		env.setdefault("DOTNET_ROLL_FORWARD", "Major")
		cwd.mkdir(parents=True, exist_ok=True)
		result = subprocess.run([str(self.utility), "ra", *args], cwd=cwd, env=env, text=True, capture_output=True)
		if result.returncode:
			raise RuntimeError(f"OpenRA.Utility {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")

	def content_file(self, name: str) -> Path:
		target = self.work / "content" / name
		if not target.is_file():
			self.run(target.parent, "--extract", name)
		if not target.is_file():
			raise FileNotFoundError(f"{name} could not be extracted from the Red Alert content")
		return target

	def frames(self, source: Path, palette: Path, key: str) -> list[Image.Image]:
		out = self.work / "frames" / key
		if not any(out.glob("*.png")):
			self.run(out, "--png", str(source), str(palette))
		paths = sorted(out.glob("*.png"))
		if not paths:
			raise RuntimeError(f"no frames produced for {source}")
		return [Image.open(path).copy() for path in paths]


def sha256(path: Path) -> str:
	return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha256(path: Path) -> str:
	"""Line-ending independent digest, so a CRLF checkout verifies too."""

	return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ---------------------------------------------------------------------------
# Terrain synthesis
# ---------------------------------------------------------------------------


def histogram(frames: list[Image.Image]) -> Counter:
	counts: Counter = Counter()
	for frame in frames:
		counts.update(frame.tobytes())
	counts.pop(0, None)
	return counts


def synth_ground(size: tuple[int, int], counts: Counter, palette: tuple, seed: int, cell: int = 4) -> Image.Image:
	"""Mottled ground with exactly the index distribution of the clear tiles."""

	width, height = size
	rng = random.Random(seed)
	gw, gh = width // cell + 2, height // cell + 2
	grid = [[rng.random() for _ in range(gw)] for _ in range(gh)]
	values = []
	for y in range(height):
		gy, fy = divmod(y / cell, 1)
		gy = int(gy)
		for x in range(width):
			gx, fx = divmod(x / cell, 1)
			gx = int(gx)
			top = grid[gy][gx] * (1 - fx) + grid[gy][gx + 1] * fx
			bottom = grid[gy + 1][gx] * (1 - fx) + grid[gy + 1][gx + 1] * fx
			values.append(top * (1 - fy) + bottom * fy + rng.random() * 0.30)
	order = sorted(range(len(values)), key=lambda index: values[index])
	by_luma = sorted(counts, key=lambda index: sum(palette[index]))
	total = sum(counts.values())
	pixels = [0] * len(values)
	cursor = 0
	for rank, index in enumerate(by_luma):
		share = counts[index] / total
		end = len(order) if rank == len(by_luma) - 1 else min(len(order), cursor + round(share * len(order)))
		for position in order[cursor:end]:
			pixels[position] = index
		cursor = end
	image = Image.new("RGBA", size)
	image.putdata([(*palette[index], 255) for index in pixels])
	return image


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------


class Fonts:
	def __init__(self, engine: Path) -> None:
		common = engine / "mods" / "common"
		self.regular = common / "FreeSans.ttf"
		self.bold = common / "FreeSansBold.ttf"

	def get(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
		return ImageFont.truetype(str(self.bold if bold else self.regular), size)


def text(image: Image.Image, fonts: Fonts, xy, value: str, size: int = 10, fill=INK, bold: bool = False, anchor: str = "la") -> None:
	ImageDraw.Draw(image).text(xy, value, font=fonts.get(size, bold), fill=fill, anchor=anchor)


def text_width(fonts: Fonts, value: str, size: int = 10, bold: bool = False) -> int:
	box = fonts.get(size, bold).getbbox(value)
	return box[2] - box[0]


def bbox(image: Image.Image) -> tuple[int, int, int, int]:
	box = image.getchannel("A").getbbox()
	return box or (0, 0, 1, 1)


def ghost(indexed: Image.Image) -> Image.Image:
	"""Flat scale ghost of a Westwood-derived sprite: shape only, no artwork."""

	data = indexed.tobytes()
	width, height = indexed.size
	solid = [value not in (0, 4) for value in data]
	pixels = []
	for index, filled in enumerate(solid):
		if not filled:
			pixels.append((0, 0, 0, 0))
			continue
		x, y = index % width, index // width
		edge = any(
			not (0 <= x + dx < width and 0 <= y + dy < height) or not solid[(y + dy) * width + x + dx]
			for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
		)
		pixels.append(GHOST_EDGE if edge else GHOST_FILL)
	out = Image.new("RGBA", indexed.size)
	out.putdata(pixels)
	return out


def air_shadow(sprite: Image.Image) -> Image.Image:
	mask = sprite.getchannel("A").point(lambda value: 90 if value else 0)
	shadow = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
	shadow.putalpha(mask)
	return shadow


def upscale(image: Image.Image, factor: int = 3) -> Image.Image:
	return image.resize((image.width * factor, image.height * factor), Image.Resampling.NEAREST)


def save_board(image: Image.Image, output: Path, name: str, written: list[Path]) -> None:
	for suffix, board in (("", image), ("@3x", upscale(image, 3))):
		path = output / f"{name}{suffix}.png"
		rgb = board.convert("RGB")
		# Boards that fit in 256 colours are stored indexed (exactly, since
		# no colour is merged); anything richer stays lossless RGB so no
		# sprite pixel is ever altered.
		colors = rgb.getcolors(256)
		if colors is not None:
			entries = sorted(color for _, color in colors)
			palette = Image.new("P", (1, 1))
			palette.putpalette([channel for color in entries for channel in color] + [0] * (768 - 3 * len(entries)))
			indexed = rgb.quantize(palette=palette, dither=Image.Dither.NONE)
			if indexed.convert("RGB").tobytes() != rgb.tobytes():
				raise RuntimeError(f"{path.name}: indexed save would alter pixels")
			indexed.save(path, optimize=True)
		else:
			rgb.save(path, optimize=True)
		written.append(path)


# ---------------------------------------------------------------------------
# Asset preparation
# ---------------------------------------------------------------------------


@dataclass
class Sprite:
	"""An indexed frame plus the pixel that sits on the actor's position."""

	image: Image.Image
	anchor: tuple[float, float]


class Library:
	def __init__(self, tools: Toolchain) -> None:
		self.tools = tools
		self.pal_paths = {name: tools.content_file(f"{name}.pal") for _, name, _ in THEATRES}
		self.palettes = {name: models.load_pal(path) for name, path in self.pal_paths.items()}
		self.player = self.palettes["temperat"]
		self.palette_map = models.PaletteMap(self.player)
		self.bits = tools.engine / "mods" / "ra" / "bits"
		self.ground = {}
		self.water = {}
		for _, name, ext in THEATRES:
			clear = tools.frames(tools.content_file(f"clear1.{ext}"), self.pal_paths[name], f"clear1-{ext}")
			water = tools.frames(tools.content_file(f"w1.{ext}"), self.pal_paths[name], f"w1-{ext}")
			self.ground[name] = histogram(clear)
			self.water[name] = histogram(water)
		self._frames: dict[str, list[Image.Image]] = {}
		self._us: dict[tuple[str, str, float], Image.Image] = {}

	# -- reference frames --------------------------------------------------

	def is_project_art(self, stem: str) -> bool:
		return (self.bits / f"{stem}.shp").is_file() and stem not in UPSTREAM_BITS

	def raw_frames(self, stem: str) -> list[Image.Image]:
		if stem not in self._frames:
			source = self.bits / f"{stem}.shp"
			if not source.is_file():
				source = self.tools.content_file(f"{stem}.shp")
			self._frames[stem] = self.tools.frames(source, self.pal_paths["temperat"], stem)
		return self._frames[stem]

	def reference(self, actor: str, facing: int) -> tuple[Image.Image, bool]:
		"""Indexed reference frame at native facing index 0-7 (N, NW, W, SW, S, SE, E, NE)."""

		stem, kind, overlay = NEIGHBOUR_SPRITES[actor]
		frames = self.raw_frames(stem)
		if kind == "infantry":
			frame = frames[facing].copy()
		elif kind in ("vehicle", "heli"):
			index = facing * 4 if len(frames) >= 32 else facing * len(frames) // 8
			frame = frames[index].copy()
			if overlay == "self" and len(frames) >= 64:
				turret = frames[32 + index]
				if actor in TURRET_OFFSETS:
					turret = shifted(turret, TURRET_OFFSETS[actor], facing)
				frame = overlay_frame(frame, turret)
		elif kind in ("plane", "ship"):
			count = 16 if len(frames) >= 16 else len(frames)
			frame = frames[(facing * count // 8) % len(frames)].copy()
			if overlay:
				turret = self.raw_frames(overlay)
				frame = overlay_frame(frame, turret[(facing * 4) % len(turret)], center=True)
		else:
			frame = frames[0].copy()
			if overlay:
				frame = overlay_frame(frame, self.raw_frames(overlay)[0], center=True)
		return frame, self.is_project_art(stem)

	# -- U.S. frames -------------------------------------------------------

	def us(self, actor: str, state_index: int, yaw: float) -> Sprite:
		spec = actors.ACTORS[actor]
		state = spec.states[state_index]
		key = (actor, state.name, round(yaw, 4))
		if key not in self._us:
			self._us[key] = actors.sprite(spec, state, yaw, self.palette_map)
		return Sprite(self._us[key], spec.origin)


# Turreted offsets (forward, lateral, up in world units) from the shipped rules,
# applied so a reference turret sits where the running game draws it.
TURRET_OFFSETS = {"ARAS8": (80, 0, 180)}


def shifted(frame: Image.Image, offset: tuple[int, int, int], facing: int) -> Image.Image:
	import math

	forward, _, up = offset
	angle = math.radians(facing * 45)
	dx = -math.sin(angle) * forward * 24 / 1024
	dy = -math.cos(angle) * forward * 24 / 1024 - up * 24 / 1024
	out = Image.new("P", frame.size, 0)
	out.putpalette(frame.getpalette())
	out.paste(frame, (round(dx), round(dy)))
	return out


def overlay_frame(base: Image.Image, top: Image.Image, center: bool = False) -> Image.Image:
	if top.size != base.size:
		canvas = Image.new("P", base.size, 0)
		canvas.putpalette(base.getpalette())
		canvas.paste(top, ((base.width - top.width) // 2, (base.height - top.height) // 2))
		top = canvas
	data = bytearray(base.tobytes())
	for index, value in enumerate(top.tobytes()):
		if value:
			data[index] = value
	out = Image.frombytes("P", base.size, bytes(data))
	out.putpalette(base.getpalette())
	return out


def reference_sprite(lib: Library, actor: str, facing: int, player: PlayerColor | None) -> tuple[Sprite, bool]:
	frame, colour = lib.reference(actor, facing)
	if colour:
		image = board_render.to_rgba(frame, board_render.player_palette(lib.player, player))
	else:
		image = ghost(frame)
	return Sprite(image, (frame.width / 2, frame.height / 2)), colour


def us_rgba(lib: Library, actor: str, state_index: int, yaw: float, player: PlayerColor | None) -> Sprite:
	sprite = lib.us(actor, state_index, yaw)
	return Sprite(board_render.to_rgba(sprite.image, board_render.player_palette(lib.player, player)), sprite.anchor)


def us_silhouette(lib: Library, actor: str, state_index: int, yaw: float) -> Sprite:
	sprite = lib.us(actor, state_index, yaw)
	return Sprite(board_render.silhouette(sprite.image), sprite.anchor)


def paste(canvas: Image.Image, sprite: Sprite, x: float, y: float, altitude: float = 0.0, shadow: bool = False) -> None:
	"""Draw sprite with its actor position at (x, y), lifted by altitude."""

	left = round(x - sprite.anchor[0])
	top = round(y - sprite.anchor[1])
	if shadow:
		_clip_paste(canvas, air_shadow(sprite.image), left, top)
	_clip_paste(canvas, sprite.image, left, round(top - altitude))


def _clip_paste(canvas: Image.Image, image: Image.Image, left: int, top: int) -> None:
	sx0, sy0 = max(0, -left), max(0, -top)
	sx1, sy1 = min(image.width, canvas.width - left), min(image.height, canvas.height - top)
	if sx1 > sx0 and sy1 > sy0:
		canvas.alpha_composite(image, (left + sx0, top + sy0), (sx0, sy0, sx1, sy1))


def extent(sprite: Sprite, altitude: float = 0.0) -> tuple[float, float, float, float]:
	"""Opaque bounds relative to the anchor: (left, top, right, bottom)."""

	x0, y0, x1, y1 = bbox(sprite.image)
	ax, ay = sprite.anchor
	return (x0 - ax, y0 - ay - altitude, x1 - ax, max(y1 - ay, 2.0))


# ---------------------------------------------------------------------------
# Board 1: roster line-up on three theatres, two player colours, silhouettes
# ---------------------------------------------------------------------------

SE = 5  # native facing index for the representative three-quarter view
DOMAINS = (
	("INFANTRY", "infantry", ("USRIFLE", "USJAV", "USJTAC", "TALONSIX")),
	("VEHICLES", "vehicle", ("USMBT", "USIFV", "USICV", "USHIMARS", "USSHORAD", "USRECOV")),
	("AIRCRAFT", "aircraft", ("USF35", "USMQ9", "USUH60", "USAC130")),
	("NAVY", "ship", ("USDDG", "USSSN", "USLPD")),
	("STRUCTURES", "structure", ("USTOC", "USIAMD", "USCUAS", "USNODE")),
)


def rep_yaw(spec: actors.ActorSpec) -> float:
	"""The representative three-quarter (SE) view, or the only view of a building."""

	yaws = spec.yaws()
	return yaws[SE] if len(yaws) > SE else yaws[0]


def lineup_columns(lib: Library):
	columns = []
	for title, domain, members in DOMAINS:
		ref_actor = DOMAIN_REFERENCE[domain][0]
		entries = [("ref", ref_actor, domain)] + [("us", actor, domain) for actor in members]
		if domain == "aircraft":
			entries.insert(3, ("ref", "TRAN", "helicopter"))
		for kind, actor, dom in entries:
			if kind == "ref":
				sprite, _ = reference_sprite(lib, actor, SE, PLAYER_A)
				altitude = 14.0 if dom in ("aircraft", "helicopter") else 0.0
			else:
				spec = actors.ACTORS[actor]
				sprite = us_rgba(lib, actor, 0, rep_yaw(spec), PLAYER_A)
				altitude = spec.altitude
			left, top, right, bottom = extent(sprite, altitude)
			width = max(46, int(right - left) + 10)
			columns.append({"kind": kind, "actor": actor, "domain": dom, "group": title, "width": width,
							"left": left, "right": right, "top": top, "bottom": bottom, "altitude": altitude})
	return columns


def build_lineup(lib: Library, fonts: Fonts) -> Image.Image:
	columns = lineup_columns(lib)
	label_w = 78
	gap = 6
	x = label_w
	for column in columns:
		column["x"] = x + column["width"] / 2 - (column["left"] + column["right"]) / 2
		column["x0"] = x
		x += column["width"]
		if column is not columns[-1] and columns[columns.index(column) + 1]["group"] != column["group"]:
			x += gap
	width = x + 8
	row_top = min(column["top"] for column in columns) - 4
	row_bottom = max(column["bottom"] for column in columns) + 6
	row_h = int(row_bottom - row_top)
	header_h = 44
	band_h = row_h * 2 + 6
	sil_h = row_h + 6
	caption_h = 30
	height = header_h + 3 * (band_h + 6) + sil_h + caption_h + 8
	board = Image.new("RGBA", (int(width), int(height)), PANEL)
	text(board, fonts, (8, 6), "United States (usa) - Checkpoint B concept board: full roster at native scale", 13, bold=True)
	text(board, fonts, (8, 25), "Each band: row 1 player blue, row 2 player red. First column of each group = role-paired native reference (grey ghost = stock Red Alert, shape only). Aircraft lifted 10-14 px with ground shadow. Labels live only in the key row.", 9, INK_DIM)

	y = header_h
	for index, (label, pal_name, _) in enumerate(THEATRES):
		ground = synth_ground((int(width - label_w), band_h), lib.ground[pal_name], lib.palettes[pal_name], seed=1000 + index)
		board.alpha_composite(ground, (label_w, y))
		# Ships sit on that theatre's water, synthesized the same way.
		navy = [column for column in columns if column["domain"] == "ship"]
		water_x0 = int(navy[0]["x0"])
		water_x1 = int(navy[-1]["x0"] + navy[-1]["width"])
		water = synth_ground((water_x1 - water_x0, band_h), lib.water[pal_name], lib.palettes[pal_name], seed=2000 + index)
		board.alpha_composite(water, (water_x0, y))
		text(board, fonts, (8, y + band_h / 2 - 12), label, 11, bold=True)
		text(board, fonts, (8, y + band_h / 2 + 3), f"{pal_name}.pal", 9, INK_DIM)
		for row, player in enumerate((PLAYER_A, PLAYER_B)):
			base = y + row * (row_h + 6) - row_top
			for column in columns:
				if column["kind"] == "ref":
					sprite, _ = reference_sprite(lib, column["actor"], SE, player)
				else:
					spec = actors.ACTORS[column["actor"]]
					sprite = us_rgba(lib, column["actor"], 0, rep_yaw(spec), player)
				airborne = column["domain"] in ("aircraft", "helicopter")
				paste(board, sprite, column["x"], base, column["altitude"], shadow=airborne)
		y += band_h + 6

	# Silhouette row (black fill) for every actor, references included.
	ImageDraw.Draw(board).rectangle((label_w, y, width - 8, y + sil_h), fill=SILHOUETTE_BG)
	text(board, fonts, (8, y + sil_h / 2 - 12), "SILHOUETTE", 10, bold=True)
	text(board, fonts, (8, y + sil_h / 2 + 3), "black fill", 9, INK_DIM)
	base = y - row_top + 3
	for column in columns:
		if column["kind"] == "ref":
			frame, _ = lib.reference(column["actor"], SE)
			sprite = Sprite(board_render.silhouette(frame), (frame.width / 2, frame.height / 2))
		else:
			spec = actors.ACTORS[column["actor"]]
			sprite = us_silhouette(lib, column["actor"], 0, rep_yaw(spec))
		paste(board, sprite, column["x"], base, column["altitude"])
	y += sil_h + 4

	# Key row: labels are kept off the art so legibility is judged unlabelled.
	for column in columns:
		label = column["actor"] + ("*" if column["kind"] == "ref" else "")
		cx = column["x0"] + column["width"] / 2
		text(board, fonts, (cx, y + 2), label, 8, INK if column["kind"] == "us" else INK_DIM, bold=column["kind"] == "us", anchor="ma")
	groups = {}
	for column in columns:
		groups.setdefault(column["group"], []).append(column)
	for title, members in groups.items():
		x0 = members[0]["x0"]
		x1 = members[-1]["x0"] + members[-1]["width"]
		ImageDraw.Draw(board).line((x0 + 2, y + 15, x1 - 2, y + 15), fill=INK_DIM, width=1)
		text(board, fonts, ((x0 + x1) / 2, y + 17), title, 8, INK_DIM, bold=True, anchor="ma")
	text(board, fonts, (8, y + 2), "KEY", 9, INK_DIM, bold=True)
	text(board, fonts, (8, y + 14), "* reference", 8, INK_DIM)
	return board


# ---------------------------------------------------------------------------
# Board 2: representative facings and states, colour + silhouette
# ---------------------------------------------------------------------------


def build_facings(lib: Library, fonts: Fonts) -> Image.Image:
	label_w = 150
	rows = []
	for title, domain, members in DOMAINS:
		rows.append(("header", title, domain))
		ref_domains = (domain, "helicopter") if domain == "aircraft" else (domain,)
		for ref_domain in ref_domains:
			rows.append(("ref", DOMAIN_REFERENCE[ref_domain][0], ref_domain))
		for actor in members:
			spec = actors.ACTORS[actor]
			for state_index in range(len(spec.states)):
				rows.append(("us", actor, state_index))

	def row_sprites(row):
		kind, actor, extra = row
		if kind == "ref":
			if extra == "structure":
				sprite, _ = reference_sprite(lib, actor, 0, PLAYER_A)
				return [sprite], [Sprite(board_render.silhouette(lib.reference(actor, 0)[0]), sprite.anchor)]
			colour = [reference_sprite(lib, actor, facing, PLAYER_A)[0] for facing in range(8)]
			silhouettes = []
			for facing in range(8):
				frame, _ = lib.reference(actor, facing)
				silhouettes.append(Sprite(board_render.silhouette(frame), (frame.width / 2, frame.height / 2)))
			return colour, silhouettes
		spec = actors.ACTORS[actor]
		yaws = spec.yaws()
		return ([us_rgba(lib, actor, extra, yaw, PLAYER_A) for yaw in yaws],
				[us_silhouette(lib, actor, extra, yaw) for yaw in yaws])

	layout = []
	max_width = 0
	for row in rows:
		if row[0] == "header":
			layout.append((row, None, None, 20, 0, 0))
			continue
		colour, silhouettes = row_sprites(row)
		extents = [extent(sprite) for sprite in colour]
		left = min(e[0] for e in extents)
		right = max(e[2] for e in extents)
		top = min(e[1] for e in extents)
		bottom = max(e[3] for e in extents)
		cell = max(30, int(right - left) + 6)
		height = int(bottom - top) + 8
		layout.append((row, colour, silhouettes, height, cell, (left, top)))
		max_width = max(max_width, label_w + cell * len(colour) * 2 + 16)
	total_h = 44 + sum(entry[3] for entry in layout) + 10
	board = Image.new("RGBA", (int(max_width) + 8, int(total_h)), PANEL)
	text(board, fonts, (8, 6), "United States (usa) - facings, states and silhouettes (native scale, native frame order N NW W SW S SE E NE)", 13, bold=True)
	text(board, fonts, (8, 25), "Left: player blue on flat temperate ground (ships on water). Right: black-fill silhouettes. Grey ghost rows are the stock role-paired references. Vehicles show ClassicFacing frames 0,4,...,28.", 9, INK_DIM)
	y = 44
	for row, colour, silhouettes, height, cell, offset in layout:
		kind, actor, extra = row
		if kind == "header":
			text(board, fonts, (8, y + 4), actor, 11, bold=True)
			ImageDraw.Draw(board).line((label_w - 60, y + 11, board.width - 8, y + 11), fill=PANEL_LIGHT, width=1)
			y += height
			continue
		domain = extra if kind == "ref" else actors.ACTORS[actor].domain
		ground = FLAT_WATER if domain == "ship" else FLAT_GROUND
		width_colour = cell * len(colour)
		draw = ImageDraw.Draw(board)
		draw.rectangle((label_w, y, label_w + width_colour - 1, y + height - 3), fill=ground)
		draw.rectangle((label_w + width_colour + 16, y, label_w + 2 * width_colour + 15, y + height - 3), fill=SILHOUETTE_BG)
		if kind == "ref":
			text(board, fonts, (8, y + height / 2 - 6), f"{actor}  (stock reference)", 9, INK_DIM)
		else:
			spec = actors.ACTORS[actor]
			text(board, fonts, (8, y + height / 2 - 12), actor, 10, bold=True)
			text(board, fonts, (8, y + height / 2 + 1), f"{spec.states[extra].name}", 9, INK_DIM)
		left, top = offset
		for index, (sprite, silhouette) in enumerate(zip(colour, silhouettes)):
			x = label_w + index * cell + 3 - left
			paste(board, sprite, x, y + 4 - top)
			paste(board, silhouette, x + width_colour + 16, y + 4 - top)
		y += height
	return board


# ---------------------------------------------------------------------------
# Board 3: mandatory comparisons (contract §8.1, §8.3)
# ---------------------------------------------------------------------------


def _landmark_point(spec: actors.ActorSpec, yaw: float, point: tuple[float, float, float]) -> tuple[float, float]:
	x, y, z = models._yaw(point, yaw)
	ky, kz = spec.projection
	return (spec.origin[0] + x * spec.px, spec.origin[1] + (y * ky - z * kz) * spec.px)


MBT_CALLOUTS = (
	("1", "APS launcher boxes proud of both turret cheeks (absent on M1A2S)", (1.11, -0.57, 1.66)),
	("2", "slatted roof screen: light hatched rectangle on the turret roof", (0.0, -0.05, 1.64)),
	("3", "deep bustle rack with a stowage lump breaking the rear outline", (0.0, 1.30, 1.58)),
)
ICV_CALLOUTS = (
	("1", "eight large wheels in one flat unbroken line", (1.04, 0.42, 0.38)),
	("2", "deep dark V-hull wedge under the hull (flat-bottomed on ARAS8)", (0.66, -0.40, 0.30)),
	("3", "small weapon station well forward, offset right of centre", (0.46, -1.02, 1.46)),
	("4", "lower roofline and no central turret", (-0.40, 0.90, 1.10)),
)


def build_comparisons(lib: Library, fonts: Fonts) -> Image.Image:
	pairs = (("USMBT", "M1A2S", MBT_CALLOUTS, "8.1"), ("USICV", "ARAS8", ICV_CALLOUTS, "8.3"))
	cell = 50
	label_w = 120
	width = label_w + cell * 8 * 2 + 30
	rows_per_theatre = 4
	row_h = 40
	band_h = rows_per_theatre * row_h + 8
	zoom = 5
	detail_h = 44 * zoom // 2 + 120
	height = 48 + 4 * (band_h + 22) + (row_h * 4 + 26) + detail_h * 2 + 20
	board = Image.new("RGBA", (width, height), PANEL)
	text(board, fonts, (8, 6), "Mandatory comparisons: USMBT beside Saudi M1A2S (contract 8.1) and USICV beside Turkish ARAS8 (contract 8.3)", 13, bold=True)
	text(board, fonts, (8, 25), "Native scale, eight native facings, snow / temperate / desert terrain palettes; units use the in-game player palette. Left block player blue, right block player red. Bottom: silhouettes and a 5x detail with the deltas.", 9, INK_DIM)
	y = 48
	for band_index, (label, pal_name, _) in enumerate(THEATRES):
		ground = synth_ground((width - label_w - 8, band_h), lib.ground[pal_name], lib.palettes[pal_name], seed=3000 + band_index)
		board.alpha_composite(ground, (label_w, y + 16))
		text(board, fonts, (8, y + 2), f"{label}  ({pal_name}.pal)", 11, bold=True)
		row_y = y + 16 + 4
		for us_actor, ref_actor, _, _ in pairs:
			for actor in (us_actor, ref_actor):
				text(board, fonts, (8, row_y + row_h / 2 - 6), actor + ("" if actor.startswith("US") else "  (shipped)"), 10, INK if actor.startswith("US") else INK_DIM, bold=actor.startswith("US"))
				for block, player in enumerate((PLAYER_A, PLAYER_B)):
					for facing in range(8):
						cx = label_w + block * (cell * 8 + 22) + facing * cell + cell / 2
						if actor.startswith("US"):
							spec = actors.ACTORS[actor]
							sprite = us_rgba(lib, actor, 0, spec.yaws()[facing], player)
						else:
							sprite, _ = reference_sprite(lib, actor, facing, player)
						paste(board, sprite, cx, row_y + row_h / 2 + 2)
				row_y += row_h
		y += band_h + 22
	# Silhouettes.
	text(board, fonts, (8, y + 2), "SILHOUETTES", 11, bold=True)
	ImageDraw.Draw(board).rectangle((label_w, y + 16, label_w + cell * 8 - 1, y + 16 + row_h * 4 + 4), fill=SILHOUETTE_BG)
	row_y = y + 20
	for us_actor, ref_actor, _, _ in pairs:
		for actor in (us_actor, ref_actor):
			text(board, fonts, (8, row_y + row_h / 2 - 6), actor, 10, INK if actor.startswith("US") else INK_DIM, bold=actor.startswith("US"))
			for facing in range(8):
				cx = label_w + facing * cell + cell / 2
				if actor.startswith("US"):
					spec = actors.ACTORS[actor]
					sprite = us_silhouette(lib, actor, 0, spec.yaws()[facing])
				else:
					frame, _ = lib.reference(actor, facing)
					sprite = Sprite(board_render.silhouette(frame), (frame.width / 2, frame.height / 2))
				paste(board, sprite, cx, row_y + row_h / 2 + 2)
			row_y += row_h
	# Remap coverage note for the pair.
	notes_x = label_w + cell * 8 + 22
	for index, (us_actor, ref_actor, _, _) in enumerate(pairs):
		us_share = sum(board_render.remap_share(lib.us(us_actor, 0, yaw).image) for yaw in actors.ACTORS[us_actor].yaws()) / 8
		ref_share = sum(board_render.remap_share(lib.reference(ref_actor, facing)[0]) for facing in range(8)) / 8
		text(board, fonts, (notes_x, y + 26 + index * 34), f"Player-colour pixels: {us_actor} {us_share * 100:.0f}%  vs  {ref_actor} {ref_share * 100:.0f}%", 10)
		text(board, fonts, (notes_x, y + 40 + index * 34), "(share of opaque pixels on remap ramp 80-95, eight facings)", 9, INK_DIM)
	y += row_h * 4 + 26
	# 4x detail panels with numbered deltas.
	for us_actor, ref_actor, callouts, section in pairs:
		spec = actors.ACTORS[us_actor]
		facing = SE
		yaw = spec.yaws()[facing]
		ImageDraw.Draw(board).rectangle((8, y, width - 9, y + detail_h - 9), fill=FLAT_GROUND)
		text(board, fonts, (14, y + 4), f"{zoom}x detail (contract {section}): {us_actor} left, {ref_actor} right, facing SE, player blue", 10, bold=True)
		us_sprite = us_rgba(lib, us_actor, 0, yaw, PLAYER_A)
		ref_sprite, _ = reference_sprite(lib, ref_actor, facing, PLAYER_A)
		us_big = Sprite(upscale(us_sprite.image, zoom), (us_sprite.anchor[0] * zoom, us_sprite.anchor[1] * zoom))
		ref_big = Sprite(upscale(ref_sprite.image, zoom), (ref_sprite.anchor[0] * zoom, ref_sprite.anchor[1] * zoom))
		us_x, ref_x = 14 + us_big.anchor[0], 14 + us_big.image.width + 20 + ref_big.anchor[0]
		base_y = y + 10 + us_big.anchor[1]
		paste(board, us_big, us_x, base_y)
		paste(board, ref_big, ref_x, base_y)
		draw = ImageDraw.Draw(board)
		legend_x = ref_x - ref_big.anchor[0] + ref_big.image.width + 40
		for index, (number, description, point) in enumerate(callouts):
			px, py = _landmark_point(spec, yaw, point)
			sx = us_x - us_big.anchor[0] + px * zoom
			sy = base_y - us_big.anchor[1] + py * zoom
			tx, ty = legend_x - 16, y + 34 + index * 24
			draw.line((sx, sy, tx, ty + 6), fill=(255, 236, 120, 255), width=1)
			draw.ellipse((sx - 3, sy - 3, sx + 3, sy + 3), outline=(255, 236, 120, 255), width=1)
			draw.ellipse((tx - 8, ty - 1, tx + 6, ty + 13), fill=(255, 236, 120, 255))
			text(board, fonts, (tx - 1, ty + 6), number, 9, (20, 20, 20, 255), bold=True, anchor="mm")
			text(board, fonts, (legend_x, ty), description, 10)
		y += detail_h
	return board.crop((0, 0, board.width, y + 8))


# ---------------------------------------------------------------------------
# Board 4: player-colour zones
# ---------------------------------------------------------------------------


def build_zones(lib: Library, fonts: Fonts) -> tuple[Image.Image, dict[str, float]]:
	shares: dict[str, float] = {}
	entries = []
	for _, _, members in DOMAINS:
		for actor in members:
			entries.append(("us", actor))
	entries += [("ref", "M1A2S"), ("ref", "ARAS8")]
	cell = 64
	label_w = 170
	row_h = 58
	width = label_w + cell * (1 + len(ZONE_COLORS)) + 8
	height = 70 + row_h * len(entries) + 10
	board = Image.new("RGBA", (width, height), PANEL)
	text(board, fonts, (8, 6), "Player-colour zones (facing SE, primary state)", 13, bold=True)
	text(board, fonts, (8, 25), "Column 1: remap-ramp pixels painted magenta over a grey sprite. Then the same frame remapped exactly as OpenRA's", 9, INK_DIM)
	text(board, fonts, (8, 37), "PlayerColorRemap does, for five lobby preset colours (blue, red, green, gold, maroon).", 9, INK_DIM)
	for index, label in enumerate(("zones",) + tuple(color.name for color in ZONE_COLORS)):
		text(board, fonts, (label_w + index * cell + cell / 2, 54), label, 9, INK_DIM, anchor="ma")
	y = 68
	for kind, actor in entries:
		if kind == "us":
			spec = actors.ACTORS[actor]
			frame = lib.us(actor, 0, rep_yaw(spec)).image
			anchor = spec.origin
			share = sum(board_render.remap_share(lib.us(actor, 0, yaw).image) for yaw in spec.yaws()) / len(spec.yaws())
			shares[actor] = share
		else:
			frame, _ = lib.reference(actor, SE)
			anchor = (frame.width / 2, frame.height / 2)
			share = sum(board_render.remap_share(lib.reference(actor, facing)[0]) for facing in range(8)) / 8
			shares[actor] = share
		domain = actors.ACTORS[actor].domain if kind == "us" else "vehicle"
		ground = FLAT_WATER if domain == "ship" else FLAT_GROUND
		ImageDraw.Draw(board).rectangle((label_w, y, width - 9, y + row_h - 4), fill=ground)
		text(board, fonts, (8, y + row_h / 2 - 13), actor, 10, INK if kind == "us" else INK_DIM, bold=kind == "us")
		text(board, fonts, (8, y + row_h / 2 + 1), f"remap {share * 100:.1f}% of opaque px", 9, INK_DIM)
		images = [board_render.zone_map(frame, lib.player)] + [board_render.to_rgba(frame, board_render.player_palette(lib.player, color)) for color in ZONE_COLORS]
		for column, image in enumerate(images):
			sprite = Sprite(image, anchor)
			left, top, right, bottom = extent(sprite)
			cx = label_w + column * cell + cell / 2 - (left + right) / 2
			cy = y + (row_h - 4) / 2 - (top + bottom) / 2
			paste(board, sprite, cx, cy)
		y += row_h
	return board, shares


# ---------------------------------------------------------------------------
# Board 5: silhouette overlap matrix
# ---------------------------------------------------------------------------


def build_matrix(lib: Library, fonts: Fonts) -> Image.Image:
	label_w = 90
	cell = 62
	row_h = 70
	max_neighbours = max(len(value) for value in NEIGHBOURS.values())
	width = label_w + cell * 3 + 20 + cell * max_neighbours + 8
	height = 52 + row_h * len(NEIGHBOURS) + 10
	board = Image.new("RGBA", (width, height), PANEL)
	text(board, fonts, (8, 6), "Silhouette overlap matrix: each U.S. actor (three facings) beside every neighbour named in contract 7.1 / 7.2", 13, bold=True)
	text(board, fonts, (8, 25), "Black fill, native scale, neighbours at the SE facing. MH60 is added for USUH60 although the contract matrix omits it. USRECOV has no neighbour in the catalog.", 9, INK_DIM)
	y = 48
	for actor, neighbours in NEIGHBOURS.items():
		spec = actors.ACTORS[actor]
		draw = ImageDraw.Draw(board)
		draw.rectangle((label_w, y, label_w + cell * 3 - 1, y + row_h - 16), fill=(226, 224, 210, 255))
		draw.rectangle((label_w + cell * 3 + 20, y, label_w + cell * 3 + 20 + cell * max(1, len(neighbours)) - 1, y + row_h - 16), fill=SILHOUETTE_BG)
		text(board, fonts, (8, y + row_h / 2 - 14), actor, 10, bold=True)
		facings = (SE, 2, 4) if spec.facings > 1 else (0,)
		for column, facing in enumerate(facings):
			sprite = us_silhouette(lib, actor, 0, spec.yaws()[facing])
			left, top, right, bottom = extent(sprite, 0)
			paste(board, sprite, label_w + column * cell + cell / 2 - (left + right) / 2, y + (row_h - 16) / 2 - (top + bottom) / 2)
		for column, neighbour in enumerate(neighbours):
			facing = SE
			frame, _ = lib.reference(neighbour, facing)
			sprite = Sprite(board_render.silhouette(frame), (frame.width / 2, frame.height / 2))
			left, top, right, bottom = extent(sprite, 0)
			cx = label_w + cell * 3 + 20 + column * cell + cell / 2
			paste(board, sprite, cx - (left + right) / 2, y + (row_h - 16) / 2 - (top + bottom) / 2)
			text(board, fonts, (cx, y + row_h - 14), neighbour, 8, INK_DIM, anchor="ma")
		if not neighbours:
			text(board, fonts, (label_w + cell * 3 + 26, y + row_h / 2 - 12), "no catalog neighbour", 9, (80, 80, 80, 255))
		y += row_h
	return board


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def git_head(path: Path) -> str:
	try:
		return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
	except (OSError, subprocess.CalledProcessError):
		return "unknown"


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("--engine", type=Path, required=True, help="OpenRA checkout with a built bin/OpenRA.Utility")
	parser.add_argument("--support-dir", type=Path, required=True, help="directory containing Content/ra/v2 (read only)")
	parser.add_argument("--output", type=Path, required=True, help="board output directory")
	parser.add_argument("--work", type=Path, help="scratch directory (defaults to a temporary directory)")
	args = parser.parse_args()

	engine = args.engine.resolve()
	support = args.support_dir.resolve()
	if not (support / "Content" / "ra" / "v2").is_dir():
		raise SystemExit(f"{support} does not contain Content/ra/v2")
	output = args.output.resolve()
	output.mkdir(parents=True, exist_ok=True)
	temporary = None
	if args.work:
		work = args.work.resolve()
		work.mkdir(parents=True, exist_ok=True)
	else:
		temporary = tempfile.TemporaryDirectory(prefix="usa-concept-")
		work = Path(temporary.name)
	try:
		# OpenRA.Utility writes logs/settings into its support directory, so it
		# gets a private one that only mirrors the read-only content.
		private_support = work / "support"
		content = private_support / "Content" / "ra" / "v2"
		if not content.is_dir():
			shutil.copytree(support / "Content" / "ra" / "v2", content)
		tools = Toolchain(engine, private_support, work)
		lib = Library(tools)
		fonts = Fonts(engine)
		written: list[Path] = []
		save_board(build_lineup(lib, fonts), output, "usa-concept-board", written)
		save_board(build_facings(lib, fonts), output, "usa-facings-states", written)
		save_board(build_comparisons(lib, fonts), output, "usa-comparisons-mbt-icv", written)
		zones, shares = build_zones(lib, fonts)
		save_board(zones, output, "usa-player-colour-zones", written)
		save_board(build_matrix(lib, fonts), output, "usa-silhouette-matrix", written)
		manifest = {
			"generator": BOARD_VERSION,
			"product_commit": git_head(SCRIPT_ROOT),
			"engine_commit": git_head(engine),
			"inputs": {
				"scripts": {path.name: text_sha256(path) for path in sorted(SCRIPT_ROOT.glob("usa_concept_*.py")) + [Path(__file__).resolve(), SCRIPT_ROOT / "red_sea_directional_vehicle.py"]},
				"palettes": {name: sha256(path) for name, path in sorted(lib.pal_paths.items())},
			},
			"player_colours": {color.name: color.hex for color in ZONE_COLORS},
			"remap_share": {actor: round(share, 4) for actor, share in shares.items()},
			"outputs": {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size, "size": list(Image.open(path).size)} for path in written},
		}
		(output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
		for path in written:
			print(f"{path.name}: {Image.open(path).size[0]}x{Image.open(path).size[1]}, {path.stat().st_size} bytes")
	finally:
		if temporary is not None:
			temporary.cleanup()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
