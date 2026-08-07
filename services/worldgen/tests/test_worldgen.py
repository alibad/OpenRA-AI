from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from openra_ai_worldgen import GeoSelection, MissionGenerator
from openra_ai_worldgen.validator import validate_package


class WorldgenTests(unittest.TestCase):
    fixture = Path(__file__).parent / "fixtures" / "overpass-river.json"

    def test_generates_valid_playable_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            selection = GeoSelection(24.7136, 46.7219, "Riyadh River Test", seed=42)
            result = MissionGenerator(self.fixture).generate(selection, Path(directory))
            self.assertTrue(result.validation.valid)
            with ZipFile(result.package_path) as archive:
                self.assertTrue({"map.yaml", "map.bin", "map.png", "briefing.md", "openra-ai-manifest.json"} <= set(archive.namelist()))
                self.assertIn("Tileset: TEMPERAT", archive.read("map.yaml").decode())
                manifest = json.loads(archive.read("openra-ai-manifest.json"))
                self.assertTrue(manifest["validation"]["valid"])

    def test_binary_and_package_are_deterministic(self) -> None:
        selection = GeoSelection(24.7136, 46.7219, "Repeatable", seed=99)
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            one = MissionGenerator(self.fixture).generate(selection, Path(first)).package_path
            two = MissionGenerator(self.fixture).generate(selection, Path(second)).package_path
            with ZipFile(one) as a, ZipFile(two) as b:
                for name in ("map.yaml", "map.bin", "map.png"):
                    self.assertEqual(hashlib.sha256(a.read(name)).digest(), hashlib.sha256(b.read(name)).digest())

    def test_validator_rejects_non_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.oramap"
            path.write_text("not a zip", encoding="utf-8")
            self.assertFalse(validate_package(path).valid)

    def test_invalid_coordinates_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                MissionGenerator(allow_network=False).generate(GeoSelection(100, 0), Path(directory))


if __name__ == "__main__":
    unittest.main()
