"""Generate disclosed generic Turkish/English synthetic radio voices.

Speech comes from local, redistributable engines (voice_engines.py): Kokoro-82M
for English and Chatterbox Multilingual for Turkish, cloned from a Kokoro-spoken
reference. No line imitates or identifies any real military member, public
figure, or political leader. Provenance is written beside the tracked concept
sources.
"""

from __future__ import annotations

import argparse
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

from voice_engines import ENGINES, QA, Synthesizer

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


# The voice field is a speaker id from voice_engines.SPEAKERS.
INF="turkey-infantry"; CREW="turkey-crew"; CTRL="turkey-control"
LINES=(
	Line("tr-infantry-select-tr.wav","tr-TR",INF,"Hazırız.","infantry"), Line("tr-infantry-select-en.wav","en-US",INF,"Squad ready.","infantry"),
	Line("tr-infantry-move-tr.wav","tr-TR",INF,"İlerliyoruz.","infantry"), Line("tr-infantry-move-en.wav","en-US",INF,"Moving out.","infantry"),
	Line("tr-infantry-attack-tr.wav","tr-TR",INF,"Hedef belirlendi.","infantry"), Line("tr-infantry-attack-en.wav","en-US",INF,"Target marked.","infantry"),
	Line("tr-vehicle-select-tr.wav","tr-TR",CREW,"Mürettebat hazır.","vehicle crew"), Line("tr-vehicle-select-en.wav","en-US",CREW,"Crew standing by.","vehicle crew"),
	Line("tr-vehicle-action-tr.wav","tr-TR",CREW,"Harekete geçiyoruz.","vehicle crew"), Line("tr-vehicle-action-en.wav","en-US",CREW,"Formation moving.","vehicle crew"),
	Line("tr-air-select-tr.wav","tr-TR",CREW,"Hava unsuru hazır.","air crew"), Line("tr-air-select-en.wav","en-US",CREW,"Air element ready.","air crew"),
	Line("tr-air-action-tr.wav","tr-TR",CREW,"Rota onaylandı.","air crew"), Line("tr-air-action-en.wav","en-US",CREW,"Course confirmed.","air crew"),
	Line("tr-naval-select-tr.wav","tr-TR",CREW,"Deniz unsuru hazır.","naval crew"), Line("tr-naval-select-en.wav","en-US",CREW,"Surface group ready.","naval crew"),
	Line("tr-naval-action-tr.wav","tr-TR",CREW,"Seyir düzenine geçiyoruz.","naval crew"), Line("tr-naval-action-en.wav","en-US",CREW,"Taking sea-control station.","naval crew"),
	Line("tr-greywolf-select-tr.wav","tr-TR",INF,"Görev net.","fictional commando"), Line("tr-greywolf-select-en.wav","en-US",INF,"Mission is clear.","fictional commando"),
	Line("tr-greywolf-move-tr.wav","tr-TR",INF,"Sessizce ilerliyorum.","fictional commando"), Line("tr-greywolf-move-en.wav","en-US",INF,"Moving under cover.","fictional commando"),
	Line("tr-greywolf-attack-tr.wav","tr-TR",INF,"Takım, işaretime göre.","fictional commando"), Line("tr-greywolf-attack-en.wav","en-US",INF,"Team, on my mark.","fictional commando"),
	Line("turkey-mission-opening-tr.wav","tr-TR",CTRL,"Boğaz hattı kesildi. Üssü kurun, drone ağını açın ve deniz koridorunu geri alın.","mission controller"),
	Line("turkey-mission-opening-en.wav","en-US",CTRL,"The strait is blocked. Build the base, bring the drone net online, and reopen the sea lane.","mission controller"),
	Line("turkey-mission-tech-tr.wav","tr-TR",CTRL,"Birleşik harekât ağı etkin. Kara, hava ve deniz üretimi kullanılabilir.","mission controller"),
	Line("turkey-mission-tech-en.wav","en-US",CTRL,"Combined operations network active. Land, air, and naval production are available.","mission controller"),
	Line("turkey-mission-harbor-tr.wav","tr-TR",CTRL,"Liman rölesi güvenli. Amfibi grup için geçiş açıldı.","mission controller"),
	Line("turkey-mission-harbor-en.wav","en-US",CTRL,"Harbor relay secure. The amphibious group has a route through.","mission controller"),
	Line("turkey-mission-victory-tr.wav","tr-TR",CTRL,"İki deniz yolu da açık. Straits Shield tamamlandı.","mission controller"),
	Line("turkey-mission-victory-en.wav","en-US",CTRL,"Both sea lanes are open. Straits Shield is complete.","mission controller"),
)


