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

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"scripts"))
import ra2_china_assets as art

class ChinaFactionTests(unittest.TestCase):
    def test_deploy_mode_badges_are_conditional_and_clear_of_the_sprite(self):
        source=(art.OUTPUT/"china-roster.yaml").read_text()
        for name,text,condition in (("AT","AT","!aa-mode"),("AA","AA","aa-mode"),("RELAY","LINK","network-deployed")):
            badge=re.search(r"\tWithTextDecoration@"+name+r":\n((?:\t\t[^\n]*\n)+)",source).group(1)
            for field in ("Text: "+text,"RequiresCondition: "+condition,"RequiresSelection: true",
                          "Position: Top","Margin: 0, -14"):
                self.assertIn(field,badge)

    def test_tooltip_descriptions_fit_the_unwrapped_native_panel(self):
        source=(art.OUTPUT/"china-messages.ftl").read_text()
        self.assertNotIn("\\n",source)
        for block in source.split("\n\n"):
            lines=block.splitlines()
            description=next((line.split(" = ",1)[1] for line in lines if "-description = " in line),None)
            if description is None:
                continue
            displayed=[description]+[line.strip() for line in lines if line.startswith(" ")]
            self.assertLessEqual(len(displayed),3)
            self.assertTrue(all(len(line)<=60 for line in displayed),displayed)

    def test_native_shp_has_independent_facings_and_valid_remap(self):
        manifest=json.loads((art.OUTPUT/"china-art/manifest.json").read_text())
        self.assertEqual(set(manifest),set(art.INFANTRY+art.DEFENSES))
        for actor,meta in manifest.items():
            data=(art.OUTPUT/"china-art"/(actor+".shp")).read_bytes()
            zero,w,h,n=struct.unpack_from("<4H",data)
            self.assertEqual((zero,w,h,n),(0,*meta["size"],meta["frames"]))
            self.assertEqual(hashlib.sha256(data).hexdigest(),meta["sha256"])
            self.assertEqual(n,112 if actor in art.INFANTRY else 41)
            frames=[]
            for i in range(n):
                x,y,fw,fh,fmt,offset=struct.unpack_from("<4HB11xI",data,8+i*24)
                self.assertEqual((x,y,fw,fh,fmt),(0,0,w,h,1))
                self.assertLessEqual(offset+w*h,len(data))
                frames.append(data[offset:offset+w*h])
            self.assertTrue(any(16<=p<32 for frame in frames for p in frame),actor)
            self.assertGreater(len(set(frames)),20)
            if actor in art.INFANTRY:
                self.assertEqual(len(set(frames[:8])),8)
                first=art.faction_render(art.soldier(actor),0,(48,48),14,(24,35),True)
                self.assertEqual(art.art.indexed(first),frames[0])

    def test_artwork_keeps_native_sizes_and_clear_infantry_borders(self):
        self.assertEqual(len(art.CHINA_UNITS),17)
        self.assertEqual(len(art.DEFENSES),3)
        for actor in art.CHINA_UNITS+art.DEFENSES:
            with Image.open(art.OUTPUT/"icons"/(actor+".png")) as image:
                self.assertEqual(image.size,(60,48))
        for actor in art.INFANTRY:
            for facing in range(0,1024,128):
                img=art.faction_render(art.soldier(actor),facing,(48,48),14,(24,35),True)
                left,top,right,bottom=img.getchannel("A").getbbox()
                self.assertGreater(left,0)
                self.assertGreater(top,0)
                self.assertLess(right,48)
                self.assertLess(bottom,48)
        with Image.open(art.OUTPUT/"previews/china.png") as image:
            self.assertEqual(image.size,(512,512))

    def test_existing_bilingual_performances_are_valid_audio(self):
        for role in ("infantry","redspear","vehicle","air","naval"):
            for action in ("select","action"):
                for language in ("en","zh"):
                    path=ROOT/"engine/openra/mods/ra/bits"/f"rcn-{role}-{action}-{language}.wav"
                    with wave.open(str(path)) as clip:
                        self.assertGreater(clip.getnframes(),0)
        for sound in ("china-role-aa","china-role-at","china-network-deploy","china-network-fold"):
            with wave.open(str(ROOT/"engine/openra/mods/ra/bits"/(sound+".wav"))) as clip:
                self.assertGreater(clip.getnframes(),0)

    def test_native_infantry_effects_and_ground_depth_are_present(self):
        seq=(art.OUTPUT/"china-roster-sequences.yaml").read_text()
        for actor in art.INFANTRY:
            rule=seq.split(actor+":\n",1)[1].split("\n\n",1)[0]
            self.assertIn("Inherits@MC: ^MindControllable",rule)
            self.assertIn("Offset: 0, -11, 16",rule)
        for actor in art.DEFENSES:
            self.assertIn("Offset: 0, -19, 19",seq.split(actor+":\n",1)[1].split("\n\n",1)[0])

if __name__=="__main__":
    unittest.main()
