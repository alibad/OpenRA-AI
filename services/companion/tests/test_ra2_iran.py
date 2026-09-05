"""Iran's native art contract, production coverage and explicit counterplay."""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import unittest

from PIL import Image

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"scripts"))
import ra2_iran_assets as art


class IranFactionTests(unittest.TestCase):
    def test_submarine_hull_normals_face_outward(self):
        hull=art.ghadir_hull()
        for face in hull.faces[:14]:
            center=tuple(sum(v[i] for v in face.vertices)/len(face.vertices)-(0,0,.34)[i] for i in range(3))
            self.assertGreater(sum(a*b for a,b in zip(face.normal,center)),0)

    def test_thin_wings_face_the_native_light_instead_of_rendering_black(self):
        for actor in ("r2azar","r2loiter"):
            mesh=art.extra_models()[actor][0]
            thin=[face for face in mesh.faces if max(v[2] for v in face.vertices)-min(v[2] for v in face.vertices)<.40]
            self.assertTrue(any(face.normal[2]>.5 for face in thin))
            self.assertFalse(any(face.normal[2]<-.5 for face in thin),actor)

    def test_roster_has_native_production_names_and_icons(self):
        self.assertEqual((len(art.UNITS),len(art.DEFENSES)),(14,3))
        catalog=(art.OUTPUT/"experiences.yaml").read_text().split("\t\tra2-iran:",1)[1].split("\t\tra2-turkey:",1)[0]
        messages=(art.OUTPUT/"messages.ftl").read_text()+(art.OUTPUT/"iran-messages.ftl").read_text()
        for actor in art.UNITS+art.DEFENSES:
            self.assertIn(actor,catalog)
            self.assertIn(f"ra2-{actor}-name =",messages)
            with Image.open(art.OUTPUT/"icons"/(actor+".png")) as image: self.assertEqual(image.size,(60,48))

    def test_native_animation_frames_are_bounded_distinct_and_remappable(self):
        manifest=json.loads((art.OUTPUT/"iran-art/manifest.json").read_text())
        for actor,info in manifest.items():
            data=(art.OUTPUT/"iran-art"/(actor+".shp")).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),info["sha256"])
            zero,w,h,count=struct.unpack_from("<4H",data)
            self.assertEqual((zero,w,h,count),(0,*info["size"],info["frames"]))
            self.assertEqual(count,112 if actor in art.INFANTRY else 41)
            frames=[]
            for i in range(count):
                x,y,fw,fh,fmt,offset=struct.unpack_from("<4HB11xI",data,8+i*24)
                self.assertEqual((x,y,fw,fh,fmt),(0,0,w,h,1))
                self.assertLessEqual(offset+w*h,len(data))
                frames.append(data[offset:offset+w*h])
            self.assertGreater(len(set(frames)),20)
            self.assertTrue(any(16<=p<32 for pixels in frames for p in pixels),actor)
            if actor in art.INFANTRY:
                self.assertEqual(len(set(frames[:8])),8)
                for pixels in frames[:8]:
                    self.assertFalse(any(pixels[:w])+any(pixels[-w:]))
        self.assertEqual(len((art.OUTPUT/"iran-art/iran.pal").read_bytes()),768)

    def test_native_effects_and_depth_offsets_are_preserved(self):
        sequences=(art.OUTPUT/"iran-roster-sequences.yaml").read_text()
        for actor in art.INFANTRY:
            block=sequences.split(actor+":\n",1)[1].split("\n\n",1)[0]
            self.assertIn("Inherits@MC: ^MindControllable",block)
            self.assertIn("Offset: 0, -11, 16",block)
        for actor in art.DEFENSES:
            self.assertIn("Offset: 0, -19, 19",sequences.split(actor+":\n",1)[1].split("\n\n",1)[0])

    def test_all_bot_profiles_have_composable_roster_and_domain_tags(self):
        ai=(art.OUTPUT/"iran-ai.yaml").read_text()
        roles=(art.OUTPUT/"iran-roles.yaml").read_text()
        for bot in ("normal","medium","rush","turtle","naval"):
            block=ai.split("UnitBuilderBotModule@"+bot+":",1)[1].split("BaseBuilderBotModule@",1)[0]
            for actor in art.UNITS: self.assertIn(actor+":",block)
        self.assertNotRegex(ai,r"(?m)^\t\t(?:AirUnitsTypes|NavalUnitsTypes|DefenseTypes):")
        for actor in art.UNITS+art.DEFENSES: self.assertIn(actor+":\n\tStrategicRole:",roles)

    def test_shared_utilities_stay_and_salvo_units_have_counterplay(self):
        replacements=(art.OUTPUT/"iran-replacements.yaml").read_text()
        for actor in ("engineer","dog","harv","smcv","htk","sapc","napowr","narefn","naweap"):
            self.assertNotRegex(replacements,rf"(?m)^{actor}:")
        weapons=(art.OUTPUT/"iran-weapons.yaml").read_text()
        coastal=weapons.split("R2IranCoastalMissile:\n",1)[1].split("\n\n",1)[0]
        self.assertIn("ValidTargets: Water, Structure",coastal)
        self.assertIn("MinRange: 4c0",coastal)
        rules=(art.OUTPUT/"iran-roster.yaml").read_text()
        loiter=rules.split("\nr2loiter:\n",1)[1].split("\nr2loiterhusk:\n",1)[0]
        self.assertIn("GrantConditionOnAttack:",loiter)
        self.assertIn("RequiresCondition: expended",loiter)
        self.assertIn("RemoveInstead: true",loiter)
        self.assertIn("PauseOnCondition: lowpower",rules)

    def test_original_bilingual_voice_sources_exist(self):
        voices=(art.OUTPUT/"iran-voices.yaml").read_text()
        for clip in re.findall(r"ra2\|modern-factions/audio/([\w-]+)",voices):
            self.assertTrue((ROOT/"engine/openra/mods/ra/bits"/(clip+".wav")).is_file(),clip)
        audio=(art.OUTPUT/"iran-audio.yaml").read_text()
        for actor in art.UNITS: self.assertIn(actor+":\n",audio)
