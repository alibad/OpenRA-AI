"""Generate disclosed synthetic bilingual radio and unit voices.

This intentionally uses generic Microsoft neural voices and does not imitate a
real person.  Outputs are radio-mastered 44.1 kHz mono PCM WAV files suitable
for OpenRA's built-in WAV loader.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import shutil
import struct
import subprocess
import tempfile
import wave
from dataclasses import dataclass, asdict
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "engine" / "openra" / "mods" / "ra" / "bits"
PROVENANCE = ROOT / "assets" / "red-sea-2026" / "voice-provenance.json"


@dataclass(frozen=True)
class VoiceLine:
    filename: str
    language: str
    voice: str
    text: str
    role: str
    radio: bool = True


LINES = (
    VoiceLine("redsea-jizan-opening-en.wav", "en-US", "en-US-GuyNeural", "Radar Node Seven is offline. Capture it with your engineer and establish layered air defense.", "Jizan controller"),
    VoiceLine("redsea-jizan-radar-ar.wav", "ar-SA", "ar-SA-HamedNeural", "محطة الرادار سبعة متوقفة. أعد تشغيلها بواسطة المهندس، وانشر الدفاع الجوي.", "Saudi command"),
    VoiceLine("redsea-jizan-drone-warning-en.wav", "en-US", "en-US-GuyNeural", "Air defense warning. Multiple low altitude tracks are approaching the corridor.", "Air-defense net"),
    VoiceLine("redsea-jizan-launchers-ar.wav", "ar-SA", "ar-SA-HamedNeural", "تم تحديد موقع منصتي إطلاق متنقلتين. دمروهما قبل دخول القافلة إلى الممر.", "Saudi command"),
    VoiceLine("redsea-jizan-convoy-ar.wav", "ar-SA", "ar-SA-HamedNeural", "القافلة دخلت الممر. حافظوا على التغطية حتى بوابة الميناء.", "Saudi command"),
    VoiceLine("redsea-jizan-convoy-loss-en.wav", "en-US", "en-US-GuyNeural", "Convoy vehicle lost. Keep the remaining trucks moving.", "Jizan controller"),
    VoiceLine("redsea-jizan-secure-en.wav", "en-US", "en-US-GuyNeural", "Convoy inside the port perimeter. The corridor is secure.", "Jizan controller"),
    VoiceLine("redsea-jizan-infrastructure-lost-en.wav", "en-US", "en-US-GuyNeural", "Critical infrastructure has been lost.", "Jizan controller"),
    VoiceLine("rsa-select-1.wav", "ar-SA", "ar-SA-HamedNeural", "جاهزون.", "Saudi vehicle crew", False),
    VoiceLine("rsa-select-2.wav", "ar-SA", "ar-SA-HamedNeural", "الدفاع الجوي متصل.", "Saudi vehicle crew", False),
    VoiceLine("rsa-action-1.wav", "ar-SA", "ar-SA-HamedNeural", "تم الاستلام.", "Saudi vehicle crew", False),
    VoiceLine("rsa-action-2.wav", "ar-SA", "ar-SA-HamedNeural", "نتحرك الآن.", "Saudi vehicle crew", False),
    VoiceLine("rye-select-1.wav", "ar-YE", "ar-YE-SalehNeural", "نحن جاهزون.", "Yemeni vehicle crew", False),
    VoiceLine("rye-select-2.wav", "ar-YE", "ar-YE-SalehNeural", "بانتظار الأمر.", "Yemeni vehicle crew", False),
    VoiceLine("rye-action-1.wav", "ar-YE", "ar-YE-SalehNeural", "على الطريق.", "Yemeni vehicle crew", False),
    VoiceLine("rye-action-2.wav", "ar-YE", "ar-YE-SalehNeural", "نحو الهدف.", "Yemeni vehicle crew", False),
    VoiceLine("redsea-hodeidah-opening-ar.wav", "ar-YE", "ar-YE-SalehNeural", "طريق الإغاثة جاهز. احموا الميناء وانقلوا الإمدادات إلى نقطة التوزيع الداخلية.", "Yemen coast command"),
    VoiceLine("redsea-hodeidah-relief-en.wav", "en-US", "en-US-GuyNeural", "Relief convoy departing Port Control. Keep the diagonal corridor clear.", "Hodeidah controller"),
    VoiceLine("redsea-hodeidah-sweep-ar.wav", "ar-YE", "ar-YE-SalehNeural", "تحذير. مسح جوي خلال خمس عشرة ثانية. انشروا الوحدات المتحركة خارج منطقة الميناء.", "Yemen coast command"),
    VoiceLine("redsea-hodeidah-strike-en.wav", "en-US", "en-US-GuyNeural", "Exposed mobile tracks confirmed. Strike force entering the corridor.", "Surveillance warning"),
    VoiceLine("redsea-hodeidah-evac-ar.wav", "ar-YE", "ar-YE-SalehNeural", "قافلة الإجلاء الأخيرة تتحرك نحو الميناء. أبقوا الطريق مفتوحاً.", "Yemen coast command"),
    VoiceLine("redsea-hodeidah-convoy-loss-en.wav", "en-US", "en-US-GuyNeural", "Lifeline vehicle lost. Protect the remaining convoy.", "Hodeidah controller"),
    VoiceLine("redsea-hodeidah-secure-ar.wav", "ar-YE", "ar-YE-SalehNeural", "وصلت القافلة الأخيرة إلى الميناء. خط الإغاثة آمن.", "Yemen coast command"),
    VoiceLine("redsea-hodeidah-infrastructure-lost-en.wav", "en-US", "en-US-GuyNeural", "Critical civilian infrastructure has been lost.", "Hodeidah controller"),
    VoiceLine("rsa-inf-select-ar.wav", "ar-SA", "ar-SA-HamedNeural", "الحرس جاهز.", "Saudi infantry", False),
    VoiceLine("rsa-inf-select-en.wav", "en-US", "en-US-GuyNeural", "Guard unit ready.", "Saudi infantry", False),
    VoiceLine("rsa-inf-action-ar.wav", "ar-SA", "ar-SA-HamedNeural", "نتحرك الآن.", "Saudi infantry", False),
    VoiceLine("rsa-inf-action-en.wav", "en-US", "en-US-GuyNeural", "Moving to position.", "Saudi infantry", False),
    VoiceLine("rsa-jtac-select-ar.wav", "ar-SA", "ar-SA-HamedNeural", "المراقب الجوي متصل.", "Saudi JTAC", False),
    VoiceLine("rsa-jtac-select-en.wav", "en-US", "en-US-GuyNeural", "JTAC network online.", "Saudi JTAC", False),
    VoiceLine("rsa-jtac-action-ar.wav", "ar-SA", "ar-SA-HamedNeural", "تم تحديد الهدف.", "Saudi JTAC", False),
    VoiceLine("rsa-jtac-action-en.wav", "en-US", "en-US-GuyNeural", "Target marked for guided fire.", "Saudi JTAC", False),
    VoiceLine("rsa-falcon-select-ar.wav", "ar-SA", "ar-SA-HamedNeural", "فالكون واحد جاهز.", "Falcon One", False),
    VoiceLine("rsa-falcon-select-en.wav", "en-US", "en-US-GuyNeural", "Falcon One, standing by.", "Falcon One", False),
    VoiceLine("rsa-falcon-move-ar.wav", "ar-SA", "ar-SA-HamedNeural", "سأصل بصمت.", "Falcon One", False),
    VoiceLine("rsa-falcon-move-en.wav", "en-US", "en-US-GuyNeural", "Moving quiet.", "Falcon One", False),
    VoiceLine("rsa-falcon-action-ar.wav", "ar-SA", "ar-SA-HamedNeural", "الضربة الدقيقة جاهزة.", "Falcon One", False),
    VoiceLine("rsa-falcon-action-en.wav", "en-US", "en-US-GuyNeural", "Precision strike designated.", "Falcon One", False),
    VoiceLine("rsa-falcon-build-ar.wav", "ar-SA", "ar-SA-HamedNeural", "فالكون في الميدان.", "Falcon One", False),
    VoiceLine("rsa-falcon-build-en.wav", "en-US", "en-US-GuyNeural", "Falcon is in the field.", "Falcon One", False),
    VoiceLine("rye-inf-select-ar.wav", "ar-YE", "ar-YE-SalehNeural", "رجال الجبل جاهزون.", "Yemeni infantry", False),
    VoiceLine("rye-inf-select-en.wav", "en-US", "en-US-GuyNeural", "Mountain unit ready.", "Yemeni infantry", False),
    VoiceLine("rye-inf-action-ar.wav", "ar-YE", "ar-YE-SalehNeural", "نعرف هذا الطريق.", "Yemeni infantry", False),
    VoiceLine("rye-inf-action-en.wav", "en-US", "en-US-GuyNeural", "We know this ground.", "Yemeni infantry", False),
    VoiceLine("rye-spot-select-ar.wav", "ar-YE", "ar-YE-SalehNeural", "الطائرة المسيرة في الجو.", "Yemeni drone spotter", False),
    VoiceLine("rye-spot-select-en.wav", "en-US", "en-US-GuyNeural", "Drone feed is live.", "Yemeni drone spotter", False),
    VoiceLine("rye-spot-action-ar.wav", "ar-YE", "ar-YE-SalehNeural", "بيانات الإطلاق جاهزة.", "Yemeni drone spotter", False),
    VoiceLine("rye-spot-action-en.wav", "en-US", "en-US-GuyNeural", "Launcher guidance updated.", "Yemeni drone spotter", False),
    VoiceLine("rye-ghost-select-ar.wav", "ar-YE", "ar-YE-SalehNeural", "الشبح يستمع.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-select-en.wav", "en-US", "en-US-GuyNeural", "The Ghost is listening.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-move-ar.wav", "ar-YE", "ar-YE-SalehNeural", "لن يروني.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-move-en.wav", "en-US", "en-US-GuyNeural", "They will not see me.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-action-ar.wav", "ar-YE", "ar-YE-SalehNeural", "الشحنة مزروعة.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-action-en.wav", "en-US", "en-US-GuyNeural", "Remote charge planted.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-build-ar.wav", "ar-YE", "ar-YE-SalehNeural", "الشبح بينكم.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-build-en.wav", "en-US", "en-US-GuyNeural", "The Ghost walks among you.", "Wadi Ghost", False),
)


def radio_finish(path: Path, enabled: bool) -> None:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        channels = source.getnchannels()
        width = source.getsampwidth()
        frames = source.readframes(source.getnframes())
    if channels != 1 or width != 2:
        raise ValueError(f"unexpected WAV layout for {path.name}")

    samples = list(struct.unpack("<" + "h" * (len(frames) // 2), frames))
    rng = random.Random(path.name)
    prefix: list[int] = []
    if enabled:
        beep_frames = int(rate * 0.055)
        prefix = [int(1500 * math.sin(2 * math.pi * 1120 * i / rate)) for i in range(beep_frames)]
        prefix += [0] * int(rate * 0.035)

    finished: list[int] = prefix
    for index, sample in enumerate(samples):
        noise = rng.randint(-85, 85) if enabled else rng.randint(-25, 25)
        fade = min(1.0, index / max(1, int(rate * 0.018)), (len(samples) - index) / max(1, int(rate * 0.025)))
        finished.append(round((sample + noise) * max(0.0, fade)))

    peak = max(1, max(abs(value) for value in finished))
    gain = min(1.0, 26000 / peak)
    encoded = struct.pack("<" + "h" * len(finished), *(max(-32768, min(32767, round(value * gain))) for value in finished))
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(encoded)


async def synthesize(line: VoiceLine, ffmpeg: str, temporary: Path) -> dict[str, object]:
    mp3 = temporary / (Path(line.filename).stem + ".mp3")
    wav = OUTPUT / line.filename
    communicator = edge_tts.Communicate(line.text, line.voice, rate="-6%", pitch="-2Hz")
    await communicator.save(str(mp3))

    filters = (
        "highpass=f=220,lowpass=f=5400,acompressor=threshold=-20dB:ratio=2.7:attack=6:release=90,"
        "loudnorm=I=-18:TP=-2:LRA=7"
        if line.radio
        else "highpass=f=120,lowpass=f=7200,acompressor=threshold=-22dB:ratio=2.2:attack=5:release=80,loudnorm=I=-19:TP=-2:LRA=8"
    )
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp3), "-af", filters,
         "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )
    radio_finish(wav, line.radio)
    with wave.open(str(wav), "rb") as check:
        return {
            **asdict(line),
            "sample_rate": check.getframerate(),
            "channels": check.getnchannels(),
            "sample_width_bits": check.getsampwidth() * 8,
            "duration_seconds": round(check.getnframes() / check.getframerate(), 3),
            "synthetic_voice_disclosed": True,
        }


async def run(selected: set[str] | None = None) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to master the generated voices")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    PROVENANCE.parent.mkdir(parents=True, exist_ok=True)
    lines = [line for line in LINES if not selected or line.filename in selected]
    with tempfile.TemporaryDirectory(prefix="openra-red-sea-voice-") as directory:
        records = []
        for line in lines:
            print(f"Synthesizing {line.filename} ({line.voice})")
            records.append(await synthesize(line, ffmpeg, Path(directory)))
    PROVENANCE.write_text(json.dumps({"generator": "edge-tts + ffmpeg", "lines": records}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*")
    args = parser.parse_args()
    asyncio.run(run(set(args.filenames) or None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
