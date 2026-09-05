from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from openra_ai_companion.game_content import import_content, ra2_content_root
from openra_ai_companion.game_runtime import GameRuntime
from openra_ai_companion.generated.rl_bridge_pb2 import GameObservation
from openra_ai_companion.models import GameSnapshot, Unit
from openra_ai_companion.strategy import strategic_profile
from openra_ai_companion.core import Companion
from openra_ai_companion.router import AIRouter
from openra_ai_companion.settings import Settings
from openra_ai_companion.strategy_contracts import detect_strategy_intent

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("prepare_ra2", ROOT / "scripts/prepare-ra2.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class RA2IntegrationTests(unittest.TestCase):
    def test_release_compatibility_lock_matches_checked_out_engine(self):
        manifest = json.loads((ROOT / "apps/installer/ra2/upstream.json").read_text())
        engine_commit = subprocess.check_output(
            ["git", "-C", str(ROOT / "engine/openra"), "rev-parse", "HEAD"], text=True).strip()
        self.assertEqual(manifest["engine_commit"], engine_commit,
                         "Update the RA2 compatibility lock after validating an engine upgrade")

    def test_modern_flags_keep_native_pixels_and_preserve_upstream_atlas(self):
        original = Image.new("RGBA", (256, 256), (12, 34, 56, 128))
        with Image.open(ROOT / "engine/openra/mods/ra/uibits/glyphs-redsea.png") as source:
            atlas, regions = prepare.extend_flag_atlas(original, source)
            self.assertEqual(atlas.size, (256, 512))
            self.assertEqual(atlas.crop((0, 0, 256, 256)).tobytes(), original.tobytes())
            for i, (country, x, y) in enumerate(prepare.MODERN_FLAGS):
                self.assertIn(f"{country}: {i * 30}, 256, 30, 15\n", regions)
                expected = source.crop((x, y, x + 30, y + 15)).convert("RGBA")
                actual = atlas.crop((i * 30, 256, (i + 1) * 30, 271))
                self.assertEqual(actual.tobytes(), expected.tobytes(), country)
            self.assertIsNone(atlas.crop((90, 256, 256, 512)).getbbox())
            self.assertIsNone(atlas.crop((0, 271, 90, 512)).getbbox())

    def test_modern_flags_fit_lobby_rows_without_touching_country_names(self):
        chrome = (ROOT / "engine/openra/mods/common/chrome/lobby-players.yaml").read_text()
        template = chrome.split("ScrollPanel@FACTION_DROPDOWN_TEMPLATE:", 1)[1].split("ScrollItem@TEMPLATE:", 1)[1]
        flag, label = template.split("Image@FLAG:", 1)[1].split("Label@LABEL:", 1)
        def value(block, key):
            return int(re.search(rf"^\s+{key}: (\d+)$", block, re.MULTILINE).group(1))
        width, height = prepare.FLAG_SIZE
        self.assertLessEqual(width, value(flag, "Width"))
        self.assertLessEqual(height, value(flag, "Height"))
        for scale in (1, 1.5, 2, 3):
            self.assertGreaterEqual((value(label, "X") - value(flag, "X") - width) * scale, 5 * scale)
            self.assertGreaterEqual((value(template, "Height") - value(flag, "Y") - height) * scale, 5 * scale)

    def test_flag_atlas_rejects_missing_source_regions(self):
        with self.assertRaisesRegex(ValueError, "missing the china flag"):
            prepare.extend_flag_atlas(Image.new("RGBA", (256, 256)), Image.new("RGBA", (30, 15)))

    def test_game_identity_and_power_plant_questions_are_not_strategy_queries(self):
        for question in ("What country am I playing?", "Which faction am I playing?",
                         "What game am I playing?", "Which power plants do I own?"):
            with self.subTest(question=question):
                self.assertEqual(detect_strategy_intent(question), ("", None))
        self.assertEqual(detect_strategy_intent("What strategy are we playing?"), ("query", None))
        self.assertEqual(detect_strategy_intent("How are we playing?"), ("query", None))

    def test_wire_schema_identifies_base_game_and_actor_names(self):
        snapshot = GameObservation(mod_id="ra2", actor_names={"e1": "GI", "e2": "Conscript"})
        decoded = GameObservation.FromString(snapshot.SerializeToString())
        self.assertEqual(decoded.mod_id, "ra2")
        self.assertEqual(decoded.actor_names["e2"], "Conscript")

    def test_ra2_observation_does_not_mislabel_units_as_ra1(self):
        snapshot = GameSnapshot.from_dict({
            "mod_id": "ra2", "tick": 1, "actor_names": {"e1": "GI", "e2": "Conscript", "gapowr": "Power Plant"},
            "units": [{"actor_id": 10, "type": "e2"}], "available_production": ["gapowr"],
        })
        self.assertEqual(snapshot.compact()["own_unit_types"], ["Conscript"])
        self.assertEqual(snapshot.action_context()["own_units"][0]["display_name"], "Conscript")
        self.assertEqual(snapshot.actor_name("unknown_ra2_actor"), "unknown_ra2_actor")
        self.assertEqual(snapshot.action_context()["available_production_names"], [{"id": "gapowr", "name": "Power Plant"}])

    def test_ra2_strategy_does_not_reuse_ra1_country_bonus(self):
        snapshot = GameSnapshot(tick=1, mod_id="ra2", units=(Unit(1, "amcv"),), available_production=("gapowr",))
        profile = strategic_profile(snapshot, {"player_faction": "germany"})
        self.assertEqual(profile["mod_id"], "ra2")
        self.assertNotIn("Chrono Tanks", str(profile))
        self.assertEqual(profile["available_production"][0]["id"], "gapowr")

    def test_ra2_battlefield_counts_use_current_game_actor_names(self):
        snapshot = GameSnapshot(tick=1, mod_id="ra2", actor_names={"e1": "GI", "e2": "Conscript"},
                                units=(Unit(1, "e1"), Unit(2, "e2"), Unit(3, "e2")))
        self.assertEqual(GameRuntime._display_type_counts(snapshot.units, snapshot=snapshot),
                         {"Conscript": 2, "GI": 1})

    def test_old_observations_remain_red_alert_compatible(self):
        snapshot = GameSnapshot.from_dict({"tick": 1})
        self.assertEqual(snapshot.mod_id, "ra")
        self.assertEqual(snapshot.actor_name("e1"), "Rifle Infantry")

    def test_ra2_model_text_uses_only_current_game_names(self):
        snapshot = GameSnapshot(tick=1, mod_id="ra2", actor_names={"e1": "GI", "e2": "Conscript"})
        self.assertEqual(snapshot.humanize_text("train e1 and e2"), "train GI and Conscript")
        self.assertEqual(GameSnapshot(tick=1, mod_id="ra2").humanize_text("e2"), "e2")

    def test_ra2_scouting_recognizes_the_existing_barracks(self):
        companion = Companion(AIRouter(Settings()))
        companion.latest_snapshot = GameSnapshot(tick=1, mod_id="ra2", map_width=64, map_height=64,
            buildings=(Unit(1, "nahand"),), available_production=("e2",), actor_names={"e2": "Conscript"})
        response = companion.handle_player_input("Please train scouts")
        self.assertEqual(response.source, "action-proposal")
        self.assertTrue(all(command["item_type"] == "e2" for command in response.metadata["action"]["commands"]))

    def test_only_off_map_prison_fences_are_trimmed(self):
        text = "Bounds: 2,4,56,108\nActors:\n\tOutside: cafncp\n\t\tLocation: 27,-27\n\tInside: cafncp\n\t\tLocation: 27,-10\n\tOther: gacnst\n\t\tLocation: 27,-27\n"
        trimmed = prepare.trim_off_map_fences(text)
        self.assertNotIn("Outside:", trimmed)
        self.assertIn("Inside: cafncp", trimmed)
        self.assertIn("Other: gacnst", trimmed)

    def test_import_cannot_choose_an_unconfigured_content_library(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "configured library"):
                ra2_content_root()

    def test_shared_content_import_preserves_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "owned", root / "content"
            source.mkdir()
            destination.mkdir()
            (source / "RA2.MIX").write_bytes(b"owned" * 1024)
            (source / "language.mix").write_bytes(b"language" * 1024)
            (destination / "ra2.mix").write_bytes(b"previous user data")
            with self.assertRaisesRegex(ValueError, "Refusing to replace"):
                import_content(source, source, destination)
            self.assertEqual((destination / "ra2.mix").read_bytes(), b"previous user data")

    def test_packaging_integrates_ra2_before_signing(self):
        package = (ROOT / "scripts/package-macos.sh").read_text()
        self.assertLess(package.index('scripts/prepare-ra2.py'), package.index('sign_runtime_payload()'))
        wrapper = (ROOT / "apps/installer/macos/OpenRAAI").read_text()
        self.assertIn('OPENRA_AI_SUPPORT_DIR="$support_root"', wrapper)
        self.assertIn('openra-ai-game.txt', wrapper)
        self.assertLess(wrapper.index('\nwait_for_companion_health\n'), wrapper.index('"$macos_dir/GameLauncher"'))

    def test_failed_import_removes_staging_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "owned", root / "content"
            source.mkdir()
            (source / "ra2.mix").write_bytes(b"owned" * 1024)
            (source / "language.mix").write_bytes(b"language" * 1024)
            with patch("openra_ai_companion.game_content.shutil.copyfileobj", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    import_content(source, source, destination)
            self.assertEqual(list(destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
