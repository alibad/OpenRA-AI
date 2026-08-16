from __future__ import annotations

import hashlib
import os
import runpy
import struct
import subprocess
import unittest
import wave
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "engine" / "openra"
UTILITY = ENGINE / "bin" / "OpenRA.Utility.exe"
BITS = ENGINE / "mods" / "ra" / "bits"
FRAMES = ROOT / "generated" / "red-sea-sprites"
MISSION = ROOT / "generated" / "missions" / "jizan-corridor-2026.oramap"
INFANTRY = ("sang", "sajtac", "saat", "falcon1", "ymr", "yrpg", "yspot", "wadighost")
PACKED_INFANTRY_FRAMES = 713


class RedSeaInfantryAssetTests(unittest.TestCase):
    def _resolved(self, actor: str) -> str:
        environment = os.environ.copy()
        environment["ENGINE_DIR"] = ".."
        environment["DOTNET_ROLL_FORWARD"] = "Major"
        return subprocess.run(
            [str(UTILITY), "ra", "--resolved-rules", actor, str(MISSION)],
            cwd=ENGINE,
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        ).stdout

    def test_every_role_has_a_full_native_state_package_and_opaque_cameo(self) -> None:
        for name in INFANTRY:
            sprite = BITS / f"{name}.shp"
            icon = BITS / f"{name}icon.shp"
            self.assertGreater(sprite.stat().st_size, 10_000, name)
            self.assertGreater(icon.stat().st_size, 1_000, name)
            with sprite.open("rb") as stream:
                self.assertEqual(struct.unpack("<H", stream.read(2))[0], PACKED_INFANTRY_FRAMES, name)
            with icon.open("rb") as stream:
                self.assertEqual(struct.unpack("<H", stream.read(2))[0], 1, name)

            cameo = Image.open(FRAMES / f"{name}icon" / f"{name}icon-0000.png")
            self.assertEqual(cameo.size, (64, 48))
            self.assertNotIn(0, cameo.tobytes(), f"{name} cameo must not have transparent holes")

    def test_directional_run_and_fire_states_are_independently_articulated(self) -> None:
        for name in INFANTRY:
            paths = sorted((FRAMES / name).glob(f"{name}-*.png"))
            self.assertEqual(len(paths), 342, name)
            for start, length, facings in ((0, 1, 8), (16, 6, 8), (64, 8, 8), (144, 4, 8), (192, 8, 8)):
                hashes = set()
                for facing in range(facings):
                    frame = Image.open(paths[start + facing * length]).convert("RGBA")
                    hashes.add(hashlib.sha256(frame.tobytes()).digest())
                self.assertEqual(len(hashes), 8, f"{name} state starting {start} must author all facings")

            run_hashes = {
                hashlib.sha256(Image.open(paths[16 + phase]).convert("RGBA").tobytes()).digest()
                for phase in range(6)
            }
            fire_hashes = {
                hashlib.sha256(Image.open(paths[64 + phase]).convert("RGBA").tobytes()).digest()
                for phase in range(8)
            }
            self.assertGreaterEqual(len(run_hashes), 5, f"{name} needs a real run cycle")
            self.assertGreaterEqual(len(fire_hashes), 5, f"{name} needs a real firing cycle")

    def test_muzzle_flash_follows_native_cardinal_handedness(self) -> None:
        renderer = runpy.run_path(str(ROOT / "scripts" / "red_sea_infantry.py"))
        style = renderer["STYLES"]["sang"]
        team = ((215, 190, 105), (170, 154, 85), (134, 113, 56), (85, 77, 36))
        make_frame = renderer["_frame"]
        centroids = []
        for facing in (0, 2, 4, 6):
            resting = make_frame(style, team, "shoot", facing, 0, 8).convert("RGBA")
            firing = make_frame(style, team, "shoot", facing, 2, 8).convert("RGBA")
            changed_bright = []
            for y in range(firing.height):
                for x in range(firing.width):
                    now = firing.getpixel((x, y))
                    before = resting.getpixel((x, y))
                    if now[3] > 100 and now[0] > 175 and now[1] > 130 and now[2] < 115 and now != before:
                        changed_bright.append((x, y))
            self.assertGreater(len(changed_bright), 0)
            centroids.append((
                sum(x for x, _ in changed_bright) / len(changed_bright),
                sum(y for _, y in changed_bright) / len(changed_bright),
            ))

        north, east, south, west = centroids
        self.assertLess(east[0], north[0] - 4)
        self.assertGreater(south[1], north[1] + 4)
        self.assertGreater(west[0], north[0] + 4)

    def test_all_eight_roles_resolve_their_faction_and_gameplay_contracts(self) -> None:
        expectations = {
            "SANG": ("~infantry.saudi", "Weapon: RedSeaGuardRifle", "HP: 7800"),
            "SAJTAC": ("~infantry.saudi", "Weapon: RedSeaJTACDesignator", "DetectCloaked:"),
            "SAAT": ("~infantry.saudi", "Weapon: RedSeaATGM", "Speed: 43"),
            "FALCON1": ("BuildLimit: 1", "AirstrikePower@PRECISION:", "UnitType: f15sa.strike"),
            "YMR": ("~infantry.yemen", "Weapon: RedSeaMountainRifle", "UncloakOn: Attack, Move, Damage"),
            "YRPG": ("~infantry.yemen", "Weapon: RedSeaRPG", "RangeMultiplier@DRONE_GUIDANCE:"),
            "YSPOT": ("ProximityExternalCondition@DRONE_GUIDANCE:", "Condition: redsea-drone-guidance", "Range: 10c0"),
            "WADIGHOST": (
                "BuildLimit: 1",
                "BuildDuration: 600",
                "Infiltrates:",
                "Weapon: RedSeaRemoteDemolition",
            ),
        }
        for actor, needles in expectations.items():
            resolved = self._resolved(actor)
            for needle in needles:
                self.assertIn(needle, resolved, f"{actor}: {needle}")

    def test_jtac_and_spotter_support_is_systemic_and_visible(self) -> None:
        rules = (ENGINE / "mods" / "ra" / "rules" / "red-sea.yaml").read_text(encoding="utf-8")
        weapons = (ENGINE / "mods" / "ra" / "weapons" / "red-sea.yaml").read_text(encoding="utf-8")
        self.assertIn("TargetTypes: RedSeaDesignated", rules)
        self.assertIn("WithColoredOverlay@REDSEA_DESIGNATED:", rules)
        self.assertIn("Warhead@MARK: GrantExternalCondition", weapons)
        self.assertGreaterEqual(weapons.count("ValidTargets: RedSeaDesignated"), 4)
        ymlr = self._resolved("YMLR")
        self.assertIn("Modifier: 125", ymlr)
        self.assertIn("Modifier: 72", ymlr)

    def test_ai_builders_include_the_entire_infantry_roster(self) -> None:
        player = self._resolved("Player")
        for name in INFANTRY:
            minimum = 2 if name in {"sajtac", "falcon1", "yspot", "wadighost"} else 5
            self.assertGreaterEqual(player.count(f"\t\t{name}:"), minimum, name)

    def test_bilingual_role_voices_and_original_combat_sounds_are_openra_ready(self) -> None:
        voice_names = (
            "rsa-inf-select-ar.wav", "rsa-inf-select-en.wav",
            "rsa-jtac-action-ar.wav", "rsa-jtac-action-en.wav",
            "rsa-falcon-select-ar.wav", "rsa-falcon-select-en.wav",
            "rye-inf-select-ar.wav", "rye-inf-select-en.wav",
            "rye-spot-action-ar.wav", "rye-spot-action-en.wav",
            "rye-ghost-select-ar.wav", "rye-ghost-select-en.wav",
        )
        sfx_names = (
            "redsea-guard-rifle.wav", "redsea-mountain-rifle.wav",
            "redsea-atgm-launch.wav", "redsea-rpg-launch.wav",
            "redsea-suppressed.wav", "redsea-remote-charge.wav",
        )
        for name in (*voice_names, *sfx_names):
            path = BITS / name
            self.assertGreater(path.stat().st_size, 4_000, name)
            with wave.open(str(path), "rb") as audio:
                self.assertEqual(audio.getframerate(), 44_100, name)
                self.assertEqual(audio.getnchannels(), 1, name)
                self.assertEqual(audio.getsampwidth(), 2, name)
                self.assertGreater(audio.getnframes(), 4_000, name)

    def test_original_concept_sheets_are_preserved_as_source_assets(self) -> None:
        root = ROOT / "assets" / "red-sea-2026" / "infantry-concepts"
        for name in ("saudi-infantry-concept.png", "yemen-infantry-concept.png"):
            path = root / name
            self.assertGreater(path.stat().st_size, 1_000_000, name)
            with Image.open(path) as image:
                self.assertGreaterEqual(image.width, 1500)
                self.assertGreaterEqual(image.height, 800)


if __name__ == "__main__":
    unittest.main()