def finish(path: Path) -> dict[str,float|int]:
	with wave.open(str(path),"rb") as source:
		rate=source.getframerate(); frames=source.readframes(source.getnframes())
	values=list(struct.unpack("<"+"h"*(len(frames)//2),frames)); rng=random.Random(path.name); beep=[round(1250*math.sin(math.tau*1080*i/rate)) for i in range(round(rate*.045))]+[0]*round(rate*.025)
	finished=beep+[round((value+rng.randint(-70,70))*min(1,index/max(1,rate*.015),(len(values)-index)/max(1,rate*.025))) for index,value in enumerate(values)]
	peak=max(1,max(abs(v) for v in finished)); gain=min(1,26000/peak); encoded=struct.pack("<"+"h"*len(finished),*(max(-32768,min(32767,round(v*gain))) for v in finished))
	with wave.open(str(path),"wb") as target: target.setnchannels(1); target.setsampwidth(2); target.setframerate(rate); target.writeframes(encoded)
	return {"sample_rate":rate,"channels":1,"sample_width_bits":16,"duration_seconds":round(len(finished)/rate,3)}


def synthesize(line: Line, ffmpeg: str, temporary: Path, synth: Synthesizer, output: Path=OUTPUT) -> dict[str,object]:
	raw=Path(temporary)/(Path(line.filename).stem+".raw.wav"); wav=output/line.filename
	# Tempo 0.96 stands in for the old edge-tts rate of -4%.
	record=synth.render(line.text,line.language,line.voice,raw,rate=0.96,expressive=line.role=="fictional commando")
	filters="highpass=f=180,lowpass=f=6000,acompressor=threshold=-21dB:ratio=2.5:attack=6:release=90,loudnorm=I=-18:TP=-2:LRA=7"
	subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-y","-i",str(raw),"-af",filters,"-ar","44100","-ac","1","-c:a","pcm_s16le",str(wav)],check=True)
	return {**asdict(line),**record,"processing":"ffmpeg "+filters+"; radio beep, noise and fades",**finish(wav),"synthetic_voice_disclosed":True,"real_person_imitation":False}


def run(output: Path=OUTPUT, provenance: Path=PROVENANCE, selected: set[str]|None=None) -> None:
	ffmpeg=shutil.which("ffmpeg")
	if not ffmpeg: raise RuntimeError("ffmpeg is required")
	output.mkdir(parents=True,exist_ok=True); records=[]; synth=Synthesizer()
	try:
		with tempfile.TemporaryDirectory(prefix="openra-turkey-voice-") as temporary:
			for line in LINES:
				if selected and line.filename not in selected: continue
				print(f"Synthesizing {line.filename} ({line.voice})"); records.append(synthesize(line,ffmpeg,Path(temporary),synth,output))
	finally: synth.close()
	provenance.parent.mkdir(parents=True,exist_ok=True); provenance.write_text(json.dumps({"generator":"voice_engines.py + ffmpeg","engines":ENGINES,"qa":QA,"lines":records},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def main() -> int:
	parser=argparse.ArgumentParser(); parser.add_argument("filenames",nargs="*")
	parser.add_argument("--output",type=Path,default=OUTPUT); parser.add_argument("--provenance",type=Path,default=PROVENANCE)
	args=parser.parse_args(); run(args.output.resolve(),args.provenance.resolve(),set(args.filenames) or None); return 0


if __name__=="__main__": raise SystemExit(main())
