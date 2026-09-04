from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "apps/installer/ra2/modern-factions"
sys.path.insert(0, str(ROOT / "scripts"))
import ra2_faction_voxels as voxels


def decode(data):
    """Independent reader for the native single-section VXL run encoding."""
    magic, version, sections, tails, body_size = struct.unpack_from("<16s4I", data)
    if magic != b"Voxel Animation\0" or sections != 1 or tails != 1:
        raise ValueError("Not a single-section VXL")
    offset = 802 + 28
    footer = struct.unpack_from("<3If12f6f4B", data, offset + body_size)
    sx, sy, sz, normal_type = footer[-4:]
    starts = struct.unpack_from(f"<{sx * sy}i", data, offset)
    spans = offset + sx * sy * 8
    result = {}
    for i, start in enumerate(starts):
        if start == -1:
            continue
        cursor, z = spans + start, 0
        while z < sz:
            skip, count = data[cursor:cursor + 2]
            cursor += 2
            z += skip
            for h in range(count):
                result[i % sx, i // sx, z + h] = tuple(data[cursor:cursor + 2])
                cursor += 2
            if data[cursor] != count:
                raise ValueError("Invalid duplicate span length")
            cursor += 1
            z += count
            if z > sz:
                raise ValueError("Span extends past voxel bounds")
    return footer, result


class RA2ModernFactionTests(unittest.TestCase):
    def test_native_voxels_round_trip_and_match_manifest(self):
        manifest = json.loads((ASSETS / "voxel-manifest.json").read_text())
        self.assertEqual(len(manifest["models"]), 21)  # 12 bodies + 9 independent turrets
        for name, expected in manifest["models"].items():
            with self.subTest(model=name):
                data = (ASSETS / "voxels" / (name + ".vxl")).read_bytes()
                footer, occupied = decode(data)
                self.assertEqual(footer[-1], 4)
                self.assertAlmostEqual(footer[3], 1 / 12, places=6)
                self.assertEqual(list(footer[-4:-1]), expected["size"])
                self.assertEqual(len(occupied), expected["occupied_voxels"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected["sha256"])
                self.assertGreater(len({v[1] for v in occupied.values()}), 5)
                self.assertTrue(all(0 < v[0] < 256 and 0 <= v[1] < 244 for v in occupied.values()))
                self.assertTrue(all(0 <= p[i] < footer[-4+i] for p in occupied for i in range(3)))
                hva = (ASSETS / "voxels" / (name + ".hva")).read_bytes()
                self.assertEqual(struct.unpack_from("<2I", hva, 16), (1, 1))
                self.assertEqual(struct.unpack_from("<12f", hva, 40), voxels.IDENTITY)

    def test_every_complete_unit_has_remap_pixels(self):
        models = json.loads((ASSETS / "voxel-manifest.json").read_text())["models"]
        for actor in voxels.models():
            count = sum(info["remap_voxels"] for name, info in models.items() if name in (actor, actor + "tur"))
            self.assertGreater(count, 20, actor)
        self.assertEqual(len((ASSETS / "voxels/modern.pal").read_bytes()), 768)

    def test_authored_palette_uses_bounded_lighting_for_units_and_husks(self):
        rules = (ASSETS / "common.yaml").read_text()
        self.assertEqual(rules.count("LightAmbientColor: -0.3,-0.3,-0.3"), 3)
        self.assertEqual(rules.count("LightDiffuseColor: 0.75,0.75,0.75"), 3)
        # Native model.frag includes the homogeneous normal component in its
        # dot product: maximum intensity is ambient + 2 * diffuse, not A + D.
        self.assertLessEqual(-0.3 + 2 * 0.75, 1.2)

    def test_geometry_axes_and_reproducible_export(self):
        self.assertEqual(voxels.coordinates((1, -2, 3)), (2, 1, 3))
        meshes = voxels.models()
        pal, colors = voxels.palette(meshes)
        size, lower, occupied = voxels.voxelize(meshes["r2qilintur"[:-3]][1], colors, voxels.normal_table())
        data = voxels.encode_vxl(size, lower, occupied, pal)
        self.assertEqual(data, (ASSETS / "voxels/r2qilintur.vxl").read_bytes())

    def test_icons_and_previews_are_native_size(self):
        for actor in voxels.models():
            with Image.open(ASSETS / "icons" / (actor + ".png")) as icon:
                self.assertEqual(icon.size, (60, 48))
                self.assertGreater(len(icon.convert("RGB").getcolors(2881)), 500)
        for country in ("china", "iran", "turkey"):
            with Image.open(ASSETS / "previews" / (country + ".png")) as preview:
                self.assertEqual(preview.size, (512, 512))

    def test_factions_are_independent_complete_packs_with_native_starts_and_ai(self):
        catalog = (ASSETS / "experiences.yaml").read_text()
        self.assertIn("DefaultProfile: ra2-modern", catalog)
        self.assertIn("ra2-classic:", catalog)
        self.assertIn("Components: ra2-china, ra2-iran, ra2-turkey", catalog)
        for country, mcv, factory in (("china", "amcv", "gaweap"), ("iran", "smcv", "naweap"), ("turkey", "amcv", "gaweap")):
            rules = (ASSETS / (country + ".yaml")).read_text()
            self.assertIn("Faction@" + country, rules)
            self.assertIn("Factions: " + country, rules)
            self.assertIn("BaseActor: " + mcv, rules)
            self.assertEqual(rules.count("StartingUnits@" + country + "-"), 4)
            self.assertEqual(rules.count("Prerequisites: ~faction." + country + ", " + factory), 4)
            for profile in ("normal", "medium", "rush", "turtle", "naval"):
                self.assertIn("UnitBuilderBotModule@" + profile, rules)
            self.assertIn("SpawnActorOnDeath:", rules)

    def test_new_ui_strings_have_translation_keys(self):
        messages = (ASSETS / "messages.ftl").read_text()
        for actor in voxels.models():
            self.assertIn("ra2-" + actor + "-name =", messages)
            self.assertIn("ra2-" + actor + "-description =", messages)

    def test_air_defense_acquires_air_and_drone_production_opens_factory_roof(self):
        for country in ("china", "iran", "turkey"):
            rules = (ASSETS / (country + ".yaml")).read_text()
            self.assertIn("GrantConditionOnProduction@" + country + "-drone", rules)
            self.assertIn("Condition: roof-open", rules)
            if country != "turkey":
                self.assertIn("Inherits@AUTOTARGET: ^AutoTargetAir", rules)

    def test_production_tests_cannot_count_pre_spawned_tanks(self):
        script = (ROOT / "scripts/validate-ra2.py").read_text()
        self.assertIn("if require_unit:", script)
        self.assertIn("StartingUnitsClass: none", script)
        ai = (ASSETS / "aircraft-ai.yaml").read_text()
        self.assertEqual(ai.count("InitialBuildOrder:"), 5)


if __name__ == "__main__":
    unittest.main()
