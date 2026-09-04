from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import unittest
import wave

from PIL import Image
from openra_ai_companion.models import GameSnapshot, Unit

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"scripts"))
import ra2_turkey_assets as art
ASSETS=art.OUTPUT


class TurkeyFactionTests(unittest.TestCase):
    def test_full_roster_is_declared_with_unique_names_and_icons(self):
        catalog=(ASSETS/"experiences.yaml").read_text().split("\t\tra2-turkey:")[1].split("\tProfiles:")[0]
        messages=(ASSETS/"messages.ftl").read_text()+(ASSETS/"turkey-messages.ftl").read_text()
        self.assertEqual(len(art.TURKEY_UNITS),16)
        self.assertEqual(len(art.DEFENSES),3)
        for actor in art.TURKEY_UNITS+art.DEFENSES:
            self.assertIn(actor,catalog)
            self.assertIn(f"ra2-{actor}-name =",messages)
            with Image.open(ASSETS/"icons"/(actor+".png")) as image: self.assertEqual(image.size,(60,48))

    def test_native_shp_frames_are_bounded_indexed_and_reproducible(self):
        manifest=json.loads((ASSETS/"turkey-art/manifest.json").read_text())
        for name,info in manifest.items():
            data=(ASSETS/"turkey-art"/(name+".shp")).read_bytes()
            zero,w,h,count=struct.unpack_from("<4H",data)
            self.assertEqual((zero,w,h,count),(0,*info["size"],info["frames"]))
            self.assertEqual(hashlib.sha256(data).hexdigest(),info["sha256"])
            self.assertEqual(count,112 if name in art.INFANTRY else 41)
            frames=[]
            for i in range(count):
                x,y,fw,fh,fmt,offset=struct.unpack_from("<4HB11xI",data,8+i*24)
                self.assertEqual((x,y,fw,fh,fmt),(0,0,w,h,1))
                self.assertLessEqual(offset+w*h,len(data))
                pixels=data[offset:offset+w*h]
                self.assertIn(0,pixels)
                frames.append(pixels)
            self.assertGreater(len(set(frames)),20)
            self.assertTrue(any(16<=p<32 for frame in frames for p in frame),name)
            # All facings are direct geometry projections, not one rotated bitmap.
            if name in art.INFANTRY:
                self.assertEqual(len(set(frames[:8])),8)
                frame=art.render(art.soldier(name),0,(48,48),15,(24,35),True)
                self.assertEqual(art.indexed(frame),frames[0])

    def test_sprites_keep_clear_borders_and_ground_anchor(self):
        for name in art.INFANTRY:
            for facing in range(0,1024,128):
                img=art.render(art.soldier(name),facing,(48,48),15,(24,35),True)
                box=img.getchannel("A").getbbox()
                self.assertGreater(box[0],0)
                self.assertLess(box[2],48)
                self.assertGreater(box[1],0)
                self.assertLess(box[3],48)

    def test_native_effects_and_depth_survive_rendering(self):
        sequences=(ASSETS/"turkey-roster-sequences.yaml").read_text()
        for actor in art.INFANTRY:
            section=sequences.split(actor+":\n",1)[1].split("\n\n",1)[0]
            self.assertIn("Inherits@MC: ^MindControllable",section)
            self.assertIn("Offset: 0, -11, 16",section)
        for actor in art.DEFENSES:
            section=sequences.split(actor+":\n",1)[1].split("\n\n",1)[0]
            self.assertIn("Offset: 0, -19, 19",section)
        with Image.open(ASSETS/"previews/turkey.png") as image:
            self.assertEqual(image.size,(512,512))

    def test_ai_covers_every_role_and_defense(self):
        ai=(ASSETS/"turkey-ai.yaml").read_text()
        original=(ASSETS/"turkey.yaml").read_text()
        for profile in ("normal","medium","rush","turtle","naval"):
            section=ai.split("UnitBuilderBotModule@"+profile+":",1)[1].split("BaseBuilderBotModule@",1)[0]
            existing=original.split("UnitBuilderBotModule@"+profile+":",1)[1].split("\n\tUnitBuilderBotModule@",1)[0]
            for actor in art.TURKEY_UNITS: self.assertIn(actor+":",section+existing)
        for actor in art.DEFENSES: self.assertEqual(ai.count(actor+": "),10)

    def test_new_starting_armies_use_turkish_infantry(self):
        rules=(ASSETS/"turkey.yaml").read_text().split("\nPlayer:")[0]
        self.assertNotRegex(rules,r"\be1\b")
        self.assertIn("r2trrifle, r2trrifle, r2trat",rules)
        self.assertIn("Class: none",rules)

    def test_replacements_restrict_only_turkey_and_keep_support(self):
        rules=(ASSETS/"turkey-replacements.yaml").read_text()
        for line in rules.splitlines():
            if "Prerequisites:" in line: self.assertTrue(line.endswith(", ~!faction.turkey"))
        for actor in ("engineer","dog","spy","cmin","lcrf","gapowr","garefn","gaweap"):
            self.assertNotRegex(rules,rf"(?m)^{actor}:")

    def test_mechanics_and_tech_boundaries_are_explicit(self):
        rules=(ASSETS/"turkey-roster.yaml").read_text()
        self.assertIn("BuildLimit: 1",rules)
        self.assertIn("Prerequisites: ~faction.turkey, gapile, gatech",rules)
        self.assertIn("Locomotor: lcraft",rules)
        self.assertIn("MaxWeight: 5",rules)
        self.assertIn("PauseOnCondition: lowpower",rules)
        self.assertIn("Modifier: 120",rules)
        self.assertIn("Condition: r2-designated",rules)
        weapons=(ASSETS/"turkey-weapons.yaml").read_text()
        self.assertIn("ValidRelationships: Enemy",weapons)
        self.assertIn("RangeLimit: 15c0",weapons)
        interceptor=weapons.split("R2InterceptorMissile:\n",1)[1].split("\n\n",1)[0]
        self.assertIn("RangeLimit: 16c0",interceptor)
        self.assertIn("Speed: 450",interceptor)
        self.assertIn("MinimumLaunchAngle: 0",interceptor)
        self.assertIn("MaximumLaunchAngle: 0",interceptor)

    def test_bilingual_voice_sources_exist_for_every_unit(self):
        voices=(ASSETS/"turkey-voices.yaml").read_text()
        audio=(ASSETS/"turkey-audio.yaml").read_text()
        names=set(re.findall(r"audio/(tr-[\w-]+)",voices))
        self.assertEqual(len(names),24)
        for name in names:
            with wave.open(str(ROOT/"engine/openra/mods/ra/bits"/(name+".wav"))) as clip:
                self.assertGreater(clip.getnframes(),0)
        for actor in art.TURKEY_UNITS:
            self.assertRegex(audio,rf"(?m)^{actor}:$")

    def test_native_actor_names_reach_companion(self):
        names={}
        for path in ("messages.ftl","turkey-messages.ftl"):
            for actor,label in re.findall(r"^ra2-(r2\w+)-name = (.+)$",(ASSETS/path).read_text(),re.MULTILINE): names[actor]=label
        state=GameSnapshot(tick=1,mod_id="ra2",units=(Unit(1,"r2trrifle"),Unit(2,"r2greywolf")),actor_names=names)
        self.assertEqual(state.compact()["own_unit_types"],["Mechanized Rifleman","Grey Wolf"])


if __name__=="__main__": unittest.main()
