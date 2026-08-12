"""Package a deterministic six-player skirmish map for the Iran roster."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import shutil
import zipfile

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "engine" / "openra" / "mods" / "ra" / "maps" / "bombardment-islands.oramap"
OUTPUT = ROOT / "generated" / "missions" / "iran-doctrine-range.oramap"
INSTALL = ROOT / "engine" / "openra" / "mods" / "ra" / "maps" / "iran-doctrine-range.oramap"
FIXED_TIME = (2026, 8, 12, 0, 0, 0)

SHOWCASE_ACTORS = """\
\tIranShowcase0: irbas
\t\tOwner: Multi0
\t\tLocation: 62,78
\t\tFacing: 0
\tIranShowcase1: iratgm
\t\tOwner: Multi0
\t\tLocation: 63,80
\t\tFacing: 128
\tIranShowcase2: irdc
\t\tOwner: Multi0
\t\tLocation: 64,78
\t\tFacing: 256
\tIranShowcase3: shadowone
\t\tOwner: Multi0
\t\tLocation: 65,80
\t\tFacing: 384
\tIranShowcase4: irkarr
\t\tOwner: Multi0
\t\tLocation: 66,78
\t\tFacing: 512
\tIranShowcase5: irraad
\t\tOwner: Multi0
\t\tLocation: 67,80
\t\tFacing: 640
\tIranShowcase6: irfajr
\t\tOwner: Multi0
\t\tLocation: 64,82
\t\tFacing: 768
\tIranShowcase7: ircoast
\t\tOwner: Multi0
\t\tLocation: 48,90
\t\tFacing: 896
\tIranShowcase8: irazar
\t\tOwner: Multi0
\t\tLocation: 62,82
\t\tFacing: 128
\tIranShowcase9: irtoufan
\t\tOwner: Multi0
\t\tLocation: 63,83
\t\tFacing: 384
\tIranShowcase10: irmohajer
\t\tOwner: Multi0
\t\tLocation: 65,83
\t\tFacing: 640
\tIranShowcase11: irloiter
\t\tOwner: Multi0
\t\tLocation: 67,83
\t\tFacing: 896
\tIranShowcase12: irpey
\t\tOwner: Multi0
\t\tLocation: 39,94
\t\tFacing: 0
\tIranShowcase13: irghadir
\t\tOwner: Multi0
\t\tLocation: 41,94
\t\tFacing: 512
\tIranTarget0: irantargettank
\t\tOwner: Multi1
\t\tLocation: 72,76
\t\tFacing: 512
\tIranTarget1: irantargetpt
\t\tOwner: Multi1
\t\tLocation: 45,94
\t\tFacing: 512
\tIranTarget2: powr
\t\tOwner: Multi1
\t\tLocation: 72,79
"""

SHOWCASE_RULES = """\
Player:
\t# Doctrine-range telemetry is symmetric: every player can inspect the full
\t# build tree and bot force composition without hidden-information inference.
\tRevealsMap@DOCTRINERANGE:

IRBAS:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRATGM:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRDC:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

SHADOWONE:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRKARR:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRRAAD:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRFAJR:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRCOAST:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRAZAR:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRTOUFAN:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRMOHAJER:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRPEY:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRGHADIR:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: AttackAnything

IRANTARGETTANK:
\tInherits: 3TNK
\t-Buildable:
\tRejectsOrders:
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: HoldFire
\tRenderSprites:
\t\tImage: 3tnk

IRANTARGETPT:
\tInherits: PT
\t-Buildable:
\tRejectsOrders:
\tHealth:
\t\tHP: 60000
\tAutoTarget:
\t\tInitialStance: HoldFire
\t\tInitialStanceAI: HoldFire
\tRenderSprites:
\t\tImage: pt
"""


def info(name: str) -> zipfile.ZipInfo:
    result = zipfile.ZipInfo(name, FIXED_TIME)
    result.compress_type = zipfile.ZIP_DEFLATED
    result.external_attr = 0o644 << 16
    return result


def preview(data: bytes) -> bytes:
    image = Image.open(io.BytesIO(data)).convert("RGBA")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for inset, color in ((0, (23, 116, 57, 255)), (2, (240, 240, 232, 255)), (4, (202, 34, 47, 255))):
        draw.rectangle((inset, inset, width - 1 - inset, height - 1 - inset), outline=color, width=2)
    center = (width // 2, height // 2)
    for radius in (9, 17, 25):
        draw.arc((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), 205, 335, fill=(102, 224, 178, 225), width=1)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def main() -> int:
    with zipfile.ZipFile(SOURCE) as source:
        files = {name: source.read(name) for name in source.namelist()}
    yaml = files["map.yaml"].decode("utf-8")
    yaml = yaml.replace("Title: Bombardment Islands", "Title: Iran Doctrine Range")
    yaml = yaml.replace("Author: Sprog", "Author: Sprog; Iran faction adaptation by OpenRA AI")
    yaml = yaml.replace("Categories: Conquest", "Categories: Conquest, Skirmish")
    yaml = yaml.replace("\t\tFaction: Random", "\t\tFaction: iran\n\t\tLockFaction: True")
    yaml = yaml.replace(
        "PlayerReference@Multi0:\n\t\tName: Multi0\n\t\tPlayable: True\n\t\tFaction: iran\n\t\tLockFaction: True",
        "PlayerReference@Multi0:\n\t\tName: Multi0\n\t\tPlayable: True\n\t\tFaction: iran\n\t\tLockFaction: True\n\t\tLockSpawn: True\n\t\tSpawn: 4",
    )
    yaml = yaml.replace(
        "PlayerReference@Multi1:\n\t\tName: Multi1\n\t\tPlayable: True\n\t\tFaction: iran\n\t\tLockFaction: True",
        "PlayerReference@Multi1:\n\t\tName: Multi1\n\t\tPlayable: True\n\t\tFaction: iran\n\t\tLockFaction: True\n\t\tLockSpawn: True\n\t\tSpawn: 3",
    )
    # Move the human start toward the strait so the initial viewport contains
    # the land, air, coastal, and naval doctrine-range exhibits together.
    yaml = yaml.replace(
        "\tActor105: mpspawn\n\t\tOwner: Neutral\n\t\tLocation: 67,87",
        "\tActor105: mpspawn\n\t\tOwner: Neutral\n\t\tLocation: 55,86",
    )
    yaml = yaml.replace("Actors:\n", "Actors:\n" + SHOWCASE_ACTORS)
    yaml += "\nRules: rules.yaml\n"
    files["map.yaml"] = yaml.encode("utf-8")
    files["map.png"] = preview(files["map.png"])
    files["rules.yaml"] = SHOWCASE_RULES.encode("utf-8")
    manifest = {
        "schema": "openra-ai.iran-skirmish/v1",
        "built": "2026-08-12",
        "source_map": "Bombardment Islands by Sprog",
        "purpose": "Six-player land/air/naval skirmish exposing the complete Iran production tree and a Multi0 doctrine-range showcase force.",
        "gameplay_guardrail": "Fictional balanced doctrine sandbox; no recreation of a real attack.",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    files["iran-map-manifest.json"] = json.dumps(manifest, indent=2).encode("utf-8") + b"\n"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w") as output:
        for name, data in sorted(files.items()):
            output.writestr(info(name), data)
    INSTALL.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUTPUT, INSTALL)
    print(f"Map: {OUTPUT}")
    print(f"Installed: {INSTALL}")
    print(f"SHA256: {hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
