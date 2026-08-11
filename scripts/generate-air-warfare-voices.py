#!/usr/bin/env python3
"""Generate disclosed bilingual synthetic responses for Red Sea air units.

The selected cloud voices are generic product voices. They are not prompted or
processed to resemble any real person. Exact text and voice metadata are
written alongside the source assets for review.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "engine" / "openra" / "mods" / "ra" / "bits"
DEFAULT_PROVENANCE = ROOT / "assets" / "red-sea-2026" / "air-voice-provenance.json"

LINES = (
    {
        "file": "rsa-air-select-ar.wav",
        "language": "ar-SA",
        "voice": "ar-SA-HamedNeural",
        "text": "جاهزون للدورية الجوية.",
        "translation": "Ready for air patrol.",
    },
    {
        "file": "rsa-air-select-en.wav",
        "language": "en-US",
        "voice": "en-US-GuyNeural",
        "text": "Air patrol standing by.",
        "translation": "Air patrol standing by.",
    },
    {
        "file": "rsa-air-action-ar.wav",
        "language": "ar-SA",
        "voice": "ar-SA-HamedNeural",
        "text": "تم الاستلام، نتجه إلى الهدف.",
        "translation": "Acknowledged, heading to the target.",
    },
    {
        "file": "rsa-air-action-en.wav",
        "language": "en-US",
        "voice": "en-US-GuyNeural",
        "text": "Copy. Moving to intercept.",
        "translation": "Copy. Moving to intercept.",
    },
    {
        "file": "rye-drone-select-ar.wav",
        "language": "ar-YE",
        "voice": "ar-YE-SalehNeural",
        "text": "الطائرة المسيّرة جاهزة.",
        "translation": "The drone is ready.",
    },
    {
        "file": "rye-drone-select-en.wav",
        "language": "en-US",
        "voice": "en-US-GuyNeural",
        "text": "Drone link established.",
        "translation": "Drone link established.",
    },
    {
        "file": "rye-drone-action-ar.wav",
        "language": "ar-YE",
        "voice": "ar-YE-SalehNeural",
        "text": "تم تثبيت الهدف.",
        "translation": "Target locked.",
    },
    {
        "file": "rye-drone-action-en.wav",
        "language": "en-US",
        "voice": "en-US-GuyNeural",
        "text": "Target set. Committing.",
        "translation": "Target set. Committing.",
    },
)


async def synthesize(line: dict[str, str], output: Path, ffmpeg: str, temporary: Path) -> None:
    source = temporary / f"{Path(line['file']).stem}.mp3"
    await edge_tts.Communicate(line["text"], line["voice"], rate="+8%").save(str(source))
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-af",
            "highpass=f=180,lowpass=f=5200,acompressor=threshold=-18dB:ratio=3:attack=5:release=80,loudnorm=I=-18:TP=-2:LRA=7",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        check=True,
    )


async def generate(output: Path, provenance: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to encode OpenRA WAV files")

    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="air-warfare-voices-") as temporary_name:
        temporary = Path(temporary_name)
        for line in LINES:
            await synthesize(line, output / line["file"], ffmpeg, temporary)

    payload = {
        "generated_utc_cutoff": "2026-08-11",
        "provider": "Microsoft Edge neural text-to-speech via edge-tts",
        "synthetic_voice_disclosed": True,
        "imitates_real_person": False,
        "processing": "Generic neural voice; speed +8%; band-pass, compression, loudness normalization; mono PCM WAV.",
        "lines": list(LINES),
    }
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    args = parser.parse_args()
    asyncio.run(generate(args.output.resolve(), args.provenance.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
