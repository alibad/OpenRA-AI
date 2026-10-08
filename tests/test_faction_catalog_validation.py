"""Shared catalog deep links, per-mode rules consistency, and RA2 catalog integration."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


catalog_module = load("content_catalog", "content_catalog.py")
validator = load("validate_faction_catalog", "validate-faction-catalog.py")
prepare_ra2 = load("prepare_ra2", "prepare-ra2.py")

# The engine that has the native catalog. Defaults to the canonical checkout beside this repository.
ENGINE = Path(os.environ.get("OPENRA_AI_ENGINE_ROOT", ROOT.parent / "OpenRA")).resolve()
RA2_ARCHIVE = ROOT / "artifacts/ra2-native" / (
    "ra2-" + json.loads((ROOT / "apps/installer/ra2/upstream.json").read_text())["commit"] + ".tar.gz")


class DeepLinkTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(catalog_module.CATALOG.read_text(encoding="utf-8"))

    def test_links_follow_the_public_site_routes_for_each_mode(self):
        self.assertEqual(catalog_module.web_link(self.catalog, "faction", "saudi-arabia", "ra"),
                         "https://rtsai.net/factions/saudi-arabia?mode=ra")
        self.assertEqual(catalog_module.web_link(self.catalog, "unit", "cnqilin", "ra2"),
                         "https://rtsai.net/units/cnqilin?mode=ra2")
        catalog_module.validate_links(self.catalog)

    def test_catalog_without_links_uses_the_same_defaults(self):
        self.catalog.pop("links")
        self.assertEqual(catalog_module.web_link(self.catalog, "faction", "iran", "ra2"),
                         "https://rtsai.net/factions/iran?mode=ra2")

    def test_rejects_malformed_link_targets(self):
        for kind, item, mode in (("faction", "Iran", "ra"), ("unit", "cnqilin", "RA2"), ("page", "iran", "ra"), ("unit", "", "ra")):
            with self.assertRaises(ValueError):
                catalog_module.web_link(self.catalog, kind, item, mode)

    def test_rejects_malformed_link_templates(self):
        for key, value in (("origin", "http://rtsai.net"), ("origin", "https://rtsai.net/site"), ("faction", "/factions/iran"),
                           ("unit", "units/{unitId}?mode={mode}"), ("unit", "/units/{unitId}")):
            candidate = copy.deepcopy(self.catalog)
            candidate["links"][key] = value
            with self.assertRaises(ValueError, msg=f"{key}={value}"):
                catalog_module.validate(candidate, ROOT.parent / "OpenRA")

    def test_mode_profiles_and_isolated_environment(self):
        self.assertEqual(validator.profile_for(self.catalog, "ra"), "world-war-iii")
        self.assertEqual(validator.profile_for(self.catalog, "ra2"), "ra2-modern")
        os.environ["OPENRA_AI_CATALOG"] = "should-not-leak.json"
        try:
            env = validator.mode_environment(Path("engine"), Path("support"), "ra2-modern", Path("stage/mods"))
        finally:
            os.environ.pop("OPENRA_AI_CATALOG")
        self.assertNotIn("OPENRA_AI_CATALOG", env)
        self.assertEqual(env["OPENRA_UTILITY_EXPERIENCE_PROFILE"], "ra2-modern")
        self.assertEqual(env["MOD_SEARCH_PATHS"], ",".join((str(Path("engine") / "mods"), str(Path("stage/mods")))))
        self.assertNotIn("MOD_SEARCH_PATHS", validator.mode_environment(Path("engine"), Path("support"), "world-war-iii", None))


class Ra2IntegrationTests(unittest.TestCase):
    def test_ra2_manifest_offers_the_faction_catalog_only_when_the_engine_ships_it(self):
        manifest_text = "ChromeLayout:\n\tcommon|chrome/mainmenu.yaml\nFluentMessages:\n\tcommon|fluent/chrome.ftl\n"
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "mod.yaml"
            engine = Path(temp) / "engine"
            manifest.write_text(manifest_text)
            prepare_ra2.integrate_faction_catalog(manifest, engine)
            self.assertEqual(manifest.read_text(), manifest_text)

            (engine / "mods/common/chrome").mkdir(parents=True)
            (engine / "mods/common/chrome/faction-catalog.yaml").write_text("")
            prepare_ra2.integrate_faction_catalog(manifest, engine)
            text = manifest.read_text()
            self.assertIn("\tcommon|chrome/mainmenu.yaml\n\tcommon|chrome/faction-catalog.yaml\n", text)
            self.assertIn("\tcommon|fluent/chrome.ftl\n\tcommon|fluent/faction-catalog.ftl\n", text)


@unittest.skipUnless(validator.supports_catalog_check(ENGINE), f"{ENGINE} has no built Faction Catalog; set OPENRA_AI_ENGINE_ROOT")
class RulesConsistencyTests(unittest.TestCase):
    """Runs the engine's own rules loader, so the catalog is checked against real, fully merged rules."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.catalog = json.loads(catalog_module.CATALOG.read_text(encoding="utf-8"))

    def check(self, catalog, mode="ra", ra2_mods=None):
        path = Path(self.temp.name) / f"catalog-{len(os.listdir(self.temp.name))}.json"
        path.write_text(json.dumps(catalog), encoding="utf-8")
        return validator.check_mode(ENGINE, path, mode, Path(self.temp.name) / "out", ra2_mods)

    def codes(self, result):
        return {issue["code"] for issue in result["issues"]}

    def unit(self, catalog, unit_id):
        return next(unit for unit in catalog["units"] if unit["id"] == unit_id)

    def test_shipped_catalog_matches_classic_rules(self):
        result = self.check(self.catalog)
        self.assertTrue(result["valid"], result)
        self.assertEqual([f for f in result["factions"] if f.startswith("modern:")],
                         ["modern:china", "modern:iran", "modern:turkey", "modern:saudi-arabia", "modern:yemen"])
        digest = json.loads(Path(result["digest"]).read_text(encoding="utf-8"))
        yemen = next(f for f in digest["factions"] if f["catalogId"] == "yemen")
        self.assertEqual([u["actor"] for u in yemen["roster"] if u.get("antiAir")], ["sam"])

    def test_missing_or_foreign_actor_fails(self):
        missing = copy.deepcopy(self.catalog)
        self.unit(missing, "cnqilin")["variants"]["ra"]["actorId"] = "CNQILIN_MISSING"
        self.assertIn("unit-missing-actor", self.codes(self.check(missing)))

        foreign = copy.deepcopy(self.catalog)
        self.unit(foreign, "cnqilin")["variants"]["ra"]["actorId"] = "IRKARR"
        result = self.check(foreign)
        self.assertFalse(result["valid"])
        self.assertTrue({"unit-not-buildable", "unit-not-in-roster"} <= self.codes(result), result["issues"])

    def test_unit_leaking_into_unavailable_mode_fails(self):
        leaking = copy.deepcopy(self.catalog)
        self.unit(leaking, "m1a2s")["variants"]["ra2"] = {"actorId": "r2m1a2s", "repository": "product", "rulesPath": "x"}
        self.assertIn("unit-in-unavailable-mode", self.codes(self.check(leaking)))

    def test_malformed_deep_link_fails(self):
        broken = copy.deepcopy(self.catalog)
        broken["links"]["faction"] = "/factions/china"
        self.assertIn("malformed-link", self.codes(self.check(broken)))

    @unittest.skipUnless(RA2_ARCHIVE.is_file(), "pinned RA2 source archive not cached; run scripts/prepare-local-ra2.py")
    def test_installed_windows_and_macos_layouts_resolve_the_staged_catalog(self):
        layout = load("verify_catalog_package_layout", "verify-catalog-package-layout.py")
        output = Path(self.temp.name) / "layout"
        self.assertEqual(layout.main(["--engine", str(ENGINE), "--output", str(output)]), 0)
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        for name in ("windows", "macos"):
            result = summary["layouts"][name]
            self.assertTrue(result["passed"], result)
            self.assertEqual({mode: r["valid"] for mode, r in result["game"].items()}, {"ra": True, "ra2": True})

    @unittest.skipUnless(RA2_ARCHIVE.is_file(), "pinned RA2 source archive not cached; run scripts/prepare-local-ra2.py")
    def test_ra2_lists_only_ra2_factions_and_rejects_premature_availability(self):
        mods = validator.prepare_ra2_mods(ENGINE, Path(self.temp.name) / "ra2")
        result = self.check(self.catalog, "ra2", mods)
        self.assertTrue(result["valid"], result)
        modern = [f for f in result["factions"] if f.startswith("modern:")]
        self.assertEqual(modern, ["modern:china", "modern:iran", "modern:turkey"])
        self.assertIn("original:rules:america", result["factions"])

        # Declaring a faction available in RA2 before its RA2 pack and units exist must fail.
        premature = copy.deepcopy(self.catalog)
        saudi = next(f for f in premature["factions"] if f["id"] == "saudi-arabia")
        saudi["variants"]["ra2"] = {"status": "implemented", "profileId": "ra2-modern", "description": "test"}
        next(p for p in premature["profiles"] if p["id"] == "ra2-modern")["factionIds"].append("saudi-arabia")
        codes = self.codes(self.check(premature, "ra2", mods))
        self.assertIn("faction-without-rules", codes)


if __name__ == "__main__":
    unittest.main()
