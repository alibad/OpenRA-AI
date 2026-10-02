#!/usr/bin/env python3
"""Generate disclosed bilingual synthetic responses for Red Sea air units.

Speech comes from local, redistributable engines (voice_engines.py): Kokoro-82M
for English and Chatterbox Multilingual for Arabic, cloned from a Kokoro-spoken
reference. Nothing is prompted or processed to resemble any real person. Exact
text, engine and voice metadata are written alongside the source assets.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from voice_engines import ENGINES, QA, Synthesizer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "engine" / "openra" / "mods" / "ra" / "bits"
DEFAULT_PROVENANCE = ROOT / "assets" / "red-sea-2026" / "air-voice-provenance.json"

LINES = (
    {
        "file": "rsa-air-select-ar.wav",
        "language": "ar-SA",
        "voice": "saudi-crew",
        "text": "جاهزون للدورية الجوية.",
        "translation": "Ready for air patrol.",
    },
    {
        "file": "rsa-air-select-en.wav",
        "language": "en-US",
        "voice": "saudi-crew",
        "text": "Air patrol standing by.",
        "translation": "Air patrol standing by.",
    },
    {
        "file": "rsa-air-action-ar.wav",
        "language": "ar-SA",
        "voice": "saudi-crew",
        "text": "تم الاستلام، نتجه إلى الهدف.",
        "translation": "Acknowledged, heading to the target.",
    },
    {
        "file": "rsa-air-action-en.wav",
        "language": "en-US",
        "voice": "saudi-crew",
        "text": "Copy. Moving to intercept.",
        "translation": "Copy. Moving to intercept.",
    },
    {
        "file": "rye-drone-select-ar.wav",
        "language": "ar-YE",
        "voice": "yemen-crew",
        "text": "الطائرة المسيّرة جاهزة.",
        "translation": "The drone is ready.",
    },
    {
        "file": "rye-drone-select-en.wav",
        "language": "en-US",
        "voice": "yemen-crew",
        "text": "Drone link established.",
        "translation": "Drone link established.",
    },
    {
        "file": "rye-drone-action-ar.wav",
        "language": "ar-YE",
        "voice": "yemen-crew",
        "text": "تم تثبيت الهدف.",
        "translation": "Target locked.",
    },
    {
        "file": "rye-drone-action-en.wav",
        "language": "en-US",
        "voice": "yemen-crew",
        "text": "Target set. Committing.",
        "translation": "Target set. Committing.",
    },
)


FILTERS = "highpass=f=180,lowpass=f=5200,acompressor=threshold=-18dB:ratio=3:attack=5:release=80,loudnorm=I=-18:TP=-2:LRA=7"


def synthesize(line: dict[str, str], output: Path, ffmpeg: str, temporary: Path, synth: Synthesizer) -> dict[str, object]:
    source = temporary / f"{Path(line['file']).stem}.raw.wav"
    # Tempo 1.08 stands in for the old edge-tts rate of +8%. `voice` is a voice_engines speaker id.
    record = synth.render(line["text"], line["language"], line["voice"], source, rate=1.08)
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
            FILTERS,
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
    return {**line, **record, "processing": "ffmpeg " + FILTERS}


def generate(output: Path, provenance: Path, selected: set[str] | None = None) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to encode OpenRA WAV files")

    output.mkdir(parents=True, exist_ok=True)
    records = []
    synth = Synthesizer()
    try:
        with tempfile.TemporaryDirectory(prefix="air-warfare-voices-") as temporary_name:
            temporary = Path(temporary_name)
            for line in LINES:
                if selected and line["file"] not in selected:
                    continue
                records.append(synthesize(line, output / line["file"], ffmpeg, temporary, synth))
    finally:
        synth.close()

    payload = {
        "generator": "voice_engines.py + ffmpeg",
        "engines": ENGINES,
        "qa": QA,
        "synthetic_voice_disclosed": True,
        "imitates_real_person": False,
        "processing": "Generic synthetic voice; tempo 1.08; band-pass, compression, loudness normalization; mono PCM WAV.",
        "lines": records,
    }
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    args = parser.parse_args()
    generate(args.output.resolve(), args.provenance.resolve(), set(args.filenames) or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
