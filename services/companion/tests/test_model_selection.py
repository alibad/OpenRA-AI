from __future__ import annotations

import json
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from openra_ai_companion.lm_studio import discover
from openra_ai_companion.model_selection import Hardware, GIB, choose_profile, selected_components, validate_profiles
from openra_ai_companion.settings import Settings


MANIFEST = Path(__file__).resolve().parents[3] / "packaging" / "ai-pack.lock.json"


class ModelSelectionTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text())

    def test_catalogue_profiles_reference_real_pinned_components(self):
        validate_profiles(self.manifest)
        for profile in self.manifest["model_profiles"]:
            self.assertTrue(profile["validated"])
            components = selected_components(self.manifest, profile)
            self.assertTrue(all(len(component["sha256"]) == 64 for component in components))
            self.assertIn("whisper-base-en", [component["id"] for component in components])

    def test_automatic_uses_balanced_on_a_capable_mac(self):
        profile = choose_profile(self.manifest, Hardware(16 * GIB, 10 * GIB, 8, True))
        self.assertEqual(profile["id"], "recommended")

    def test_automatic_preserves_memory_on_an_eight_gigabyte_mac(self):
        profile = choose_profile(self.manifest, Hardware(8 * GIB, 5 * GIB, 8, True))
        self.assertEqual(profile["id"], "lightweight")
        self.assertIsNone(profile["projector"])
        self.assertLess(sum(component["bytes"] for component in selected_components(self.manifest, profile)), 1_400_000_000)

    def test_cpu_only_and_unknown_hardware_choose_lightweight(self):
        for hardware in (Hardware(), Hardware(32 * GIB, 24 * GIB, 16, False)):
            self.assertEqual(choose_profile(self.manifest, hardware)["id"], "lightweight")

    def test_pressure_refuses_to_steal_game_memory(self):
        with self.assertRaisesRegex(ValueError, "memory"):
            choose_profile(self.manifest, Hardware(8 * GIB, 3 * GIB, 4, True))

    def test_explicit_choice_is_respected_when_it_fits(self):
        profile = choose_profile(self.manifest, Hardware(32 * GIB, 24 * GIB, 8, True), "lightweight")
        self.assertEqual(profile["id"], "lightweight")

    def test_unvalidated_newer_candidates_never_win(self):
        candidate = dict(self.manifest["model_profiles"][0], id="new", priority=999, validated=False)
        self.manifest["model_profiles"].append(candidate)
        self.assertEqual(choose_profile(self.manifest, Hardware(64 * GIB, 50 * GIB, 16, True))["id"], "recommended")

    def test_invalid_catalogue_reference_is_rejected(self):
        self.manifest["model_profiles"][0]["model"] = "../outside.gguf"
        with self.assertRaises(ValueError):
            validate_profiles(self.manifest)

    def test_selection_setting_defaults_and_validation(self):
        self.assertEqual(Settings().model_selection, "auto")
        self.assertEqual(Settings().with_updates({"model_selection": "lightweight"}).model_selection, "lightweight")
        with self.assertRaises(ValueError):
            Settings(model_selection="latest-from-internet").validated()

    def test_lm_studio_uses_capabilities_not_model_name(self):
        payload = {"models": [
            {"type": "embedding", "key": "ignore", "size_bytes": 10},
            {"type": "llm", "key": "huge", "size_bytes": 100 * GIB, "capabilities": {"trained_for_tool_use": True}},
            {"type": "llm", "key": "latest-coder", "size_bytes": GIB, "capabilities": {}},
            {"type": "llm", "key": "unknown-name", "display_name": "My model", "size_bytes": GIB,
             "capabilities": {"trained_for_tool_use": True, "vision": True}, "loaded_instances": [{"id": "loaded"}]},
        ]}
        with patch("urllib.request.urlopen", return_value=BytesIO(json.dumps(payload).encode())):
            result = discover(hardware=Hardware(16 * GIB, 10 * GIB, 8, True))
        self.assertEqual(result["suggested"]["id"], "unknown-name")
        self.assertTrue(result["suggested"]["supports_vision"])
        self.assertEqual(len(result["models"]), 3)

    def test_discovery_never_contacts_a_remote_server(self):
        with patch("urllib.request.urlopen") as network:
            with self.assertRaises(ValueError):
                discover("https://example.com")
            network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
