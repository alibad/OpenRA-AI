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
            # Names and roles must match what each game mode shows, with RA2 canonical.
            lambda c: c["units"][0]["variants"]["ra2"].update(name="Renamed In Catalog Only"),
            lambda c: c["units"][0]["variants"]["ra"].update(name="Renamed In Catalog Only"),
            lambda c: c["units"][0].update(name=c["units"][0]["variants"]["ra"]["name"]),
            lambda c: c["units"][0].update(role="Different role"),
            lambda c: c["units"][0]["variants"]["ra2"].pop("role"),
            lambda c: c["factions"][2]["variants"]["ra2"].update(name="Turkey"),
            lambda c: c["factions"][2]["variants"]["ra2"].update(engineFactionId="missing"),
            lambda c: c["factions"][2].update(name="Turkey"),
        ):
            candidate = copy.deepcopy(self.catalog)
            mutation(candidate)
            with self.assertRaises(ValueError):
                module.validate(candidate, self.engine)

    def test_every_faction_has_identity_rival_views_and_flavour(self):
        factions = {faction["id"]: faction for faction in self.catalog["factions"]}
        self.assertEqual(set(factions), set(self.catalog["profiles"][1]["factionIds"]))
        for faction in factions.values():
            self.assertTrue(faction["identity"]["motto"] and faction["identity"]["story"])
            self.assertEqual(len(faction["identity"]["keywords"]), 3)
            self.assertTrue(all(view["rival"] in factions for view in faction["rivalViews"]))
        module.validate_narrative(self.catalog)

    def test_rejects_incomplete_or_unsafe_narrative(self):
        def faction(c, faction_id):
            return next(row for row in c["factions"] if row["id"] == faction_id)

        def views(c, faction_id):
            return faction(c, faction_id)["rivalViews"]

        def loading(c, faction_id):
            return faction(c, faction_id)["flavour"]["loading"]

        def identity(c, faction_id):
            return faction(c, faction_id)["identity"]

        def silence_hezbollah(c):
            for target, index, rival in (("turkey", 2, "saudi-arabia"), ("saudi-arabia", 2, "china"), ("israel", 0, "turkey")):
                views(c, target)[index].update(rival=rival)
            loading(c, "israel")[1].update(rival="turkey")

        one_sentence ="We hold the line for every family behind us" + ", and they sleep easier for it" * 10 + "."
        short_story = ("We hold the line for every family that sleeps behind us, from the coast to the hills. " * 4).strip()
        for mutation in (
            lambda c: c.pop("narrative"),
            lambda c: faction(c, "china").pop("identity"),
            lambda c: faction(c, "iran").pop("rivalViews"),
            lambda c: faction(c, "turkey").pop("flavour"),
            lambda c: identity(c, "yemen").update(motto="Steadfast as the mountains and the sea and the sky and the stars."),
            lambda c: identity(c, "israel").update(story=one_sentence),
            lambda c: identity(c, "israel").update(story="We hold. We stay. We endure."),
            # Equal depth: one faction's story may not shrink far below the others.
            lambda c: identity(c, "hezbollah").update(story=short_story),
            lambda c: identity(c, "china").update(keywords=["Unity", "Discipline"]),
            lambda c: identity(c, "china").update(keywords=["Unity", "unity", "Renewal"]),
            lambda c: identity(c, "china").update(keywords=["Unity", "Discipline", "lowercase"]),
            lambda c: views(c, "iran")[0].update(rival="usa"),
            lambda c: views(c, "china")[0].update(rival="china"),
            lambda c: views(c, "turkey")[1].update(rival=views(c, "turkey")[0]["rival"]),
            lambda c: views(c, "saudi-arabia")[0].update(kind="fact"),
            lambda c: views(c, "yemen")[0].update(text=one_sentence[:290] + "."),
            lambda c: views(c, "iran")[0].update(text=views(c, "iran")[0]["text"] + " Barbarians, all of them."),
            lambda c: views(c, "israel").pop(),
            lambda c: loading(c, "china").pop(),
            lambda c: loading(c, "china")[1].update(rival="iran"),
            lambda c: loading(c, "china")[0].update(rival="turkey"),
            lambda c: faction(c, "hezbollah")["flavour"].update(voiceIdeas=[]),
            # No faction may be only a target: Hezbollah must voice at least one rival view.
            silence_hezbollah,
        ):
            candidate = copy.deepcopy(self.catalog)
            mutation(candidate)
            with self.assertRaises(ValueError):
                module.validate_narrative(candidate)
        candidate = copy.deepcopy(self.catalog)
        faction(candidate, "israel").pop("identity")
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
