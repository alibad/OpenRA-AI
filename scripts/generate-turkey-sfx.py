"""Generate deterministic original Turkey faction weapon and support sounds."""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "engine" / "openra" / "mods" / "ra" / "bits"
RATE = 44100
SEED = 20260812


def write(name: str, samples: list[float], peak: float = .70) -> None:
	mean=sum(samples)/len(samples); values=[math.tanh((s-mean)*1.25) for s in samples]; maximum=max(.001,max(abs(v) for v in values)); gain=peak/maximum
	frames=b"".join(struct.pack("<h",round(max(-1,min(1,v*gain))*32767)) for v in values)
	OUTPUT.mkdir(parents=True,exist_ok=True)
	with wave.open(str(OUTPUT/name),"wb") as target:
		target.setnchannels(1); target.setsampwidth(2); target.setframerate(RATE); target.writeframes(frames)


def gun(rng: random.Random, duration: float, bass: float, bursts: int=1) -> list[float]:
	result=[]; noise=0.; pulse_times=[.025+i*duration*.55/max(1,bursts) for i in range(bursts)]
	for i in range(round(duration*RATE)):
		t=i/RATE; p=t/duration; noise=noise*.32+rng.uniform(-1,1)*.68
		pulse=sum(math.exp(-115*abs(t-x)) for x in pulse_times)
		pressure=math.sin(math.tau*bass*t)*math.exp(-7*t)
		result.append((noise*pulse+.55*pressure)*min(1,t*300)*max(0,(1-p)/.18 if p>.82 else 1))
	return result


def missile(rng: random.Random, duration: float, start: float, end: float) -> list[float]:
	result=[]; hiss=0.; phase=0.
	for i in range(round(duration*RATE)):
		t=i/RATE; p=t/duration; hiss=hiss*.55+rng.uniform(-1,1)*.45; phase+=math.tau*(start+(end-start)*p*p)/RATE
		clamp=math.exp(-130*abs(t-.035))*math.sin(math.tau*170*t)
		result.append((.35*clamp+.62*math.sin(phase)*min(1,t*35)+.44*hiss*min(1,t*28))*(1-p)**.35)
	return result


def impact(rng: random.Random, duration: float, bass: float) -> list[float]:
	result=[]; debris=0.; tail=0.
	for i in range(round(duration*RATE)):
		t=i/RATE; p=t/duration; white=rng.uniform(-1,1); debris=debris*.38+white*.62; tail=tail*.965+white*.035
		result.append(1.05*debris*math.exp(-40*t)+.78*math.sin(math.tau*(bass-20*p)*t)*math.exp(-7*t)+.38*tail*math.exp(-3.2*t))
	return result


def designate(duration: float=.34) -> list[float]:
	result=[]
	for i in range(round(duration*RATE)):
		t=i/RATE; p=t/duration
		beeps=sum(math.exp(-130*abs(t-x))*math.sin(math.tau*f*t) for x,f in ((.03,950),(.14,1260),(.25,1580)))
		result.append(beeps*math.sin(math.pi*p))
	return result


def main() -> int:
	rng=random.Random(SEED)
	outputs={
		"turkey-rifle.wav":gun(rng,.32,115,3), "turkey-greywolf-fire.wav":gun(rng,.30,132,3),
		"turkey-autocannon.wav":gun(rng,.46,86,4), "turkey-tank-fire.wav":gun(rng,.92,52),
		"turkey-howitzer.wav":gun(rng,1.08,44), "turkey-rotor-cannon.wav":gun(rng,.52,78,4),
		"turkey-fighter-cannon.wav":gun(rng,.43,102,4), "turkey-usv-gun.wav":gun(rng,.38,98,3),
		"turkey-at-launch.wav":missile(rng,.70,260,2100), "turkey-aa-launch.wav":missile(rng,.74,420,3300),
		"turkey-drone-launch.wav":missile(rng,.66,330,2100), "turkey-rotor-launch.wav":missile(rng,.72,360,2400),
		"turkey-fighter-missile.wav":missile(rng,.78,480,3600), "turkey-naval-missile.wav":missile(rng,.88,300,2600),
		"turkey-at-impact.wav":impact(rng,.72,78), "turkey-heavy-impact.wav":impact(rng,.94,54),
		"turkey-artillery-impact.wav":impact(rng,1.10,48), "turkey-air-impact.wav":impact(rng,.76,72),
		"turkey-naval-impact.wav":impact(rng,1.02,46), "turkey-designate.wav":designate(),
		"turkey-naval-gun.wav":gun(rng,.96,49),
	}
	for name,samples in outputs.items(): write(name,samples)
	print(f"Generated {len(outputs)} original PCM sound effects in {OUTPUT}")
	return 0


if __name__=="__main__": raise SystemExit(main())
