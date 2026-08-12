"""Generate disclosed generic Turkish/English synthetic radio voices.

The selected Microsoft neural voices are generic service voices. They do not
imitate or identify any real military member, public figure, or political
leader. Provenance is written beside the tracked concept sources.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import shutil
import struct
import subprocess
import tempfile
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import edge_tts

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"engine"/"openra"/"mods"/"ra"/"bits"
PROVENANCE=ROOT/"assets"/"turkey-faction"/"voice-provenance.json"


@dataclass(frozen=True)
class Line:
	filename: str
	language: str
	voice: str
	text: str
	role: str


TR="tr-TR-AhmetNeural"; EN="en-US-GuyNeural"
LINES=(
	Line("tr-infantry-select-tr.wav","tr-TR",TR,"Hazırız.","infantry"), Line("tr-infantry-select-en.wav","en-US",EN,"Squad ready.","infantry"),
	Line("tr-infantry-move-tr.wav","tr-TR",TR,"İlerliyoruz.","infantry"), Line("tr-infantry-move-en.wav","en-US",EN,"Moving out.","infantry"),
	Line("tr-infantry-attack-tr.wav","tr-TR",TR,"Hedef belirlendi.","infantry"), Line("tr-infantry-attack-en.wav","en-US",EN,"Target marked.","infantry"),
	Line("tr-vehicle-select-tr.wav","tr-TR",TR,"Mürettebat hazır.","vehicle crew"), Line("tr-vehicle-select-en.wav","en-US",EN,"Crew standing by.","vehicle crew"),
	Line("tr-vehicle-action-tr.wav","tr-TR",TR,"Harekete geçiyoruz.","vehicle crew"), Line("tr-vehicle-action-en.wav","en-US",EN,"Formation moving.","vehicle crew"),
	Line("tr-air-select-tr.wav","tr-TR",TR,"Hava unsuru hazır.","air crew"), Line("tr-air-select-en.wav","en-US",EN,"Air element ready.","air crew"),
	Line("tr-air-action-tr.wav","tr-TR",TR,"Rota onaylandı.","air crew"), Line("tr-air-action-en.wav","en-US",EN,"Course confirmed.","air crew"),
	Line("tr-naval-select-tr.wav","tr-TR",TR,"Deniz unsuru hazır.","naval crew"), Line("tr-naval-select-en.wav","en-US",EN,"Surface group ready.","naval crew"),
	Line("tr-naval-action-tr.wav","tr-TR",TR,"Seyir düzenine geçiyoruz.","naval crew"), Line("tr-naval-action-en.wav","en-US",EN,"Taking sea-control station.","naval crew"),
	Line("tr-greywolf-select-tr.wav","tr-TR",TR,"Görev net.","fictional commando"), Line("tr-greywolf-select-en.wav","en-US",EN,"Mission is clear.","fictional commando"),
	Line("tr-greywolf-move-tr.wav","tr-TR",TR,"Sessizce ilerliyorum.","fictional commando"), Line("tr-greywolf-move-en.wav","en-US",EN,"Moving under cover.","fictional commando"),
	Line("tr-greywolf-attack-tr.wav","tr-TR",TR,"Takım, işaretime göre.","fictional commando"), Line("tr-greywolf-attack-en.wav","en-US",EN,"Team, on my mark.","fictional commando"),
	Line("turkey-mission-opening-tr.wav","tr-TR",TR,"Boğaz hattı kesildi. Üssü kurun, drone ağını açın ve deniz koridorunu geri alın.","mission controller"),
	Line("turkey-mission-opening-en.wav","en-US",EN,"The strait is blocked. Build the base, bring the drone net online, and reopen the sea lane.","mission controller"),
	Line("turkey-mission-tech-tr.wav","tr-TR",TR,"Birleşik harekât ağı etkin. Kara, hava ve deniz üretimi kullanılabilir.","mission controller"),
	Line("turkey-mission-tech-en.wav","en-US",EN,"Combined operations network active. Land, air, and naval production are available.","mission controller"),
	Line("turkey-mission-harbor-tr.wav","tr-TR",TR,"Liman rölesi güvenli. Amfibi grup için geçiş açıldı.","mission controller"),
	Line("turkey-mission-harbor-en.wav","en-US",EN,"Harbor relay secure. The amphibious group has a route through.","mission controller"),
	Line("turkey-mission-victory-tr.wav","tr-TR",TR,"İki deniz yolu da açık. Straits Shield tamamlandı.","mission controller"),
	Line("turkey-mission-victory-en.wav","en-US",EN,"Both sea lanes are open. Straits Shield is complete.","mission controller"),
)


def finish(path: Path) -> dict[str,float|int]:
	with wave.open(str(path),"rb") as source:
		rate=source.getframerate(); frames=source.readframes(source.getnframes())
	values=list(struct.unpack("<"+"h"*(len(frames)//2),frames)); rng=random.Random(path.name); beep=[round(1250*math.sin(math.tau*1080*i/rate)) for i in range(round(rate*.045))]+[0]*round(rate*.025)
	finished=beep+[round((value+rng.randint(-70,70))*min(1,index/max(1,rate*.015),(len(values)-index)/max(1,rate*.025))) for index,value in enumerate(values)]
	peak=max(1,max(abs(v) for v in finished)); gain=min(1,26000/peak); encoded=struct.pack("<"+"h"*len(finished),*(max(-32768,min(32767,round(v*gain))) for v in finished))
	with wave.open(str(path),"wb") as target: target.setnchannels(1); target.setsampwidth(2); target.setframerate(rate); target.writeframes(encoded)
	return {"sample_rate":rate,"channels":1,"sample_width_bits":16,"duration_seconds":round(len(finished)/rate,3)}


async def run() -> None:
	ffmpeg=shutil.which("ffmpeg")
	if not ffmpeg: raise RuntimeError("ffmpeg is required")
	OUTPUT.mkdir(parents=True,exist_ok=True); records=[]
	with tempfile.TemporaryDirectory(prefix="openra-turkey-voice-") as temporary:
		for line in LINES:
			print(f"Synthesizing {line.filename} ({line.voice})"); mp3=Path(temporary)/(Path(line.filename).stem+".mp3"); wav=OUTPUT/line.filename
			await edge_tts.Communicate(line.text,line.voice,rate="-4%",pitch="-2Hz").save(str(mp3))
			subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-y","-i",str(mp3),"-af","highpass=f=180,lowpass=f=6000,acompressor=threshold=-21dB:ratio=2.5:attack=6:release=90,loudnorm=I=-18:TP=-2:LRA=7","-ar","44100","-ac","1","-c:a","pcm_s16le",str(wav)],check=True)
			records.append({**asdict(line),**finish(wav),"synthetic_voice_disclosed":True,"real_person_imitation":False})
	PROVENANCE.parent.mkdir(parents=True,exist_ok=True); PROVENANCE.write_text(json.dumps({"generator":"edge-tts + ffmpeg","generated_utc":"2026-08-12","lines":records},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__": asyncio.run(run())
