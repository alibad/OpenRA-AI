"""Generate disclosed synthetic radio for Bab al-Mandab Passage.

This mission-specific pipeline is intentionally separate from the shared Red
Sea and air-session voice list. Speech comes from local, redistributable engines
(voice_engines.py: Kokoro-82M for English, Chatterbox Multilingual for Arabic);
no real person is imitated. FFmpeg produces OpenRA-ready 44.1 kHz mono PCM WAVs.
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


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "engine" / "openra" / "mods" / "ra" / "bits"
PROVENANCE = ROOT / "assets" / "red-sea-2026" / "mandab-voice-provenance.json"


@dataclass(frozen=True)
class VoiceLine:
    filename: str
    language: str
    voice: str
    text: str
    role: str


LINES = (
    VoiceLine("redsea-mandab-opening-ar.wav", "ar-SA", "redsea-control", "هنا قيادة الممر. ابنوا مركز التقنية واستعدوا للعبور.", "Mandab passage control"),
    VoiceLine("redsea-mandab-readiness-en.wav", "en-US", "redsea-control", "Tech online. Sweep the three coastal sectors.", "Saudi maritime command"),
    VoiceLine("redsea-mandab-recon-ar.wav", "ar-SA", "redsea-control", "اكتمل المسح. منصات متحركة تهدد الممر. حيّدوها.", "Saudi maritime command"),
    VoiceLine("redsea-mandab-shipping-en.wav", "en-US", "redsea-control", "Civilian transit has begun. Hold both Mayyun lanes.", "Civilian shipping control"),
    VoiceLine("redsea-mandab-recovery-ar.wav", "ar-SA", "redsea-control", "سفينة متأخرة. قاطرة المرافقة تعيدها إلى المسار.", "Civilian shipping control"),
    VoiceLine("redsea-mandab-loss-en.wav", "en-US", "redsea-control", "Civilian ship lost. Protect the remaining convoy.", "Civilian shipping control"),
    VoiceLine("redsea-mandab-final-ar.wav", "ar-SA", "redsea-control", "بدأ الهجوم الأخير. أبقوا الممر مفتوحاً حتى اكتمال العبور.", "Saudi maritime command"),
    VoiceLine("redsea-mandab-beacon-lost-en.wav", "en-US", "redsea-control", "Navigation beacon lost. Optional objective failed.", "Mandab passage control"),
    VoiceLine("redsea-mandab-victory-ar.wav", "ar-SA", "redsea-control", "اكتمل العبور. الممر آمن.", "Mandab passage control"),
    VoiceLine("redsea-mandab-failure-en.wav", "en-US", "redsea-control", "Passage Control lost. Civilian transit suspended.", "Mandab passage control"),
)


def radio_finish(path: Path) -> None:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        samples = list(struct.unpack("<" + "h" * source.getnframes(), source.readframes(source.getnframes())))
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError(f"unexpected WAV layout for {path.name}")

    rng = random.Random(path.name)
    beep_frames = int(rate * 0.055)
    finished = [int(1500 * math.sin(2 * math.pi * 1120 * i / rate)) for i in range(beep_frames)]
    finished += [0] * int(rate * 0.035)
    for index, sample in enumerate(samples):
        fade = min(1.0, index / max(1, int(rate * 0.018)), (len(samples) - index) / max(1, int(rate * 0.025)))
        finished.append(round((sample + rng.randint(-85, 85)) * max(0.0, fade)))

    gain = min(1.0, 26000 / max(1, max(abs(value) for value in finished)))
    encoded = struct.pack("<" + "h" * len(finished), *(max(-32768, min(32767, round(value * gain))) for value in finished))
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(encoded)


def synthesize(line: VoiceLine, ffmpeg: str, temporary: Path, synth: Synthesizer,
               output: Path = OUTPUT) -> dict[str, object]:
    raw = temporary / f"{Path(line.filename).stem}.raw.wav"
    wav = output / line.filename
    # Tempo 0.94 stands in for the old edge-tts rate of -6%. `voice` is a voice_engines speaker id.
    record = synth.render(line.text, line.language, line.voice, raw, rate=0.94)
    filters = (
        "highpass=f=220,lowpass=f=5400,acompressor=threshold=-20dB:ratio=2.7:attack=6:release=90,"
        "loudnorm=I=-18:TP=-2:LRA=7"
    )
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-af", filters,
         "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )
    radio_finish(wav)
    with wave.open(str(wav), "rb") as check:
        return {
            **asdict(line),
            **record,
            "processing": "ffmpeg " + filters + "; radio beep, noise and fades",
            "sample_rate": check.getframerate(),
            "channels": check.getnchannels(),
            "sample_width_bits": check.getsampwidth() * 8,
            "duration_seconds": round(check.getnframes() / check.getframerate(), 3),
            "synthetic_voice_disclosed": True,
            "real_person_imitation": False,
        }


def run(output: Path = OUTPUT, provenance: Path = PROVENANCE, selected: set[str] | None = None) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to master the generated voices")
    output.mkdir(parents=True, exist_ok=True)
    provenance.parent.mkdir(parents=True, exist_ok=True)
    synth = Synthesizer()
    try:
        with tempfile.TemporaryDirectory(prefix="openra-mandab-voice-") as directory:
            records = []
            for line in LINES:
                if selected and line.filename not in selected:
                    continue
                print(f"Synthesizing {line.filename} ({line.voice})")
                records.append(synthesize(line, ffmpeg, Path(directory), synth, output))
    finally:
        synth.close()
    provenance.write_text(
        json.dumps(
            {
                "generator": "voice_engines.py + ffmpeg",
                "engines": ENGINES,
                "qa": QA,
                "disclosure": "Generic synthetic voices; no real person is imitated.",
                "mission": "bab-al-mandab-passage-2026",
                "lines": records,
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--provenance", type=Path, default=PROVENANCE)
    args = parser.parse_args()
    run(args.output.resolve(), args.provenance.resolve(), set(args.filenames) or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
