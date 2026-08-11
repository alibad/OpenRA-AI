from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock
from zipfile import ZipFile

from openra_ai_worldgen import GeoSelection, MissionGenerator
from openra_ai_worldgen.models import TerrainAnalysis
from openra_ai_worldgen.native import generation_options, terrain_profile
from openra_ai_worldgen.osm import fetch_features, parse_overpass
from openra_ai_worldgen.raster import WATER, build_terrain
from openra_ai_worldgen.scenarios import FACTIONS, scenario_manifest
from openra_ai_worldgen.server import create_server
from openra_ai_worldgen.terrain import _zoom_for_radius, fetch_terrain_view
from openra_ai_worldgen.validator import validate_package


class WorldgenTests(unittest.TestCase):
    fixture = Path(__file__).parent / "fixtures" / "overpass-river.json"

    def test_red_sea_scenario_contract_is_source_dated(self) -> None:
        selection = GeoSelection(
            16.8892,
            42.5511,
            scenario_id="jizan-corridor-2026",
            player_faction="saudi",
            opponent_faction="yemen",
            mission_archetype="convoy-defense",
        ).validated()
        scenario = scenario_manifest(selection.scenario_id)

        self.assertIsNotNone(scenario)
        self.assertEqual(scenario["factual_cutoff"], "2026-08-11")
        self.assertEqual(scenario["player_faction"], "saudi")
        self.assertGreaterEqual(len(scenario["objectives"]), 4)
        self.assertGreaterEqual(len(scenario["sources"]), 2)
        self.assertEqual(FACTIONS["saudi"].openra_side, "Allies")
        self.assertEqual(FACTIONS["yemen"].openra_side, "Soviet")

    def test_unknown_scenario_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown scenario_id"):
            GeoSelection(16.8892, 42.5511, scenario_id="missing").validated()

    def test_scenario_rejects_a_conflicting_country(self) -> None:
        with self.assertRaisesRegex(ValueError, "player_faction conflicts"):
            GeoSelection(
                16.8892,
                42.5511,
                scenario_id="jizan-corridor-2026",
                player_faction="yemen",
            ).validated()

    def test_generates_valid_playable_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            selection = GeoSelection(24.7136, 46.7219, "Riyadh River Test", location_name="Riyadh, Saudi Arabia", seed=42)
            result = MissionGenerator(self.fixture).generate(selection, Path(directory))
            self.assertTrue(result.validation.valid)
            with ZipFile(result.package_path) as archive:
                self.assertTrue({"map.yaml", "map.bin", "map.png", "briefing.md", "openra-ai-manifest.json"} <= set(archive.namelist()))
                self.assertIn("Author: OpenRA AI / OpenRA Classic Generator", archive.read("map.yaml").decode())
                manifest = json.loads(archive.read("openra-ai-manifest.json"))
                self.assertTrue(manifest["validation"]["valid"])
                self.assertEqual(manifest["generator"]["engine_generator"], "classic")
                self.assertTrue(manifest["generator"]["passability"]["valid"])
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

    def test_generation_reports_real_pipeline_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stages: list[tuple[int, str]] = []
            MissionGenerator(self.fixture).generate(
                GeoSelection(24.7136, 46.7219, "Progress Test", map_size=64),
                Path(directory),
                progress=lambda stage, message: stages.append((stage, message)),
            )
        self.assertEqual([stage for stage, _ in stages], [1, 4, 5])
        self.assertTrue(all(message for _, message in stages))

    def test_validator_rejects_non_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.oramap"
            path.write_text("not a zip", encoding="utf-8")
            self.assertFalse(validate_package(path).valid)

    def test_invalid_coordinates_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                MissionGenerator(allow_network=False).generate(GeoSelection(100, 0), Path(directory))

    def test_invalid_imagery_style_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GeoSelection(24.638916, 46.71601, imagery_style="street").validated()

    def test_defaults_favor_adaptive_evidence_and_playability(self) -> None:
        selection = GeoSelection(24.638916, 46.71601)
        self.assertEqual(selection.imagery_style, "auto")
        self.assertEqual(selection.generation_mode, "playability-first")
        self.assertEqual(selection.radius_m, 500)

    def test_tactical_earth_view_uses_close_battlefield_crop(self) -> None:
        selection = GeoSelection(24.638916, 46.71601, radius_m=500)
        self.assertEqual(_zoom_for_radius(selection, 512, maximum_zoom=16), 16)

    def test_satellite_view_uses_eox_imagery_and_reports_provenance(self) -> None:
        import io
        from PIL import Image

        image = Image.new("RGB", (256, 256), (137, 108, 68))
        encoded = io.BytesIO()
        image.save(encoded, format="JPEG")
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = encoded.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("openra_ai_worldgen.terrain.urlopen", return_value=response) as urlopen:
                view = fetch_terrain_view(
                    GeoSelection(24.638916, 46.71601, imagery_style="satellite"),
                    Path(directory),
                    output_size=128,
                )

        self.assertTrue(view.image.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(view.style, "satellite")
        self.assertIn("Sentinel-2", view.provider)
        self.assertIn("s2cloudless-2025_3857", urlopen.call_args.args[0].full_url)

    def test_hybrid_view_adds_map_detail_to_satellite(self) -> None:
        import io
        from PIL import Image

        satellite = Image.new("RGB", (256, 256), (150, 120, 90))
        satellite_bytes = io.BytesIO()
        satellite.save(satellite_bytes, format="JPEG")
        mapped = Image.new("RGB", (256, 256), (255, 255, 255))
        for x in range(96, 160):
            for y in range(96, 160):
                mapped.putpixel((x, y), (40, 40, 40))
        map_bytes = io.BytesIO()
        mapped.save(map_bytes, format="PNG")

        def response_for(request, timeout=15):
            del timeout
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = (
                satellite_bytes.getvalue() if request.full_url.endswith(".jpg") else map_bytes.getvalue()
            )
            return response

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("openra_ai_worldgen.terrain.urlopen", side_effect=response_for) as urlopen:
                view = fetch_terrain_view(
                    GeoSelection(24.638916, 46.71601, radius_m=500, imagery_style="hybrid"),
                    Path(directory),
                    output_size=128,
                )

        self.assertEqual(view.style, "hybrid")
        self.assertIn("OpenTopoMap", view.provider)
        self.assertTrue(any(call.args[0].full_url.endswith(".jpg") for call in urlopen.call_args_list))
        self.assertTrue(any(call.args[0].full_url.endswith(".png") for call in urlopen.call_args_list))

    def test_auto_view_uses_clear_map_at_tactical_scale(self) -> None:
        import io
        from PIL import Image

        mapped = Image.new("RGB", (256, 256), (245, 245, 245))
        encoded = io.BytesIO()
        mapped.save(encoded, format="PNG")
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = encoded.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("openra_ai_worldgen.terrain.urlopen", return_value=response) as urlopen:
                view = fetch_terrain_view(
                    GeoSelection(24.638916, 46.71601, radius_m=500, imagery_style="auto"),
                    Path(directory),
                    output_size=128,
                )

        self.assertEqual(view.style, "terrain")
        self.assertEqual(view.provider, "OpenTopoMap")
        self.assertTrue(all(call.args[0].full_url.endswith(".png") for call in urlopen.call_args_list))

    def test_auto_view_uses_unmodified_satellite_for_regional_scale(self) -> None:
        import io
        from PIL import Image

        image = Image.new("RGB", (256, 256), (137, 108, 68))
        encoded = io.BytesIO()
        image.save(encoded, format="JPEG")
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = encoded.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("openra_ai_worldgen.terrain.urlopen", return_value=response):
                view = fetch_terrain_view(
                    GeoSelection(24.638916, 46.71601, radius_m=2000, imagery_style="auto"),
                    Path(directory),
                    output_size=128,
                )

        self.assertEqual(view.style, "satellite")

    def test_offline_generation_does_not_invent_water(self) -> None:
        plan = build_terrain(
            GeoSelection(24.638916, 46.71601, map_size=64),
            [],
            TerrainAnalysis(biome="desert"),
        )
        self.assertEqual(plan.tileset, "DESERT")
        self.assertFalse(any(WATER in row for row in plan.cells))

    def test_earth_analysis_selects_native_openra_generator_options(self) -> None:
        selection = GeoSelection(24.638916, 46.71601, map_size=96, generation_mode="playability-first")
        analysis = TerrainAnalysis(biome="desert", urban_density=0.7, relief="flat")
        options = generation_options(selection, analysis)
        self.assertEqual(options["tileset"], "DESERT")
        self.assertEqual(options["terrain"], "Plots")
        self.assertEqual(options["symmetry"], "2Rotations")
        self.assertTrue(options["roads"])
        self.assertTrue(options["deny-walled-areas"])

    def test_mountainous_water_uses_native_mountain_lakes_profile(self) -> None:
        analysis = TerrainAnalysis(relief="mountainous", water_confidence=0.8)
        self.assertEqual(terrain_profile(analysis), "MountainLakes")

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

    def test_world_studio_exposes_pollable_generation_progress(self) -> None:
        with tempfile.TemporaryDirectory() as output, tempfile.TemporaryDirectory() as install:
            server = create_server("127.0.0.1", 0, Path(output), Path(install))
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                body = json.dumps({
                    "latitude": 24.7136,
                    "longitude": 46.7219,
                    "title": "Async Studio Test",
                    "location_name": "Riyadh, Saudi Arabia",
                    "map_size": 64,
                    "seed": 8,
                }).encode()
                request = urllib.request.Request(
                    base + "/v1/missions/generate-async",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )
                fixture_generator = MissionGenerator(self.fixture)
                with mock.patch("openra_ai_worldgen.server.MissionGenerator", return_value=fixture_generator):
                    with urllib.request.urlopen(request, timeout=3) as response:
                        accepted = json.loads(response.read())
                    for _ in range(200):
                        with urllib.request.urlopen(base + accepted["poll_url"], timeout=3) as response:
                            job = json.loads(response.read())
                        if job["state"] in {"succeeded", "failed"}:
                            break
                        time.sleep(0.025)

                self.assertEqual(job["state"], "succeeded", job)
                self.assertEqual(job["stage"], 6)
                self.assertTrue(Path(job["result"]["installed_path"]).is_file())
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
