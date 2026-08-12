"""Generate deterministic original sound effects for the China faction."""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "engine" / "openra" / "mods" / "ra" / "bits"
RATE = 44_100
SEED = 20_260_812


SOUNDS = {
    "china-network-deploy.wav": ("network", 0.72, 610),
    "china-network-fold.wav": ("network", 0.56, 430),
    "china-role-aa.wav": ("ui", 0.34, 1160),
    "china-role-at.wav": ("ui", 0.34, 780),
    "china-command-online.wav": ("network", 0.92, 880),
    "china-rifle.wav": ("gun", 0.28, 170),
    "china-network-carbine.wav": ("gun", 0.25, 210),
    "china-portable-launch.wav": ("launch", 0.70, 460),
    "china-missile-impact.wav": ("impact", 0.88, 72),
    "china-redspear-rifle.wav": ("gun", 0.48, 125),
    "china-qilin-fire.wav": ("heavy", 0.92, 58),
    "china-heavy-impact.wav": ("impact", 0.84, 64),
    "china-ugv-cannon.wav": ("gun", 0.38, 190),
    "china-zbd-cannon.wav": ("gun", 0.43, 155),
    "china-zbd-missile.wav": ("launch", 0.62, 520),
    "china-longbow-launch.wav": ("launch", 1.20, 260),
    "china-air-missile.wav": ("launch", 0.72, 720),
    "china-drone-release.wav": ("drone", 0.58, 320),
    "china-drone-impact.wav": ("impact", 0.92, 78),
    "china-heli-cannon.wav": ("gun", 0.56, 142),
    "china-heli-rocket.wav": ("launch", 0.70, 590),
    "china-naval-missile.wav": ("launch", 0.82, 410),
    "china-naval-gun.wav": ("heavy", 0.76, 70),
    "china-carrier-launch.wav": ("drone", 1.08, 250),
    "china-ship-sink.wav": ("sink", 1.65, 48),
    "china-mantis-launch.wav": ("launch", 0.68, 680),
    "china-patrol-missile.wav": ("launch", 0.61, 540),
    "china-landing-ramp.wav": ("heavy", 0.78, 46),
    "china-torpedo.wav": ("launch", 0.90, 190),
    "china-bastion-fire.wav": ("heavy", 0.62, 82),
    "china-skyshield-launch.wav": ("launch", 0.74, 630),
    "china-spectrum-pulse.wav": ("network", 0.88, 520),
}


def render(kind: str, duration: float, base: float, rng: random.Random) -> list[float]:
    samples: list[float] = []
    noise = 0.0
    phase = 0.0
    for index in range(round(duration * RATE)):
        t = index / RATE
        p = t / duration
        white = rng.uniform(-1, 1)
        noise = noise * (0.86 if kind in {"launch", "drone", "sink"} else 0.42) + white * (0.14 if kind in {"launch", "drone", "sink"} else 0.58)
        attack = min(1.0, t * 120)
        release = max(0.0, min(1.0, (1 - p) * (5 if kind != "sink" else 2.2)))
        if kind == "network":
            phase += math.tau * (base + 520 * p) / RATE
            signal = 0.45 * math.sin(phase) + 0.20 * math.sin(math.tau * base * 1.5 * t)
            for pulse in (0.08, duration * 0.48):
                signal += math.exp(-110 * abs(t - pulse)) * math.sin(math.tau * (base + 280) * t) * 0.36
        elif kind == "ui":
            signal = math.sin(math.tau * base * t) * math.exp(-6 * t) + 0.35 * math.sin(math.tau * base * 1.5 * t) * math.exp(-9 * t)
        elif kind == "gun":
            signal = noise * math.exp(-26 * t) * 1.15 + math.sin(math.tau * base * t) * math.exp(-14 * t) * 0.65
        elif kind == "heavy":
            signal = noise * math.exp(-18 * t) * 1.25 + math.sin(math.tau * base * t) * math.exp(-7 * t) * 0.95
        elif kind == "impact":
            signal = noise * math.exp(-15 * t) * 1.20 + math.sin(math.tau * (base - 20 * p) * t) * math.exp(-6 * t)
        elif kind == "launch":
            phase += math.tau * (base + 1900 * p * p) / RATE
            signal = math.sin(phase) * (0.74 - 0.30 * p) + noise * (0.30 + 0.44 * p)
        elif kind == "drone":
            phase += math.tau * (base + 440 * p) / RATE
            signal = 0.48 * math.sin(phase) + 0.18 * math.sin(phase * 2) + noise * 0.30
        else:
            signal = math.sin(math.tau * (base - 20 * p) * t) * math.exp(-2.4 * t) + noise * math.exp(-2.1 * t) * 0.76
            signal += math.exp(-85 * abs(t - duration * 0.58)) * math.sin(math.tau * 310 * t) * 0.36
        samples.append(signal * attack * release)
    return samples


def write(path: Path, values: list[float]) -> None:
    mean = sum(values) / len(values)
    values = [math.tanh((value - mean) * 1.22) for value in values]
    peak = max(0.001, max(abs(value) for value in values))
    encoded = struct.pack("<" + "h" * len(values), *(round(max(-1, min(1, value * 0.72 / peak)) * 32767) for value in values))
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes(encoded)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for index, (filename, spec) in enumerate(SOUNDS.items()):
        write(OUTPUT / filename, render(*spec, random.Random(SEED + index * 137)))
        print(filename)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
