#!/usr/bin/env python3
"""Build native RA2 models and sidebar assets from original project sources."""
from PIL import Image, ImageOps

from ra2_faction_voxels import ROOT, OUTPUT, build

ROSTERS = {
    "china": ("r2qilin", "r2lynx", "r2mantis", "r2cloud"),
    "iran": ("r2karrar", "r2raad", "r2fajr", "r2mohajer"),
    "turkey": ("r2bozkir", "r2yildirim", "r2sancak", "r2kuzgun"),
}


def portraits(output=OUTPUT):
    for folder in ("icons", "previews"):
        (output / folder).mkdir(parents=True, exist_ok=True)
    for country, actors in ROSTERS.items():
        source = ROOT / "assets/ra2-modern-factions" / (country + "-portraits-v1.png")
        with Image.open(source) as image:
            w, h = image.size
            for i, actor in enumerate(actors):
                x, y = i % 2, i // 2
                tile = image.crop((x*w//2, y*h//2, (x+1)*w//2, (y+1)*h//2)).convert("RGB")
                # Preserve the unit's proportions. Narrow dark side margins are
                # preferable to stretching a square concept into a wide cameo.
                icon = ImageOps.pad(tile, (60, 48), method=Image.Resampling.LANCZOS, color=(10, 22, 26))
                icon.save(output / "icons" / (actor + ".png"))
            image.resize((512, 512), Image.Resampling.LANCZOS).save(output / "previews" / (country + ".png"))


if __name__ == "__main__":
    build()
    portraits()
