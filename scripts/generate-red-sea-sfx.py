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


def write_wav(path: Path, samples: list[float], peak_level: float = 0.72) -> None:
    mean = sum(samples) / len(samples)
    dc_free = [sample - mean for sample in samples]
    # Gentle saturation controls procedural spikes while retaining transients.
    mastered = [math.tanh(sample * 1.28) for sample in dc_free]
    peak = max(0.001, max(abs(sample) for sample in mastered))
    scale = peak_level / peak
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, sample * scale)) * 32767))
        for sample in mastered
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(frames)


def interceptor(rng: random.Random) -> list[float]:
    duration = 0.78
    samples: list[float] = []
    phase = 0.0
    low_noise = 0.0
    for index in range(int(duration * SAMPLE_RATE)):
        t = index / SAMPLE_RATE
        p = t / duration
        frequency = 310 + 3900 * p * p
        phase += math.tau * frequency / SAMPLE_RATE
        low_noise = low_noise * 0.88 + rng.uniform(-1, 1) * 0.12
        ignition = max(0.0, t - 0.11)
        launch = math.sin(phase) * (0.56 - 0.28 * p) * min(1.0, ignition * 45)
        whoosh = low_noise * (0.16 + 0.42 * p) * min(1.0, ignition * 35)
        lock_a = math.exp(-95 * abs(t - 0.035)) * math.sin(math.tau * 1080 * t)
        lock_b = math.exp(-95 * abs(t - 0.095)) * math.sin(math.tau * 1380 * t)
        motor = math.sin(math.tau * 78 * t) * math.exp(-9 * max(0, t - 0.11))
        samples.append((launch + whoosh + 0.22 * lock_a + 0.18 * lock_b + 0.22 * motor) * envelope(p, 0.008, 0.16))
    return samples


def mobile_launch(rng: random.Random) -> list[float]:
    duration = 1.25
    samples: list[float] = []
    rumble = 0.0
    hiss = 0.0
    for index in range(int(duration * SAMPLE_RATE)):
        t = index / SAMPLE_RATE
        p = t / duration
        rumble = rumble * 0.96 + rng.uniform(-1, 1) * 0.04
        hiss = hiss * 0.55 + rng.uniform(-1, 1) * 0.45
        launch_time = max(0.0, t - 0.14)
        ignition = math.sin(math.tau * (58 + 52 * p) * t) * math.exp(-3.4 * launch_time)
        exhaust = hiss * min(1.0, launch_time * 28) * math.exp(-1.35 * launch_time)
        body = rumble * min(1.0, launch_time * 22) * (0.52 - 0.20 * p)
        clamp = math.exp(-125 * abs(t - 0.045)) * math.sin(math.tau * 175 * t)
        door = math.exp(-85 * abs(t - 0.105)) * math.sin(math.tau * 92 * t)
        samples.append((0.30 * clamp + 0.22 * door + 0.58 * ignition + 0.64 * exhaust + body) * envelope(p, 0.006, 0.22))
    return samples


def drone_strike(rng: random.Random) -> list[float]:
    duration = 0.95
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
        release_click = math.exp(-210 * abs(t - 0.16)) * (0.6 * mechanical + math.sin(math.tau * 240 * t))
        dive = math.sin(math.tau * (240 + 1850 * p * p) * t) * max(0.0, p - 0.16)
        air = mechanical * max(0.0, p - 0.12) * (1.0 - 0.55 * p)
        samples.append(
            (0.20 * propeller + 0.48 * release_click + 0.42 * dive + 0.16 * air)
            * envelope(p, 0.018, 0.17)
        )
    return samples


def drone_loiter(rng: random.Random) -> list[float]:
    """Build a quiet, seamless one-second pusher-propeller loop."""

    duration = 1.0
    samples: list[float] = []
    for index in range(int(duration * SAMPLE_RATE)):
        t = index / SAMPLE_RATE
        # Integer-cycle harmonics and modulation meet at the loop boundary.
        propeller = (
            math.sin(math.tau * 84 * t)
            + 0.38 * math.sin(math.tau * 168 * t)
            + 0.16 * math.sin(math.tau * 252 * t)
        )
        flutter = 0.82 + 0.12 * math.sin(math.tau * 4 * t) + 0.06 * math.sin(math.tau * 7 * t)
        airframe = 0.08 * math.sin(math.tau * 336 * t + 0.4)
        samples.append(propeller * flutter + airframe)
    return samples


