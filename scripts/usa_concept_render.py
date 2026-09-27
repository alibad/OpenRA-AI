"""Render indexed Red Alert sprites the way OpenRA draws them.

``PlayerColorRemap`` is a line-for-line port of
``OpenRA.Game/Graphics/PlayerColorRemap.cs`` and the linear-light helpers in
``OpenRA.Game/Primitives/Color.cs`` so player colours on the concept board
match the running game.  Shadow indexes are drawn as premultiplied black with
alpha 140, matching ``ImmutablePalette``'s shadow handling.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


Color = tuple[int, int, int]
REMAP_INDEXES = tuple(range(80, 96))


def _srgb_to_linear(c: float) -> float:
	return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
	return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _rgb_to_hsv(r: float, g: float, b: float) -> tuple[float, float, float]:
	rgb_max = max(r, g, b)
	rgb_min = min(r, g, b)
	delta = rgb_max - rgb_min
	if delta == 0:
		return 0.0, 0.0, rgb_max
	if r == rgb_max:
		hue = (g - b) / (6 * delta)
	elif g == rgb_max:
		hue = (b - r) / (6 * delta) + 1 / 3
	else:
		hue = (r - g) / (6 * delta) + 2 / 3
	h = hue - int(hue)
	if h < 0:
		h += 1
	return h, delta / rgb_max, rgb_max


def _clamp01(value: float) -> float:
	return 0.0 if value < 0 else 1.0 if value > 1 else value


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
	px = abs(h * 6 - 3)
	py = abs((h + 2 / 3) % 1 * 6 - 3)
	pz = abs((h + 1 / 3) % 1 * 6 - 3)

	def lerp(a: float, b: float, t: float) -> float:
		return a + (b - a) * t

	return (v * lerp(1, _clamp01(px - 1), s), v * lerp(1, _clamp01(py - 1), s), v * lerp(1, _clamp01(pz - 1), s))


@dataclass(frozen=True)
class PlayerColor:
	name: str
	hex: str

	@property
	def rgb(self) -> Color:
		return (int(self.hex[0:2], 16), int(self.hex[2:4], 16), int(self.hex[4:6], 16))


def remap_color(original: Color, player: Color) -> Color:
	pr, pg, pb = (_srgb_to_linear(c / 255) for c in player)
	hue, saturation, value = _rgb_to_hsv(pr, pg, pb)
	r, g, b = (_srgb_to_linear(c / 255) for c in original)
	brightness = max(r, g, b)
	nr, ng, nb = _hsv_to_rgb(hue, saturation, brightness * value)
	return tuple(round(_linear_to_srgb(c) * 255) for c in (nr, ng, nb))  # type: ignore[return-value]


def player_palette(base: tuple[Color, ...], player: PlayerColor | None) -> list[tuple[int, int, int, int]]:
	"""RGBA palette with transparency (0), shadow (4) and optional remap."""

	entries: list[tuple[int, int, int, int]] = []
	for index, color in enumerate(base):
		if index == 0:
			entries.append((0, 0, 0, 0))
		elif index == 4:
			entries.append((0, 0, 0, 140))
		elif player is not None and index in REMAP_INDEXES:
			entries.append((*remap_color(color, player.rgb), 255))
		else:
			entries.append((*color, 255))
	return entries


def to_rgba(indexed: Image.Image, palette: list[tuple[int, int, int, int]]) -> Image.Image:
	data = indexed.tobytes()
	out = Image.new("RGBA", indexed.size)
	out.putdata([palette[value] for value in data])
	return out


def silhouette(indexed: Image.Image, fill=(12, 12, 12, 255)) -> Image.Image:
	"""Black-fill every opaque, non-shadow pixel."""

	data = indexed.tobytes()
	out = Image.new("RGBA", indexed.size)
	out.putdata([fill if value not in (0, 4) else (0, 0, 0, 0) for value in data])
	return out


def zone_map(indexed: Image.Image, base: tuple[Color, ...], zone=(255, 0, 214, 255)) -> Image.Image:
	"""Desaturate the sprite and paint its player-colour zones in solid magenta."""

	data = indexed.tobytes()
	out = Image.new("RGBA", indexed.size)
	pixels = []
	for value in data:
		if value == 0:
			pixels.append((0, 0, 0, 0))
		elif value == 4:
			pixels.append((0, 0, 0, 140))
		elif value in REMAP_INDEXES:
			pixels.append(zone)
		else:
			r, g, b = base[value]
			grey = round(0.3 * r + 0.59 * g + 0.11 * b)
			pixels.append((grey, grey, grey, 255))
	out.putdata(pixels)
	return out


def remap_share(indexed: Image.Image) -> float:
	data = indexed.tobytes()
	opaque = sum(1 for value in data if value not in (0, 4))
	remap = sum(1 for value in data if 80 <= value <= 95)
	return remap / opaque if opaque else 0.0
