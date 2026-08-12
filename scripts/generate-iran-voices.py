"""Generate disclosed generic Persian/English radio voices.

Microsoft neural voices are used as generic synthetic performers.  No line is
written to resemble a real person and Shadow One is explicitly fictional.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import wave

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "engine" / "openra" / "mods" / "ra" / "bits"
PROVENANCE = ROOT / "assets" / "iran-faction" / "voice-provenance.json"


@dataclass(frozen=True)
class Line:
    filename: str
    language: str
    voice: str
    text: str
    role: str


def bilingual(prefix: str, role: str, phrases: dict[str, tuple[str, str]]) -> list[Line]:
    lines: list[Line] = []
    for action, (persian, english) in phrases.items():
        lines.append(Line(f"{prefix}-{action}-fa.wav", "fa-IR", "fa-IR-FaridNeural", persian, role))
        lines.append(Line(f"{prefix}-{action}-en.wav", "en-US", "en-US-GuyNeural", english, role))
    return lines


LINES = tuple(
    bilingual("iran-inf", "generic infantry", {
        "select": ("آماده‌ایم.", "Section ready."),
        "move": ("در حال حرکت.", "Moving now."),
        "action": ("دستور دریافت شد.", "Order received."),
        "attack": ("درگیر می‌شویم.", "Engaging."),
    })
    + bilingual("iran-veh", "generic vehicle crew", {
        "select": ("خدمه آماده است.", "Crew standing by."),
        "move": ("ستون حرکت می‌کند.", "Column moving."),
        "action": ("مسیر تأیید شد.", "Route confirmed."),
        "attack": ("سامانه روی هدف است.", "System on target."),
    })
    + bilingual("iran-air", "generic aircrew", {
        "select": ("پرواز آماده است.", "Flight ready."),
        "move": ("به سمت نقطه مسیر.", "Proceeding to waypoint."),
        "action": ("دریافت شد، کنترل.", "Copy, control."),
        "attack": ("هدف در دید است.", "Target in sight."),
    })
    + bilingual("iran-drone", "generic drone operator", {
        "select": ("پیوند داده برقرار است.", "Data link established."),
        "move": ("مسیر پرواز به‌روز شد.", "Flight path updated."),
        "action": ("تصویر روشن است.", "Picture is clear."),
        "attack": ("نشانه‌گذاری کامل شد.", "Designation complete."),
    })
    + bilingual("iran-naval", "generic naval crew", {
        "select": ("خدمه دریایی آماده است.", "Naval crew ready."),
        "move": ("به سوی مسیر ساحلی.", "Taking the coastal route."),
        "action": ("فرمان دریافت شد.", "Command received."),
        "attack": ("ردیابی تثبیت شد.", "Track is steady."),
    })
    + bilingual("shadow", "fictional Shadow One performer", {
        "select": ("سایه در شبکه است.", "Shadow is on the net."),
        "move": ("بی‌صدا حرکت می‌کنم.", "Moving quietly."),
        "action": ("نقطه ورود مشخص شد.", "Entry point marked."),
        "attack": ("هدف جدا شد.", "Target isolated."),
        "demolish": ("بارگذاری انجام شد.", "Charge is set."),
        "build": ("سایه یک آماده است.", "Shadow One ready."),
    })
)


def radio_finish(path: Path) -> None:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        channels = source.getnchannels()
        width = source.getsampwidth()
        frames = source.readframes(source.getnframes())
    if channels != 1 or width != 2:
        raise ValueError(f"unexpected WAV layout for {path.name}")
    samples = list(struct.unpack("<" + "h" * (len(frames) // 2), frames))
    rng = random.Random(f"iran-radio:{path.name}")
    beep = [round(1250 * math.sin(math.tau * 1040 * i / rate)) for i in range(round(rate * .045))]
    finished = beep + [0] * round(rate * .025)
    for index, sample in enumerate(samples):
        fade = min(1.0, index / max(1, round(rate * .015)), (len(samples) - index) / max(1, round(rate * .025)))
        finished.append(round((sample + rng.randint(-68, 68)) * max(0.0, fade)))
    peak = max(1, max(abs(value) for value in finished))
    gain = min(1.0, 26000 / peak)
    encoded = struct.pack("<" + "h" * len(finished), *(max(-32768, min(32767, round(value * gain))) for value in finished))
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(encoded)


async def render(line: Line, temporary: Path, ffmpeg: str, semaphore: asyncio.Semaphore, only_missing: bool) -> None:
    destination = OUTPUT / line.filename
    if only_missing and destination.exists():
        print(f"keep {line.filename}")
        return
    async with semaphore:
        mp3 = temporary / f"{Path(line.filename).stem}.mp3"
        await edge_tts.Communicate(line.text, line.voice).save(str(mp3))
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(destination)],
            check=True,
        )
        radio_finish(destination)
        print(line.filename)


async def generate(only_missing: bool) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to normalize neural voice output")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="iran-voices-") as directory:
        semaphore = asyncio.Semaphore(4)
        await asyncio.gather(*(render(line, Path(directory), ffmpeg, semaphore, only_missing) for line in LINES))
    PROVENANCE.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE.write_text(json.dumps({
        "generated": "2026-08-12",
        "disclosure": "Generic Microsoft neural voices; no real-person imitation.",
        "lines": [asdict(line) for line in LINES],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-missing", action="store_true")
    args = parser.parse_args()
    asyncio.run(generate(args.only_missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