def drone_impact(rng: random.Random) -> list[float]:
    duration = 1.05
    samples: list[float] = []
    crackle = 0.0
    dust = 0.0
    for index in range(int(duration * SAMPLE_RATE)):
        t = index / SAMPLE_RATE
        p = t / duration
        white = rng.uniform(-1, 1)
        crackle = crackle * 0.34 + white * 0.66
        dust = dust * 0.965 + white * 0.035
        snap = crackle * math.exp(-48 * t)
        pressure = math.sin(math.tau * (64 - 28 * p) * t) * math.exp(-7.8 * t)
        fragments = (
            math.exp(-105 * abs(t - 0.09)) * math.sin(math.tau * 690 * t)
            + math.exp(-92 * abs(t - 0.16)) * math.sin(math.tau * 920 * t)
        )
        tail = dust * math.exp(-3.4 * t) * min(1.0, t * 24)
        samples.append(
            (1.15 * snap + 0.82 * pressure + 0.30 * fragments + 0.44 * tail)
            * envelope(p, 0.001, 0.24)
        )
    return samples


def m1_fire(rng: random.Random) -> list[float]:
    duration = 0.92
    samples: list[float] = []
    blast_noise = 0.0
    tail_noise = 0.0
    for index in range(int(duration * SAMPLE_RATE)):
        t = index / SAMPLE_RATE
        p = t / duration
        white = rng.uniform(-1, 1)
        blast_noise = blast_noise * 0.28 + white * 0.72
        tail_noise = tail_noise * 0.94 + white * 0.06
        crack = blast_noise * math.exp(-42 * t)
        pressure = math.sin(math.tau * (54 - 16 * p) * t) * math.exp(-7.0 * t)
        breech = math.sin(math.tau * 128 * t) * math.exp(-115 * abs(t - 0.055))
        desert_tail = tail_noise * math.exp(-3.8 * t) * min(1.0, t * 30)
        samples.append((1.30 * crack + 0.92 * pressure + 0.30 * breech + 0.36 * desert_tail) * envelope(p, 0.001, 0.20))
    return samples


def m1_impact(rng: random.Random) -> list[float]:
    duration = 0.78
    samples: list[float] = []
    debris = 0.0
    dust = 0.0
    for index in range(int(duration * SAMPLE_RATE)):
        t = index / SAMPLE_RATE
        p = t / duration
        white = rng.uniform(-1, 1)
        debris = debris * 0.48 + white * 0.52
        dust = dust * 0.97 + white * 0.03
        strike = debris * math.exp(-35 * t)
        ground = math.sin(math.tau * (72 - 30 * p) * t) * math.exp(-8.5 * t)
        fragments = (
            math.exp(-150 * abs(t - 0.075)) * math.sin(math.tau * 540 * t)
            + math.exp(-130 * abs(t - 0.135)) * math.sin(math.tau * 710 * t)
        )
        samples.append((0.95 * strike + 0.70 * ground + 0.28 * fragments + 0.40 * dust * math.exp(-3.2 * t)) * envelope(p, 0.001, 0.22))
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
        "redsea-interceptor.wav": (interceptor(rng), 0.72),
        "redsea-mobile-launch.wav": (mobile_launch(rng), 0.72),
        "redsea-drone-strike.wav": (drone_strike(rng), 0.68),
        "redsea-drone-loiter.wav": (drone_loiter(rng), 0.26),
        "redsea-drone-impact.wav": (drone_impact(rng), 0.72),
        "redsea-m1-fire.wav": (m1_fire(rng), 0.72),
        "redsea-m1-impact.wav": (m1_impact(rng), 0.72),
    }
    for name, (samples, peak_level) in outputs.items():
        path = args.output / name
        write_wav(path, samples, peak_level)
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
