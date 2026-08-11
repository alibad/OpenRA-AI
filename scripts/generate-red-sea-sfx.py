from __future__ import annotations

import argparse
import math
import random
import struct
import wave
from pathlib import Path


SAMPLE_RATE = 44_100
SEED = 20_260_811


def envelope(position: float, attack: float = 0.02, release: float = 0.18) -> float:
    if position < attack:
        return position / attack
    if position > 1.0 - release:
        return max(0.0, (1.0 - position) / release)
    return 1.0


def write_wav(path: Path, samples: list[float]) -> None:
    peak = max(0.001, max(abs(sample) for sample in samples))
    scale = 0.92 / peak
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, sample * scale)) * 32767))
        for sample in samples
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(frames)


def interceptor(rng: random.Random) -> list[float]:
    duration = 0.62
    samples: list[float] = []
    phase = 0.0
    low_noise = 0.0
    for index in range(int(duration * SAMPLE_RATE)):
        t = index / SAMPLE_RATE
        p = t / duration
        frequency = 380 + 3000 * p * p
        phase += math.tau * frequency / SAMPLE_RATE
        low_noise = low_noise * 0.88 + rng.uniform(-1, 1) * 0.12
        launch = math.sin(phase) * (0.52 - 0.22 * p)
        whoosh = low_noise * (0.18 + 0.32 * p)
        lock_tone = math.sin(math.tau * 1180 * t) * max(0.0, 0.16 - p) * 0.45
        samples.append((launch + whoosh + lock_tone) * envelope(p, 0.015, 0.12))
    return samples


def mobile_launch(rng: random.Random) -> list[float]:
    duration = 1.05
    samples: list[float] = []
    rumble = 0.0
    hiss = 0.0
    for index in range(int(duration * SAMPLE_RATE)):
        t = index / SAMPLE_RATE
        p = t / duration
        rumble = rumble * 0.96 + rng.uniform(-1, 1) * 0.04
        hiss = hiss * 0.55 + rng.uniform(-1, 1) * 0.45
        ignition = math.sin(math.tau * (72 + 44 * p) * t) * math.exp(-4.0 * p)
        exhaust = hiss * (math.sin(math.pi * min(1.0, p * 2.2)) ** 2) * (1.0 - 0.55 * p)
        body = rumble * (0.55 - 0.25 * p)
        samples.append((0.55 * ignition + 0.55 * exhaust + body) * envelope(p, 0.01, 0.2))
    return samples


def drone_strike(rng: random.Random) -> list[float]:
    duration = 0.82
    samples: list[float] = []
    mechanical = 0.0
    for index in range(int(duration * SAMPLE_RATE)):
        t = index / SAMPLE_RATE
        p = t / duration
        propeller = (
            math.sin(math.tau * 92 * t)
            + 0.45 * math.sin(math.tau * 184 * t)
            + 0.2 * math.sin(math.tau * 276 * t)
        )
        mechanical = mechanical * 0.72 + rng.uniform(-1, 1) * 0.28
        release_click = math.exp(-180 * abs(t - 0.12)) * mechanical
        dive = math.sin(math.tau * (260 + 1500 * p * p) * t) * max(0.0, p - 0.12)
        samples.append(
            (0.23 * propeller + 0.36 * release_click + 0.42 * dive + 0.08 * mechanical)
            * envelope(p, 0.025, 0.12)
        )
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate original Red Sea vertical-slice sound effects")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("engine/openra/mods/ra/bits"),
        help="OpenRA package directory for generated WAV files",
    )
    args = parser.parse_args()
    rng = random.Random(SEED)
    outputs = {
        "redsea-interceptor.wav": interceptor(rng),
        "redsea-mobile-launch.wav": mobile_launch(rng),
        "redsea-drone-strike.wav": drone_strike(rng),
    }
    for name, samples in outputs.items():
        path = args.output / name
        write_wav(path, samples)
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
