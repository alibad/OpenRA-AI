"""Package an unlisted two-player map for live Turkey AI progression checks."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "engine" / "openra" / "mods" / "ra" / "maps" / "shuriken-island"
DEFAULT_OUTPUT = ROOT / "generated" / "validation" / "turkey-ai-progression.oramap"
INSTALL = ROOT / "engine" / "openra" / "mods" / "ra" / "maps" / "turkey-ai-progression.oramap"


PLAYERS = """Players:
\tPlayerReference@Neutral:
\t\tName: Neutral
\t\tOwnsWorld: True
\t\tNonCombatant: True
\t\tFaction: england
\tPlayerReference@Creeps:
\t\tName: Creeps
\t\tNonCombatant: True
\t\tFaction: england
\tPlayerReference@Multi0:
\t\tName: Multi0
\t\tPlayable: True
\t\tRequired: True
\t\tAllowBots: False
\t\tLockFaction: True
\t\tFaction: turkey
\t\tEnemies: Creeps
\tPlayerReference@Multi1:
\t\tName: Multi1
\t\tPlayable: True
\t\tRequired: True
\t\tAllowBots: True
\t\tLockFaction: True
\t\tFaction: russia
\t\tEnemies: Creeps

"""

RULES = """Player:
\tPlayerResources:
\t\tDefaultCash: 20000
\t\tDefaultCashDropdownLocked: True
"""


def build(output: Path) -> None:
    source_yaml = (SOURCE / "map.yaml").read_text(encoding="utf-8")
    source_yaml = source_yaml.replace("Title: Shuriken Island", "Title: Turkey AI Progression Range", 1)
    players_start = source_yaml.index("Players:\n")
    actors_start = source_yaml.index("Actors:\n", players_start)
    map_yaml = source_yaml[:players_start] + PLAYERS + source_yaml[actors_start:]
    map_yaml += "\nRules: rules.yaml\n"

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("map.yaml", map_yaml)
        archive.writestr("rules.yaml", RULES)
        archive.write(SOURCE / "map.bin", "map.bin")
        archive.write(SOURCE / "map.png", "map.png")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    build(output)
    print(f"AI validation map: {output}")
    if args.install:
        INSTALL.write_bytes(output.read_bytes())
        print(f"Installed: {INSTALL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
