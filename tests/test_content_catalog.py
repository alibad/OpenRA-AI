import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("content_catalog", ROOT / "scripts/content_catalog.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ContentCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(module.CATALOG.read_text(encoding="utf-8"))
        self.engine = ROOT.parent / "OpenRA"

    def test_all_actor_references_resolve(self):
        module.validate(self.catalog, self.engine)

    def test_rejects_broken_graph_and_modes(self):
        for mutation in (
            lambda c: c["units"][0].update(id="missing"),
            lambda c: c["factions"][0]["unitIds"].append("missing"),
            lambda c: c["units"][0]["variants"]["ra"].update(actorId="MISSING"),
            lambda c: c["units"][0]["variants"]["ra"].update(rulesPath="../../outside"),
            lambda c: c["units"].append(copy.deepcopy(c["units"][0])),
            lambda c: c["factions"][0]["variants"]["ra2"].update(status="unavailable"),
        ):
            candidate = copy.deepcopy(self.catalog)
            mutation(candidate)
            with self.assertRaises(ValueError):
                module.validate(candidate, self.engine)

    def test_package_receives_byte_identical_catalog(self):
        with tempfile.TemporaryDirectory() as stage:
            result = subprocess.run([sys.executable, str(ROOT / "scripts/content_catalog.py"), "--engine", str(self.engine), "--stage", stage], check=True, capture_output=True, text=True)
            staged = Path(stage) / "catalog/factions.json"
            self.assertEqual(staged.read_bytes(), module.CATALOG.read_bytes())
            self.assertEqual(json.loads(result.stdout)["sha256"], hashlib.sha256(staged.read_bytes()).hexdigest())

    def test_packagers_validate_and_stage_the_shared_catalog(self):
        windows = (ROOT / "scripts/package-windows.ps1").read_text(encoding="utf-8")
        macos = (ROOT / "scripts/package-macos.sh").read_text(encoding="utf-8")
        self.assertIn('"content_catalog.py") --engine $engineRoot --stage $stageRoot', windows)
        self.assertIn('catalog_sha256', windows)
        self.assertIn('"$CATALOG_TOOL" --engine "$ENGINE_ROOT" --stage "$RESOURCES"', macos)


if __name__ == "__main__":
    unittest.main()
