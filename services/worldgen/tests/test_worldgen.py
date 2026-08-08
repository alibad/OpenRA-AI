from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock
from zipfile import ZipFile

from openra_ai_worldgen import GeoSelection, MissionGenerator
from openra_ai_worldgen.models import TerrainAnalysis
from openra_ai_worldgen.osm import GeoFeature, fetch_features, parse_overpass
from openra_ai_worldgen.package import compile_map_binary
from openra_ai_worldgen.raster import ROAD, WATER, build_terrain
from openra_ai_worldgen.server import create_server
from openra_ai_worldgen.validator import validate_package


class WorldgenTests(unittest.TestCase):
    fixture = Path(__file__).parent / "fixtures" / "overpass-river.json"

    def test_generates_valid_playable_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            selection = GeoSelection(24.7136, 46.7219, "Riyadh River Test", location_name="Riyadh, Saudi Arabia", seed=42)
            result = MissionGenerator(self.fixture).generate(selection, Path(directory))
            self.assertTrue(result.validation.valid)
            with ZipFile(result.package_path) as archive:
                self.assertTrue({"map.yaml", "map.bin", "map.png", "briefing.md", "openra-ai-manifest.json"} <= set(archive.namelist()))
                self.assertIn("Tileset: TEMPERAT", archive.read("map.yaml").decode())
                manifest = json.loads(archive.read("openra-ai-manifest.json"))
                self.assertTrue(manifest["validation"]["valid"])
                self.assertEqual(manifest["selection"]["location_name"], "Riyadh, Saudi Arabia")
                self.assertIn("Riyadh, Saudi Arabia", archive.read("briefing.md").decode())

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

    def test_offline_generation_does_not_invent_water(self) -> None:
        plan = build_terrain(
            GeoSelection(24.638916, 46.71601, map_size=64),
            [],
            TerrainAnalysis(biome="desert"),
        )
        self.assertEqual(plan.tileset, "DESERT")
        self.assertFalse(any(WATER in row for row in plan.cells))

    def test_real_road_cells_are_written_as_openra_road_tiles(self) -> None:
        selection = GeoSelection(24.638916, 46.71601, map_size=64)
        road = GeoFeature("road", ((24.63, 46.70), (24.65, 46.73)), tags=(("highway", "primary"),))
        plan = build_terrain(selection, [road], TerrainAnalysis(biome="desert"))
        binary = compile_map_binary(plan, selection.seed)
        road_tiles = 0
        offset = 17
        for x in range(plan.width):
            for y in range(plan.height):
                tile_id = int.from_bytes(binary[offset:offset + 2], "little")
                if plan.cells[y][x] == ROAD:
                    self.assertIn(tile_id, {164, 165})
                    road_tiles += 1
                offset += 3
        self.assertGreater(road_tiles, 0)

    def test_intermittent_waterways_are_not_permanent_water(self) -> None:
        features = parse_overpass({"elements": [{
            "type": "way",
            "tags": {"waterway": "river", "intermittent": "yes"},
            "geometry": [{"lat": 24.61, "lon": 46.69}, {"lat": 24.62, "lon": 46.70}],
        }]})
        self.assertEqual(features[0].kind, "dry-river")

    def test_geographic_acquisition_falls_back_to_second_overpass_instance(self) -> None:
        payload = self.fixture.read_bytes()
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = payload
        with mock.patch(
            "openra_ai_worldgen.osm.urllib.request.urlopen",
            side_effect=[urllib.error.URLError("primary unavailable"), response],
        ) as urlopen:
            features = fetch_features(GeoSelection(24.7136, 46.7219), timeout=0.1)
        self.assertEqual(urlopen.call_count, 2)
        self.assertGreater(len(features), 0)

    def test_world_studio_generates_installs_and_downloads_a_map(self) -> None:
        with tempfile.TemporaryDirectory() as output, tempfile.TemporaryDirectory() as install:
            server = create_server("127.0.0.1", 0, Path(output), Path(install))
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urllib.request.urlopen(base + "/", timeout=3) as response:
                    self.assertIn(b"Mission Studio", response.read())
                body = json.dumps({
                    "latitude": 24.7136,
                    "longitude": 46.7219,
                    "title": "HTTP Studio Test",
                    "location_name": "Riyadh, Saudi Arabia",
                    "map_size": 64,
                    "seed": 7,
                }).encode()
                request = urllib.request.Request(
                    base + "/v1/missions/generate",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )
                fixture_generator = MissionGenerator(self.fixture)
                with mock.patch("openra_ai_worldgen.server.MissionGenerator", return_value=fixture_generator):
                    with urllib.request.urlopen(request, timeout=5) as response:
                        payload = json.loads(response.read())
                installed = Path(payload["installed_path"])
                self.assertTrue(installed.is_file())
                with urllib.request.urlopen(base + payload["download_url"], timeout=3) as response:
                    self.assertTrue(response.read().startswith(b"PK"))
            finally:
                server.shutdown()
                server.server_close()
                worker.join()

    def test_geocode_requests_english_place_names(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps([{
            "display_name": "الرياض، منطقة الرياض، السعودية",
            "namedetails": {"name:en": "Riyadh"},
            "lat": "24.638916",
            "lon": "46.71601",
        }]).encode()
        with tempfile.TemporaryDirectory() as output, tempfile.TemporaryDirectory() as install:
            server = create_server("127.0.0.1", 0, Path(output), Path(install))
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with mock.patch("openra_ai_worldgen.server.urlopen", return_value=response) as urlopen:
                    with urllib.request.urlopen(base + "/v1/geocode?query=Riyadh", timeout=3) as result:
                        payload = json.loads(result.read())

                request = urlopen.call_args.args[0]
                self.assertIn("accept-language=en", request.full_url)
                self.assertIn("namedetails=1", request.full_url)
                self.assertEqual(request.get_header("Accept-language"), "en")
                self.assertEqual(payload["name"], "Riyadh")
                self.assertEqual(payload["native_name"], "الرياض، منطقة الرياض، السعودية")
            finally:
                server.shutdown()
                server.server_close()
                worker.join()

    def test_map_tile_proxy_identifies_itself_and_caches_for_reuse(self) -> None:
        tile = b"\x89PNG\r\n\x1a\n" + b"cached-tile"
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = tile
        with tempfile.TemporaryDirectory() as output, tempfile.TemporaryDirectory() as install:
            server = create_server("127.0.0.1", 0, Path(output), Path(install))
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with mock.patch("openra_ai_worldgen.server.urlopen", return_value=response) as urlopen:
                    with urllib.request.urlopen(base + "/v1/map-tile?latitude=24.638916&longitude=46.71601&zoom=11", timeout=3) as result:
                        self.assertEqual(result.read(), tile)
                    with urllib.request.urlopen(base + "/v1/map-tile?latitude=24.638916&longitude=46.71601&zoom=11", timeout=3) as result:
                        self.assertEqual(result.read(), tile)

                self.assertEqual(urlopen.call_count, 1)
                request = urlopen.call_args.args[0]
                self.assertEqual(request.full_url, "https://tile.openstreetmap.org/11/1289/879.png")
                self.assertIn("OpenRA-AI/0.1", request.get_header("User-agent"))
            finally:
                server.shutdown()
                server.server_close()
                worker.join()


if __name__ == "__main__":
    unittest.main()
