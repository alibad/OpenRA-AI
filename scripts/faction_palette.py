"""Deterministic Red Alert palette quantization for the faction sprite generators.

``PIL.Image.quantize(palette=...)`` uses an approximate, version-dependent
nearest-colour cache.  Regenerating the same geometry with another Pillow
build moved thousands of pixels between the player-remap ramp and ordinary
palette entries, which is why several shipped vehicles could not be
reproduced and why their ownership colour flickered between facings.

This module performs an exact nearest-colour search in NumPy and encodes the
three special roles of the Red Alert ``player`` palette explicitly:

* ownership: faces authored with a team material are rendered by
  ``red_sea_directional_vehicle._render`` as magenta markers whose brightness
  carries the lighting; they are mapped onto remap indices 80..95 by
  luminance so the whole ramp is used, as in native units;
* shadow: the renderer's translucent ground shadow becomes index 4, which the
  engine draws as a 140-alpha shadow;
* animation safety: indices 96..102 cycle as water and 103 blinks in the
  player palette, so ordinary artwork never uses them.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
from PIL import Image


TRANSPARENT = 0
SHADOW = 4
REMAP = tuple(range(80, 96))
PALETTE_ANIMATED = tuple(range(96, 104))
OPAQUE_FILL = 16  # native cameos use this near-black instead of index 0
RESERVED = (1, 3, SHADOW)
ALPHA_OPAQUE = 96
ALPHA_SHADOW = 40


def palette_rgb(palette_image: Image.Image) -> np.ndarray:
    raw = palette_image.getpalette()
    if raw is None:
        raise ValueError("reference palette image has no palette")
    raw = list(raw) + [0] * (768 - len(raw))
    return np.array(raw[:768], dtype=np.int32).reshape(256, 3)


def luminance(rgb: np.ndarray) -> np.ndarray:
    rgb = rgb.astype(np.float64)
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def nearest_indices(pixels: np.ndarray, palette: np.ndarray, allowed: Iterable[int]) -> np.ndarray:
    """Exact nearest palette entry (squared RGB distance) among ``allowed``."""

    allowed = np.array(sorted(set(allowed)), dtype=np.int32)
    if len(pixels) == 0:
        return np.zeros(0, dtype=np.uint8)
    candidates = palette[allowed]
    result = np.empty(len(pixels), dtype=np.uint8)
    pixels = pixels.astype(np.int32)
    for start in range(0, len(pixels), 4096):
        chunk = pixels[start:start + 4096]
        distance = ((chunk[:, None, :] - candidates[None, :, :]) ** 2).sum(axis=2)
        result[start:start + 4096] = allowed[np.argmin(distance, axis=1)]
    return result


def team_marker(intensity: float) -> tuple[int, int, int]:
    """Marker colour for a team-material face at the given brightness (0..1)."""

    value = max(24, min(255, round(255 * intensity)))
    return (value, 0, value)


def is_team_marker(rgb: np.ndarray) -> np.ndarray:
    """Pixels in the magenta marker family, tolerant of LANCZOS edge blending."""

    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)
    low = np.minimum(r, b)
    # Markers are (v, 0, v); outlines darken them and LANCZOS blends them with
    # neighbouring materials. No authored material has red and blue both well
    # above green, so a clear magenta excess identifies the marker family.
    return (low >= 12) & (low - g >= 10) & (g * 2 < low + 8) & (np.abs(r - b) <= np.maximum(24, low // 2))


def remap_for_markers(values: np.ndarray, palette: np.ndarray, gain: float = 1.0,
                      darkest: int = 93) -> np.ndarray:
    """Map marker brightness to the remap ramp by luminance (80 brightest)."""

    ramp = np.array([index for index in REMAP if index <= darkest], dtype=np.int32)
    ramp_luma = luminance(palette[ramp])
    target = np.clip(values.astype(np.float64) / 255.0 * ramp_luma.max() * gain, 0, 255)
    choice = np.argmin(np.abs(target[:, None] - ramp_luma[None, :]), axis=1)
    return ramp[choice].astype(np.uint8)


def quantize_sprite(image: Image.Image, palette_image: Image.Image, *, opaque: bool = False,
                    shadow: bool = True, remap_gain: float = 1.0, allow_remap_matches: bool = False) -> Image.Image:
    """Quantize an RGBA render into an indexed Red Alert sprite frame."""

    palette = palette_rgb(palette_image)
    rgba = np.array(image.convert("RGBA"), dtype=np.int32)
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    height, width = alpha.shape
    out = np.zeros((height, width), dtype=np.uint8)

    solid = np.ones_like(alpha, dtype=bool) if opaque else alpha >= ALPHA_OPAQUE
    team = solid & is_team_marker(rgb)
    ordinary = solid & ~team
    # The reference palette is the ``--noshadow`` PNG export, which blanks
    # indices 1, 3 and 4 to black; in the real palette 1 is magenta and 3/4
    # are shadow greens (4 is the unit shadow, 3 the chrome shadow), so none
    # of them may be chosen for ordinary colors.
    excluded = {TRANSPARENT, *RESERVED, *PALETTE_ANIMATED}
    if not allow_remap_matches:
        excluded |= set(REMAP)
    allowed = [index for index in range(256) if index not in excluded]
    out[ordinary] = nearest_indices(rgb[ordinary], palette, allowed)
    if team.any():
        values = np.maximum(rgb[..., 0], rgb[..., 2])[team]
        out[team] = remap_for_markers(values, palette, remap_gain)
    if shadow and not opaque:
        # The renderer's contact shadow is pure black at partial alpha;
        # anti-aliased silhouette edges carry the body color and stay clear.
        shade = ~solid & (alpha >= ALPHA_SHADOW) & (rgb.max(axis=2) <= 8)
        out[shade] = SHADOW

    result = Image.frombytes("P", (width, height), out.tobytes())
    result.putpalette(palette.astype(np.uint8).flatten().tolist())
    if not opaque:
        result.info["transparency"] = TRANSPARENT
    return result


def neutralize_team_markers(image: Image.Image, tint: tuple[float, float, float] = (0.60, 0.60, 0.54)) -> Image.Image:
    """Replace ownership markers with a neutral material of similar brightness.

    Wrecks, husks and sinking hulls are desaturated derivatives of the live
    render; they must not inherit magenta marker pixels.
    """

    rgba = np.array(image.convert("RGBA"), dtype=np.int32)
    marker = is_team_marker(rgba[..., :3]) & (rgba[..., 3] > 0)
    if marker.any():
        value = np.maximum(rgba[..., 0], rgba[..., 2])[marker].astype(np.float64)
        for channel, factor in enumerate(tint):
            rgba[..., channel][marker] = np.clip(np.round(value * factor), 0, 255).astype(np.int32)
    return Image.fromarray(rgba.astype(np.uint8), "RGBA")
