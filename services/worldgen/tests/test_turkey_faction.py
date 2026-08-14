from __future__ import annotations

import hashlib
import json
import re
import struct
import unittest
import wave
import zipfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "engine" / "openra"
BITS = ENGINE / "mods" / "ra" / "bits"
FRAMES = ROOT / "generated" / "turkey-sprites"
RULES = ENGINE / "mods" / "ra" / "rules" / "turkey.yaml"
FACTION_PACK = ENGINE / "mods" / "ra" / "experiences" / "factions" / "turkey.yaml"
SEQUENCES = ENGINE / "mods" / "ra" / "sequences" / "turkey.yaml"
MISSION = ROOT / "generated" / "missions" / "straits-shield-2026.oramap"


class TurkeyFactionTests(unittest.TestCase):
    def test_selector_and_complete_native_tree_contract(self) -> None:
        world = FACTION_PACK.read_text(encoding="utf-8")
        rules = RULES.read_text(encoding="utf-8")
        chrome = (ENGINE / "mods" / "ra" / "chrome.yaml").read_text(encoding="utf-8")
        self.assertIn("Faction@turkey:", world)
        self.assertIn("InternalName: turkey", world)
        self.assertIn("turkey: 226, 113, 30, 15", chrome)
        self.assertEqual(chrome.count("\n\t\tturkey:"), 1)
        for actor, prerequisite in (("FACT", "structures.turkey"), ("TENT", "infantry.turkey"),
                                    ("WEAP", "vehicles.turkey"), ("HPAD", "aircraft.turkey"),
                                    ("SYRD", "ships.turkey")):
            block = rules.split(f"\n{actor}:\n", 1)[1].split("\n\n", 1)[0]
            self.assertIn(prerequisite, block)
        for structure in ("powr", "apwr", "proc", "silo", "tent", "weap", "fix", "dome", "atek", "hpad", "syrd"):
            self.assertIn(structure, (ENGINE / "mods" / "ra" / "rules" / "structures.yaml").read_text(encoding="utf-8").lower())

    def test_required_roles_and_native_systems(self) -> None:
        rules = RULES.read_text(encoding="utf-8")
        for actor in ("TRRIFLE", "TRAT", "TRDRONEOP", "GREYWOLF", "BOZKIR", "ARAS8", "YILDIRIM",
                      "GOKKALKAN", "SANCAK", "DENIZKAPLAN", "KUZGUNM", "TURNAAH", "SAHINX",
                      "MARMARA", "EGE", "POYRAZ"):
            self.assertRegex(rules, rf"(?m)^{actor}:$")
        self.assertIn("BuildLimit: 1", rules.split("GREYWOLF:", 1)[1].split("\n\n", 1)[0])
        for contract in ("ProximityExternalCondition@MECHANIZED", "Warhead@DESIGNATE: GrantExternalCondition",
                         "JamsMissiles", "Locomotor: amphibious", "Inherits: MIG", "AmmoPool",
                         "SpawnActorOnDeath", "LeavesTrails@WAKE"):
            haystack = rules + (ENGINE / "mods" / "ra" / "weapons" / "turkey.yaml").read_text(encoding="utf-8")
            self.assertIn(contract, haystack)

    def test_every_standard_bot_personality_has_turkey_production(self) -> None:
        rules = RULES.read_text(encoding="utf-8")
        personalities = ("beginner", "easy", "medium", "rush", "normal", "turtle", "naval")
        for personality in personalities:
            marker = f"UnitBuilderBotModule@{personality}:"
            self.assertIn(marker, rules)
            block = rules.split(marker, 1)[1].split("\n\tUnitBuilderBotModule@", 1)[0]
            for unit in ("trrifle", "trat", "trdroneop", "aras8", "bozkir", "yildirim", "gokkalkan",
                         "sancak", "denizkaplan", "kuzgunm", "turnaah", "sahinx", "marmara", "ege", "poyraz"):
                self.assertIn(f"\n\t\t\t{unit}:", block, f"{personality}: {unit}")
        for personality in personalities:
            squad = f"SquadManagerBotModule@{personality}:"
            self.assertIn(squad, rules)

    def test_directional_frame_counts_and_uniqueness(self) -> None:
        expected = {
            **{name: 64 for name in ("bozkir", "aras8", "yildirim", "gokkalkan", "sancak", "denizkaplan")},
            "kuzgunm": 16, "sahinx": 16, "turnaah": 32,
            "marmara": 48, "ege": 48, "poyraz": 48,
            "turnaahrotor": 12,
            **{name: 378 for name in ("trrifle", "trat", "trdroneop", "greywolf")},
        }
        for name, count in expected.items():
            paths = sorted((FRAMES / name).glob(f"{name}-*.png"))
            self.assertEqual(count, len(paths), name)
            directional = paths if count < 100 else paths[:256]
            hashes = {hashlib.sha256(Image.open(path).convert("RGBA").tobytes()).digest() for path in directional}
            minimum = count if count < 100 else 80
            self.assertGreaterEqual(len(hashes), minimum, name)
        for name in ("marmara", "ege", "poyraz"):
            self.assertEqual(96, len(list((FRAMES / f"{name}sink").glob(f"{name}sink-*.png"))))

    def test_sequences_enforce_authored_native_facing_contracts(self) -> None:
        sequences = SEQUENCES.read_text(encoding="utf-8")
        # Ground/husk images inherit the shared classic-facing contracts, so
        # count definitions rather than expanded actor instances.
        self.assertGreaterEqual(sequences.count("UseClassicFacings: True"), 7)
        self.assertGreaterEqual(sequences.count("InterpolatedFacings: 64"), 4)
        self.assertIn("Start: 32\n\t\tFacings: 32", sequences)
        for sequence in ("stand", "stand2", "run", "shoot", "prone-stand", "prone-run", "liedown",
                         "standup", "prone-shoot", "idle1", "idle2", "die1", "die2", "die3", "die4", "die5"):
            self.assertRegex(sequences, rf"(?m)^\t{re.escape(sequence)}:")
        builder = (ROOT / "scripts" / "build-turkey-sprites.py").read_text(encoding="utf-8")
        self.assertNotIn(".rotate(", builder)

    def test_packed_sprite_frame_counts(self) -> None:
        expected = {"bozkir": 64, "sancak": 64, "kuzgunm": 16, "turnaah": 32, "sahinx": 16,
                    "marmara": 48, "ege": 48, "poyraz": 48, "trrifle": 378, "trat": 378,
                    "trdroneop": 378, "greywolf": 378, "marmarasink": 96}
        for name, count in expected.items():
            with (BITS / f"{name}.shp").open("rb") as stream:
                self.assertEqual(count, struct.unpack("<H", stream.read(2))[0], name)

    def test_bilingual_voice_provenance_and_pcm_contract(self) -> None:
        provenance = json.loads((ROOT / "assets" / "turkey-faction" / "voice-provenance.json").read_text(encoding="utf-8"))
        languages = {line["language"] for line in provenance["lines"]}
        self.assertEqual({"tr-TR", "en-US"}, languages)
        self.assertTrue(all(line["synthetic_voice_disclosed"] and not line["real_person_imitation"] for line in provenance["lines"]))
        for line in provenance["lines"]:
            with wave.open(str(BITS / line["filename"]), "rb") as audio:
                self.assertEqual((1, 2, 44100), (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()))

    def test_mission_is_construction_enabled_and_exposes_all_domains(self) -> None:
        self.assertTrue(MISSION.exists())
        with zipfile.ZipFile(MISSION) as archive:
            names = set(archive.namelist())
            self.assertTrue({"map.yaml", "map.bin", "map.png", "rules.yaml", "straits-shield.lua", "map.ftl"} <= names)
            script = archive.read("straits-shield.lua").decode("utf-8")
            map_yaml = archive.read("map.yaml").decode("utf-8")
            self.assertIn('HasPrerequisites({ "weap", "dome", "fix", "hpad", "atek", "syrd" })', script)
            self.assertIn("Faction: turkey", map_yaml)
            for actor in ("fact", "proc", "tent", "kuzgunm", "denizkaplan", "marmara", "ege", "poyraz"):
                self.assertIn(actor, map_yaml.lower())
            self.assertNotIn("real political leader", script.lower())


if __name__ == "__main__":
    unittest.main()
