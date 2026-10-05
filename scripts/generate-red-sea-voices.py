"""Generate disclosed synthetic bilingual radio and unit voices.

Speech comes from local, redistributable engines (voice_engines.py): Kokoro-82M
for English and Chatterbox Multilingual (Modern Standard Arabic) for Arabic,
cloned from a Kokoro-spoken reference; no real person is imitated. Outputs are
radio-mastered 44.1 kHz mono PCM WAV files suitable for OpenRA's built-in WAV
loader.
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
from dataclasses import dataclass, asdict
from pathlib import Path

from voice_engines import ENGINES, QA, Synthesizer


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "engine" / "openra" / "mods" / "ra" / "bits"
PROVENANCE = ROOT / "assets" / "red-sea-2026" / "voice-provenance.json"
# RA2-only lines ship with the RA2 overlay; the Classic engine bits stay untouched.
RA2_OUTPUT = ROOT / "apps" / "installer" / "ra2" / "modern-factions" / "audio"
RA2_PROVENANCE = ROOT / "assets" / "red-sea-2026" / "ra2-voice-provenance.json"


@dataclass(frozen=True)
class VoiceLine:
    filename: str
    language: str
    voice: str  # speaker id from voice_engines.SPEAKERS
    text: str
    role: str
    radio: bool = True


LINES = (
    VoiceLine("redsea-jizan-opening-en.wav", "en-US", "redsea-control", "Radar Node Seven is offline. Capture it with your engineer and establish layered air defense.", "Jizan controller"),
    VoiceLine("redsea-jizan-radar-ar.wav", "ar-SA", "redsea-control", "محطة الرادار سبعة متوقفة. أعد تشغيلها بواسطة المهندس، وانشر الدفاع الجوي.", "Saudi command"),
    VoiceLine("redsea-jizan-drone-warning-en.wav", "en-US", "redsea-control", "Air defense warning. Multiple low altitude tracks are approaching the corridor.", "Air-defense net"),
    VoiceLine("redsea-jizan-launchers-ar.wav", "ar-SA", "redsea-control", "تم تحديد موقع منصتي إطلاق متنقلتين. دمروهما قبل دخول القافلة إلى الممر.", "Saudi command"),
    VoiceLine("redsea-jizan-convoy-ar.wav", "ar-SA", "redsea-control", "القافلة دخلت الممر. حافظوا على التغطية حتى بوابة الميناء.", "Saudi command"),
    VoiceLine("redsea-jizan-convoy-loss-en.wav", "en-US", "redsea-control", "Convoy vehicle lost. Keep the remaining trucks moving.", "Jizan controller"),
    VoiceLine("redsea-jizan-secure-en.wav", "en-US", "redsea-control", "Convoy inside the port perimeter. The corridor is secure.", "Jizan controller"),
    VoiceLine("redsea-jizan-infrastructure-lost-en.wav", "en-US", "redsea-control", "Critical infrastructure has been lost.", "Jizan controller"),
    VoiceLine("rsa-select-1.wav", "ar-SA", "saudi-crew", "جاهزون.", "Saudi vehicle crew", False),
    VoiceLine("rsa-select-2.wav", "ar-SA", "saudi-crew", "الدفاع الجوي متصل.", "Saudi vehicle crew", False),
    VoiceLine("rsa-action-1.wav", "ar-SA", "saudi-crew", "تم الاستلام.", "Saudi vehicle crew", False),
    VoiceLine("rsa-action-2.wav", "ar-SA", "saudi-crew", "نتحرك الآن.", "Saudi vehicle crew", False),
    VoiceLine("rye-select-1.wav", "ar-YE", "yemen-crew", "نحن جاهزون.", "Yemeni vehicle crew", False),
    VoiceLine("rye-select-2.wav", "ar-YE", "yemen-crew", "بانتظار الأمر.", "Yemeni vehicle crew", False),
    VoiceLine("rye-action-1.wav", "ar-YE", "yemen-crew", "على الطريق.", "Yemeni vehicle crew", False),
    VoiceLine("rye-action-2.wav", "ar-YE", "yemen-crew", "نحو الهدف.", "Yemeni vehicle crew", False),
    VoiceLine("redsea-hodeidah-opening-ar.wav", "ar-YE", "redsea-control", "طريق الإغاثة جاهز. احموا الميناء وانقلوا الإمدادات إلى نقطة التوزيع الداخلية.", "Yemen coast command"),
    VoiceLine("redsea-hodeidah-relief-en.wav", "en-US", "redsea-control", "Relief convoy departing Port Control. Keep the diagonal corridor clear.", "Hodeidah controller"),
    VoiceLine("redsea-hodeidah-sweep-ar.wav", "ar-YE", "redsea-control", "تحذير. مسح جوي خلال خمس عشرة ثانية. انشروا الوحدات المتحركة خارج منطقة الميناء.", "Yemen coast command"),
    VoiceLine("redsea-hodeidah-strike-en.wav", "en-US", "redsea-control", "Exposed mobile tracks confirmed. Strike force entering the corridor.", "Surveillance warning"),
    VoiceLine("redsea-hodeidah-evac-ar.wav", "ar-YE", "redsea-control", "قافلة الإجلاء الأخيرة تتحرك نحو الميناء. أبقوا الطريق مفتوحاً.", "Yemen coast command"),
    VoiceLine("redsea-hodeidah-convoy-loss-en.wav", "en-US", "redsea-control", "Lifeline vehicle lost. Protect the remaining convoy.", "Hodeidah controller"),
    VoiceLine("redsea-hodeidah-secure-ar.wav", "ar-YE", "redsea-control", "وصلت القافلة الأخيرة إلى الميناء. خط الإغاثة آمن.", "Yemen coast command"),
    VoiceLine("redsea-hodeidah-infrastructure-lost-en.wav", "en-US", "redsea-control", "Critical civilian infrastructure has been lost.", "Hodeidah controller"),
    VoiceLine("rsa-inf-select-ar.wav", "ar-SA", "saudi-infantry", "الحرس جاهز.", "Saudi infantry", False),
    VoiceLine("rsa-inf-select-en.wav", "en-US", "saudi-infantry", "Guard unit ready.", "Saudi infantry", False),
    VoiceLine("rsa-inf-action-ar.wav", "ar-SA", "saudi-infantry", "نتحرك الآن.", "Saudi infantry", False),
    VoiceLine("rsa-inf-action-en.wav", "en-US", "saudi-infantry", "Moving to position.", "Saudi infantry", False),
    VoiceLine("rsa-jtac-select-ar.wav", "ar-SA", "saudi-infantry", "المراقب الجوي متصل.", "Saudi JTAC", False),
    VoiceLine("rsa-jtac-select-en.wav", "en-US", "saudi-infantry", "JTAC network online.", "Saudi JTAC", False),
    VoiceLine("rsa-jtac-action-ar.wav", "ar-SA", "saudi-infantry", "تم تحديد الهدف.", "Saudi JTAC", False),
    VoiceLine("rsa-jtac-action-en.wav", "en-US", "saudi-infantry", "Target marked for guided fire.", "Saudi JTAC", False),
    VoiceLine("rsa-falcon-select-ar.wav", "ar-SA", "saudi-infantry", "الصقر واحد جاهز.", "Falcon One", False),
    VoiceLine("rsa-falcon-select-en.wav", "en-US", "saudi-infantry", "Falcon One, standing by.", "Falcon One", False),
    VoiceLine("rsa-falcon-move-ar.wav", "ar-SA", "saudi-infantry", "سأصل بصمت.", "Falcon One", False),
    VoiceLine("rsa-falcon-move-en.wav", "en-US", "saudi-infantry", "Moving quiet.", "Falcon One", False),
    VoiceLine("rsa-falcon-action-ar.wav", "ar-SA", "saudi-infantry", "الضربة الدقيقة جاهزة.", "Falcon One", False),
    VoiceLine("rsa-falcon-action-en.wav", "en-US", "saudi-infantry", "Precision strike designated.", "Falcon One", False),
    VoiceLine("rsa-falcon-build-ar.wav", "ar-SA", "saudi-infantry", "الصقر في الميدان.", "Falcon One", False),
    VoiceLine("rsa-falcon-build-en.wav", "en-US", "saudi-infantry", "Falcon is in the field.", "Falcon One", False),
    VoiceLine("rye-inf-select-ar.wav", "ar-YE", "yemen-infantry", "رجال الجبل جاهزون.", "Yemeni infantry", False),
    VoiceLine("rye-inf-select-en.wav", "en-US", "yemen-infantry", "Mountain unit ready.", "Yemeni infantry", False),
    VoiceLine("rye-inf-action-ar.wav", "ar-YE", "yemen-infantry", "نعرف هذا الطريق.", "Yemeni infantry", False),
    VoiceLine("rye-inf-action-en.wav", "en-US", "yemen-infantry", "We know this ground.", "Yemeni infantry", False),
    VoiceLine("rye-spot-select-ar.wav", "ar-YE", "yemen-infantry", "الطائرة المسيرة في الجو.", "Yemeni drone spotter", False),
    VoiceLine("rye-spot-select-en.wav", "en-US", "yemen-infantry", "Drone feed is live.", "Yemeni drone spotter", False),
    VoiceLine("rye-spot-action-ar.wav", "ar-YE", "yemen-infantry", "بيانات الإطلاق جاهزة.", "Yemeni drone spotter", False),
    VoiceLine("rye-spot-action-en.wav", "en-US", "yemen-infantry", "Launcher guidance updated.", "Yemeni drone spotter", False),
    VoiceLine("rye-ghost-select-ar.wav", "ar-YE", "yemen-infantry", "الشبح يستمع.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-select-en.wav", "en-US", "yemen-infantry", "The Ghost is listening.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-move-ar.wav", "ar-YE", "yemen-infantry", "لن يروني.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-move-en.wav", "en-US", "yemen-infantry", "They will not see me.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-action-ar.wav", "ar-YE", "yemen-infantry", "الشحنة مزروعة.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-action-en.wav", "en-US", "yemen-infantry", "Remote charge planted.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-build-ar.wav", "ar-YE", "yemen-infantry", "الشبح بينكم.", "Wadi Ghost", False),
    VoiceLine("rye-ghost-build-en.wav", "en-US", "yemen-infantry", "The Ghost walks among you.", "Wadi Ghost", False),
)


# Red Alert 2 vehicle and naval crews. Classic had Arabic-only vehicle
# acknowledgements and no Red Sea naval voices; RA2 pairs each with English.
RA2_LINES = (
    VoiceLine("rsa-veh-select-ar.wav", "ar-SA", "saudi-crew", "طاقم المدرعة جاهز.", "Saudi vehicle crew", False),
    VoiceLine("rsa-veh-select-en.wav", "en-US", "saudi-crew", "Armor crew ready.", "Saudi vehicle crew", False),
    VoiceLine("rsa-veh-action-ar.wav", "ar-SA", "saudi-crew", "تم الاستلام، نتحرك.", "Saudi vehicle crew", False),
    VoiceLine("rsa-veh-action-en.wav", "en-US", "saudi-crew", "Copy. Moving out.", "Saudi vehicle crew", False),
    VoiceLine("rsa-naval-select-ar.wav", "ar-SA", "saudi-crew", "السفينة جاهزة، الحساسات تعمل.", "Saudi naval crew", False),
    VoiceLine("rsa-naval-select-en.wav", "en-US", "saudi-crew", "Bridge here. Sensors up.", "Saudi naval crew", False),
    VoiceLine("rsa-naval-action-ar.wav", "ar-SA", "saudi-crew", "تغيير المسار الآن.", "Saudi naval crew", False),
    VoiceLine("rsa-naval-action-en.wav", "en-US", "saudi-crew", "Coming about. Steady.", "Saudi naval crew", False),
    VoiceLine("rye-veh-select-ar.wav", "ar-YE", "yemen-crew", "الطاقم جاهز على الطريق.", "Yemeni vehicle crew", False),
    VoiceLine("rye-veh-select-en.wav", "en-US", "yemen-crew", "Crew ready. Engine running.", "Yemeni vehicle crew", False),
    VoiceLine("rye-veh-action-ar.wav", "ar-YE", "yemen-crew", "نتحرك بسرعة.", "Yemeni vehicle crew", False),
    VoiceLine("rye-veh-action-en.wav", "en-US", "yemen-crew", "Moving fast. Stay low.", "Yemeni vehicle crew", False),
    VoiceLine("rye-naval-select-ar.wav", "ar-YE", "yemen-crew", "الزورق جاهز، الرابط متصل.", "Yemeni coastal crew", False),
    VoiceLine("rye-naval-select-en.wav", "en-US", "yemen-crew", "Boat ready. Link is up.", "Yemeni coastal crew", False),
    VoiceLine("rye-naval-action-ar.wav", "ar-YE", "yemen-crew", "نقترب من الساحل.", "Yemeni coastal crew", False),
    VoiceLine("rye-naval-action-en.wav", "en-US", "yemen-crew", "Closing on the coast.", "Yemeni coastal crew", False),
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


HEROES = {"Falcon One", "Wadi Ghost"}


def synthesize(line: VoiceLine, ffmpeg: str, temporary: Path, synth: Synthesizer,
               output: Path = OUTPUT) -> dict[str, object]:
    raw = temporary / (Path(line.filename).stem + ".raw.wav")
    wav = output / line.filename
    # Tempo 0.94 stands in for the old edge-tts rate of -6%.
    record = synth.render(line.text, line.language, line.voice, raw, rate=0.94, expressive=line.role in HEROES)

    filters = (
        "highpass=f=220,lowpass=f=5400,acompressor=threshold=-20dB:ratio=2.7:attack=6:release=90,"
        "loudnorm=I=-18:TP=-2:LRA=7"
        if line.radio
        else "highpass=f=120,lowpass=f=7200,acompressor=threshold=-22dB:ratio=2.2:attack=5:release=80,loudnorm=I=-19:TP=-2:LRA=8"
    )
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-af", filters,
         "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
        check=True,
    )
    radio_finish(wav, line.radio)
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
        }


def run(selected: set[str] | None = None, ra2: bool = False, output: Path | None = None,
        provenance: Path | None = None) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to master the generated voices")
    default_output, default_provenance, source = (RA2_OUTPUT, RA2_PROVENANCE, RA2_LINES) if ra2 else (OUTPUT, PROVENANCE, LINES)
    output = output or default_output
    provenance = provenance or default_provenance
    output.mkdir(parents=True, exist_ok=True)
    provenance.parent.mkdir(parents=True, exist_ok=True)
    lines = [line for line in source if not selected or line.filename in selected]
    synth = Synthesizer()
    try:
        with tempfile.TemporaryDirectory(prefix="openra-red-sea-voice-") as directory:
            records = []
            for line in lines:
                print(f"Synthesizing {line.filename} ({line.voice})")
                records.append(synthesize(line, ffmpeg, Path(directory), synth, output))
    finally:
        synth.close()
    provenance.write_text(json.dumps({"generator": "voice_engines.py + ffmpeg", "engines": ENGINES, "qa": QA,
                                      "lines": records}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*")
    parser.add_argument("--ra2", action="store_true", help="Generate the RA2 vehicle/naval crew lines into the RA2 overlay")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--provenance", type=Path)
    args = parser.parse_args()
    run(set(args.filenames) or None, args.ra2, args.output and args.output.resolve(),
        args.provenance and args.provenance.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
