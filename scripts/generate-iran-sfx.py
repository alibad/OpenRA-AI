"""Generate deterministic original sound effects for the Iran roster."""

from __future__ import annotations

import json
import math
import random
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "engine" / "openra" / "mods" / "ra" / "bits"
PROVENANCE = ROOT / "assets" / "iran-faction" / "sound-provenance.json"
RATE = 44_100


def envelope(position: float, attack: float = .012, release: float = .20) -> float:
    return min(1.0, position / attack, max(0.0, (1 - position) / release))


def synthesize(name: str, duration: float, base: float, sweep: float, noise: float, pulses: int) -> list[float]:
    rng = random.Random(f"iran-faction:{name}:2026-08-12")
    result: list[float] = []
    phase = 0.0
    filtered = 0.0
    for index in range(round(duration * RATE)):
        t = index / RATE
        p = t / duration
        frequency = max(24.0, base + sweep * p * p)
        phase += math.tau * frequency / RATE
        filtered = filtered * .82 + rng.uniform(-1, 1) * .18
        harmonic = math.sin(phase) + .38 * math.sin(phase * 2.01) + .16 * math.sin(phase * .49)
        pulse = 1.0
        if pulses > 1:
            pulse = .36 + .64 * max(0.0, math.sin(math.pi * pulses * p))
        transient = math.exp(-46 * t) * math.sin(math.tau * (base * .55 + 38) * t)
        result.append((.46 * harmonic * pulse + noise * filtered + .34 * transient) * envelope(p))
    return result


def write(path: Path, samples: list[float]) -> None:
    mean = sum(samples) / len(samples)
    shaped = [math.tanh((sample - mean) * 1.24) for sample in samples]
    peak = max(.001, max(abs(sample) for sample in shaped))
    data = b"".join(struct.pack("<h", round(max(-1, min(1, sample * .76 / peak)) * 32767)) for sample in shaped)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes(data)


DEFINITIONS = {
    "iran-rifle.wav": (.22, 104, -16, .44, 1),
    "iran-suppressed.wav": (.19, 132, -24, .18, 1),
    "iran-shadow-fire.wav": (.34, 158, -48, .20, 3),
    "iran-atgm-launch.wav": (.82, 205, 1840, .54, 1),
    "iran-atgm-impact.wav": (.70, 76, -28, .72, 1),
    "iran-sabotage.wav": (1.05, 94, 1240, .42, 3),
    "iran-tank-fire.wav": (.78, 61, -18, .70, 1),
    "iran-heavy-impact.wav": (1.10, 48, -12, .78, 1),
    "iran-raad-launch.wav": (.78, 290, 2950, .42, 1),
    "iran-missile-impact.wav": (.72, 82, -30, .68, 1),
    "iran-fajr-launch.wav": (1.22, 118, 1320, .63, 2),
    "iran-coastal-launch.wav": (1.35, 96, 1650, .66, 1),
    "iran-air-missile.wav": (.68, 340, 3300, .38, 1),
    "iran-air-cannon.wav": (.42, 124, -35, .52, 4),
    "iran-heli-cannon.wav": (.48, 98, -21, .54, 4),
    "iran-heli-rocket.wav": (.76, 245, 1820, .46, 2),
    "iran-drone-release.wav": (.58, 510, -160, .22, 2),
    "iran-loiter-impact.wav": (.96, 69, -20, .76, 1),
    "iran-naval-launch.wav": (.92, 178, 2240, .48, 2),
    "iran-torpedo.wav": (.88, 72, 310, .30, 2),
}


def main() -> int:
    records = []
    for name, definition in DEFINITIONS.items():
        write(OUTPUT / name, synthesize(name, *definition))
        records.append({"file": name, "method": "deterministic procedural PCM", "seed": f"iran-faction:{name}:2026-08-12"})
        print(name)
    PROVENANCE.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE.write_text(json.dumps({"generated": "2026-08-12", "sample_rate": RATE, "files": records}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
