"""Generate disclosed, generic Mandarin/English China faction voices.

The synthetic speakers come from local, redistributable engines (see
voice_engines.py): Kokoro-82M for English, Chatterbox Multilingual for
Mandarin, cloned from a Kokoro-spoken reference. They are not modeled on, named
after, or intended to represent any real person or military figure.
All outputs are mastered to 44.1 kHz mono PCM WAV for OpenRA.
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
PROVENANCE = ROOT / "assets" / "china-faction" / "voice-provenance.json"


@dataclass(frozen=True)
class VoiceLine:
    filename: str
    language: str
    voice: str
    text: str
    role: str
    radio: bool = False


# `voice` is a speaker id from voice_engines.SPEAKERS.
INF = "china-infantry"
CREW = "china-crew"
CTRL = "china-control"
LINES = (
    VoiceLine("rcn-infantry-select-zh.wav", "zh-CN", INF, "步兵小组，通信正常。", "generic infantry"),
    VoiceLine("rcn-infantry-select-en.wav", "en-US", INF, "Infantry team, network check complete.", "generic infantry"),
    VoiceLine("rcn-infantry-action-zh.wav", "zh-CN", INF, "收到，协同前进。", "generic infantry"),
    VoiceLine("rcn-infantry-action-en.wav", "en-US", INF, "Copy. Advancing in coordination.", "generic infantry"),
    VoiceLine("rcn-vehicle-select-zh.wav", "zh-CN", CREW, "装甲平台在线。", "generic vehicle crew"),
    VoiceLine("rcn-vehicle-select-en.wav", "en-US", CREW, "Armored platform online.", "generic vehicle crew"),
    VoiceLine("rcn-vehicle-action-zh.wav", "zh-CN", CREW, "路线确认，开始机动。", "generic vehicle crew"),
    VoiceLine("rcn-vehicle-action-en.wav", "en-US", CREW, "Route confirmed. Moving now.", "generic vehicle crew"),
    VoiceLine("rcn-air-select-zh.wav", "zh-CN", CREW, "空中编队等待指令。", "generic aircrew"),
    VoiceLine("rcn-air-select-en.wav", "en-US", CREW, "Air element awaiting tasking.", "generic aircrew"),
    VoiceLine("rcn-air-action-zh.wav", "zh-CN", CREW, "目标已同步，正在接近。", "generic aircrew"),
    VoiceLine("rcn-air-action-en.wav", "en-US", CREW, "Target synchronized. Approaching.", "generic aircrew"),
    VoiceLine("rcn-naval-select-zh.wav", "zh-CN", CREW, "海上编队通信畅通。", "generic naval crew"),
    VoiceLine("rcn-naval-select-en.wav", "en-US", CREW, "Maritime group, communications clear.", "generic naval crew"),
    VoiceLine("rcn-naval-action-zh.wav", "zh-CN", CREW, "航向确认，舰队前进。", "generic naval crew"),
    VoiceLine("rcn-naval-action-en.wav", "en-US", CREW, "Course confirmed. Fleet underway.", "generic naval crew"),
    VoiceLine("rcn-redspear-select-zh.wav", "zh-CN", INF, "赤矛接入指挥网络。", "fictional Red Spear operator"),
    VoiceLine("rcn-redspear-select-en.wav", "en-US", INF, "Red Spear linked to the command network.", "fictional Red Spear operator"),
    VoiceLine("rcn-redspear-action-zh.wav", "zh-CN", INF, "精确坐标已接收。", "fictional Red Spear operator"),
    VoiceLine("rcn-redspear-action-en.wav", "en-US", INF, "Precision coordinates received.", "fictional Red Spear operator"),
    VoiceLine("china-haitan-opening-zh.wav", "zh-CN", CTRL, "演训区受到干扰。部署网络专家，恢复战场信息链。", "fictional exercise controller", True),
    VoiceLine("china-haitan-network-en.wav", "en-US", CTRL, "Network picture restored. Amphibious route data is now available.", "fictional exercise controller", True),
    VoiceLine("china-haitan-amphibious-zh.wav", "zh-CN", CTRL, "两栖编队已进入海湾，掩护登陆部队。", "fictional exercise controller", True),
    VoiceLine("china-haitan-combined-en.wav", "en-US", CTRL, "Coordinate armor, aviation, and naval fire on the final control node.", "fictional exercise controller", True),
    VoiceLine("china-haitan-warning-zh.wav", "zh-CN", CTRL, "发现无人机群。切换便携导弹小组的防空模式。", "fictional exercise controller", True),
    VoiceLine("china-haitan-secure-en.wav", "en-US", CTRL, "Exercise control confirms all network nodes secure.", "fictional exercise controller", True),
)


def finish_wav(path: Path, radio: bool) -> None:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        frames = source.readframes(source.getnframes())
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError(f"unexpected WAV layout for {path.name}")

    samples = list(struct.unpack("<" + "h" * (len(frames) // 2), frames))
    rng = random.Random(path.name)
    prefix = []
    if radio:
        count = int(rate * 0.045)
        prefix = [int(1200 * math.sin(2 * math.pi * 1050 * i / rate)) for i in range(count)]
        prefix += [0] * int(rate * 0.025)

    finished = prefix[:]
    for index, sample in enumerate(samples):
        noise = rng.randint(-70, 70) if radio else rng.randint(-18, 18)
        fade = min(1.0, index / max(1, int(rate * 0.012)), (len(samples) - index) / max(1, int(rate * 0.02)))
        finished.append(round((sample + noise) * max(0.0, fade)))

    peak = max(1, max(abs(value) for value in finished))
    gain = min(1.0, 25500 / peak)
    encoded = struct.pack("<" + "h" * len(finished), *(max(-32768, min(32767, round(value * gain))) for value in finished))
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(encoded)


def synthesize(line: VoiceLine, ffmpeg: str, temporary: Path, synth: Synthesizer,
               output: Path = OUTPUT) -> dict[str, object]:
    raw = temporary / (Path(line.filename).stem + ".raw.wav")
    wav = output / line.filename
    # Tempo 0.95 stands in for the old edge-tts rate of -5%.
    record = synth.render(line.text, line.language, line.voice, raw, rate=0.95,
                          expressive="Red Spear" in line.role)
    filters = "highpass=f=190,lowpass=f=5900,acompressor=threshold=-21dB:ratio=2.5:attack=6:release=90,loudnorm=I=-19:TP=-2:LRA=8"
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-af", filters,
                    "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True)
    finish_wav(wav, line.radio)
    with wave.open(str(wav), "rb") as check:
        return {
            **asdict(line),
            **record,
            "processing": "ffmpeg " + filters + ("; radio beep, noise and fades" if line.radio else "; noise floor and fades"),
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
        with tempfile.TemporaryDirectory(prefix="openra-china-voice-") as directory:
            records = []
            for line in LINES:
                if selected and line.filename not in selected:
                    continue
                print(f"Synthesizing {line.filename} ({line.voice})")
                records.append(synthesize(line, ffmpeg, Path(directory), synth, output))
    finally:
        synth.close()
    provenance.write_text(json.dumps({
        "generator": "voice_engines.py + ffmpeg",
        "engines": ENGINES,
        "qa": QA,
        "disclosure": "Generic synthetic voices; no real person is represented or imitated.",
        "lines": records,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
