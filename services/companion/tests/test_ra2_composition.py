from __future__ import annotations

import importlib.util
import itertools
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "apps/installer/ra2/modern-factions"
SPEC = importlib.util.spec_from_file_location("prepare_ra2", ROOT / "scripts/prepare-ra2.py")
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


class FactionCompositionTests(unittest.TestCase):
    def test_country_exclusions_combine_without_overwriting_stock_technology(self):
        merged = PREPARE.combined_replacements(ASSETS)
        actors = {}
        for actor, requirements in re.findall(r"(?m)^(\w+):\n\tBuildable:\n\t\tPrerequisites: (.+)$", merged):
            actors[actor] = requirements.split(", ")
        self.assertEqual(actors["e1"], ["~gapile", "~!faction.china", "~!faction.turkey"])
        self.assertEqual(actors["e2"], ["~nahand", "~!faction.iran"])
        for count in range(4):
            for selected in itertools.combinations(("china", "iran", "turkey"), count):
                for player_country in ("china", "iran", "turkey", "america", "england", "france", "germany", "korea", "russia", "iraq", "cuba", "libya"):
                    provided = {"faction." + player_country} if player_country in selected else set()
                    for actor, requirements in actors.items():
                        blocked = any(req[2:] in provided for req in requirements if req.startswith("~!"))
                        expected = ("~!faction." + player_country) in requirements and player_country in selected
                        self.assertEqual(blocked, expected, (selected, player_country, actor))
        for utility in ("engineer", "dog", "spy", "cmin", "harv", "amcv", "smcv"):
            self.assertNotIn(utility, actors)

    def test_inconsistent_original_prerequisites_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for country, prerequisite in (("china", "radar"), ("iran", "tech"), ("turkey", "radar")):
                (root / (country + "-replacements.yaml")).write_text(
                    f"example:\n\tBuildable:\n\t\tPrerequisites: {prerequisite}, ~!faction.{country}\n")
            with self.assertRaisesRegex(ValueError, "Inconsistent original prerequisites"):
                PREPARE.combined_replacements(root)

    def test_bot_actor_classifications_compose_by_country(self):
        for country in ("china", "iran", "turkey"):
            rules = (ASSETS / (country + "-ai.yaml")).read_text()
            for name in ("AdditionalAirUnitsTypes", "AdditionalNavalUnitsTypes", "AdditionalDefenseTypes"):
                self.assertEqual(rules.count(name + ":"), 5, (country, name))
            self.assertNotRegex(rules, r"(?m)^\t\t(?:AirUnitsTypes|NavalUnitsTypes|DefenseTypes):")
        catalog = (ASSETS / "experiences.yaml").read_text()
        self.assertIn("ra2|modern-factions/shared-replacements.yaml", catalog)
        self.assertNotRegex(catalog, r"ra2\|modern-factions/(china|iran|turkey)-replacements.yaml")

    def test_doctrine_is_optional_and_changes_no_combat_stats(self):
        rules = (ASSETS / "combined-arms-ai.yaml").read_text()
        self.assertNotRegex(rules, r"(?m)^\s+(?:Valued|Health|Armament|Buildable|DamageMultiplier|ReloadDelayMultiplier):")
        for profile in ("normal", "medium", "rush", "turtle", "naval"):
            section = rules.split("UnitBuilderBotModule@" + profile + ":", 1)[1].split("SquadManagerBotModule@", 1)[0]
            for role in ("line-infantry", "anti-armor", "main-battle-tank", "artillery", "anti-air", "naval-screen"):
                self.assertRegex(section, role + r": [1-9]\d*")
        catalog = (ASSETS / "experiences.yaml").read_text()
        classic = catalog.split("\t\tra2-classic:", 1)[1]
        self.assertNotIn("ra2-combined-arms-ai", classic)
        self.assertIn("ra2-original-combined-arms:", catalog)
        self.assertIn("Default: 8", catalog)
        self.assertIn("Minimum: 3", catalog)
        self.assertIn("Maximum: 20", catalog)

    def test_original_country_roles_match_native_weapons_not_unit_names(self):
        rules = (ASSETS / "combined-arms-ai.yaml").read_text()
        # Native RA2 weapons/mgs.yaml: Tanya's DoublePistols inherit MP5's zero
        # Light/Medium/Heavy damage. Her separate C4 ability sabotages buildings.
        # weapons/zaps.yaml: Tesla Tank's TankBolt has only 4c range (6c elite).
        # weapons/missiles.yaml: Aegis uses Medusa (^AAMissile), Black Eagle uses
        # Maverick2 ground-strike missiles; neither is an anti-sub/interceptor.
        # rules/soviet-naval.yaml: Sea Scorpion carries an AA FlakWeapon secondary.
        # weapons/misc.yaml: carrier HornetLauncher reaches 25c, Ground/Water only.
        expected = {
            "tany": ("line-infantry", "ground"),
            "ttnk": ("anti-armor", "ground"),
            "hyd": ("anti-air", "naval"),
            "carrier": ("artillery", "naval"),
            "aegis": ("anti-air", "naval"),
            "beag": ("strike-aircraft", "air"),
        }
        for actor, (role, domain) in expected.items():
            block = re.search(rf"(?m)^{actor}:\n((?:\t[^\n]*\n)+)", rules)
            self.assertIsNotNone(block, actor)
            self.assertRegex(block.group(1), rf"(?m)^\t\tRoles: {role}$", actor)
            self.assertRegex(block.group(1), rf"(?m)^\t\tDomain: {domain}$", actor)

        # This RA2 adapter has V3/Dreadnought sequences, but no buildable actor
        # implementations. Metadata alone must not create phantom ActorInfos.
        for absent_actor in ("v3", "dred"):
            self.assertNotRegex(rules, rf"(?m)^{absent_actor}:$")

    def test_original_infantry_recruitment_includes_bounded_native_specialists(self):
        rules = (ASSETS / "combined-arms-ai.yaml").read_text()
        # Every Infantry actor in native rules/ai.yaml UnitsToBuild, including
        # dog scouting/detection. Engineer/Spy are not in that recruitment list.
        infantry = ("e1", "e2", "dog", "flakt", "shk", "ivan", "jumpjet", "deso", "tany", "yuri", "snipe")
        role_by_actor = {}
        for actor in infantry:
            block = re.search(rf"(?m)^{actor}:\n((?:\t[^\n]*\n)+)", rules)
            self.assertIsNotNone(block, actor)
            role_by_actor[actor] = re.search(r"Roles: ([\w-]+)", block.group(1)).group(1)
        # Native AWP is infantry-only, RadBeam/RadEruption counter infantry/light
        # armor, IvanBomber plants bombs, Yuri has MindControl/PsiWave, and dogs
        # detect spies/cloak. None should masquerade as an ordinary tank counter.
        for actor in ("snipe", "deso"):
            self.assertEqual(role_by_actor[actor], "line-infantry")
        for actor in ("ivan", "yuri", "dog"):
            self.assertEqual(role_by_actor[actor], "support")

        for profile in ("normal", "medium", "rush", "turtle", "naval"):
            block = rules.split("\tUnitBuilderBotModule@" + profile + ":", 1)[1].split("\tSquadManagerBotModule@", 1)[0]
            shares, limits = block.split("\t\tUnitLimits:\n", 1)
            positive_roles = {role for role, weight in re.findall(r"\t\t\t([\w-]+): (\d+)", shares) if int(weight) > 0}
            for actor in infantry:
                self.assertIn(role_by_actor[actor], positive_roles, (profile, actor))
            caps = {actor: int(limit) for actor, limit in re.findall(r"\t\t\t(\w+): (\d+)", limits)}
            self.assertEqual(caps, {actor: 2 for actor in ("snipe", "deso", "ivan", "civan", "yuri")})
            # Retain native dog4 and human Tanya/Yuri Prime build-limit-one gates.
            self.assertNotIn("dog", caps)
            self.assertNotIn("tany", caps)
            self.assertNotIn("yuripr", caps)


if __name__ == "__main__":
    unittest.main()
