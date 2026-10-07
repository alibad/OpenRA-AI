"""Generate the Israel (Hebrew/English) and Hezbollah (Lebanese Arabic/English) unit voices for the RA2 mod.

Speech comes from local, redistributable engines (voice_engines.py): Kokoro-82M for English and Chatterbox
Multilingual for Hebrew and Arabic, cloned from a synthetic native reference that a Kokoro voicepack first spoke
in English; no real person is imitated. The Lebanese lines are written in Lebanese Arabic and cloned from a
Lebanese-dialect reference sentence (voice_engines.NATIVE_REFERENCE_TEXT["ar-LB"]).

Every line is a neutral unit acknowledgement or report, like the other factions' lines: no slogans, no religious
or political phrases, no real people or operations.

    python scripts/generate-levant-voices.py --output <RTSAI-Mod>/mods/rtsai/modern-factions/audio [files...]
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
OUTPUT = ROOT.parent / "RTSAI-Mod" / "mods" / "rtsai" / "modern-factions" / "audio"
PROVENANCE = ROOT / "assets" / "levant" / "voice-provenance.json"


@dataclass(frozen=True)
class Line:
    filename: str
    language: str
    voice: str  # speaker id from voice_engines.SPEAKERS
    text: str
    role: str
    translation: str = ""  # English meaning of a non-English line
    spoken: str = ""  # what the engine reads when it differs from the script (pointed Hebrew)


def bilingual(prefix: str, language: str, suffix: str, role: str, speaker: str,
              phrases: dict[str, tuple[str, str]]) -> list[Line]:
    lines: list[Line] = []
    for action, (native, english) in phrases.items():
        lines.append(Line(f"{prefix}-{action}-{suffix}.wav", language, speaker, native, role, english,
                          POINTED.get(native, "")))
        lines.append(Line(f"{prefix}-{action}-en.wav", "en-US", speaker, english, role))
    return lines


# Chatterbox's Hebrew front end expects pointed (niqqud) text; it would add the points with the optional dicta_onnx
# diacritizer, which is not installed. The points below are written by hand; the unpointed script stays the text
# that is shown, checked by speech recognition and reviewed.
POINTED = {
    "הצוות מוכן.": "הַצֶּוֶות מוּכָן.",
    "זזים עכשיו.": "זָזִים עַכְשָׁיו.",
    "פותחים באש.": "פּוֹתְחִים בָּאֵשׁ.",
    "קיבלתי, מבצעים.": "קִיבַּלְתִּי, מְבַצְּעִים.",
    "תצפית בעמדה.": "תַּצְפִּית בָּעֶמְדָּה.",
    "עובר לנקודת תצפית.": "עוֹבֵר לִנְקוּדַּת תַּצְפִּית.",
    "המטרה מסומנת.": "הַמַּטָּרָה מְסוּמֶּנֶת.",
    "מעביר נקודות ציון.": "מַעֲבִיר נְקוּדּוֹת צִיּוּן.",
    "הסייר מוכן.": "הַסַּיָּר מוּכָן.",
    "נע בשקט.": "נָע בְּשֶׁקֶט.",
    "יש קשר עין עם המטרה.": "יֵשׁ קֶשֶׁר עַיִן עִם הַמַּטָּרָה.",
    "הדרך פנויה.": "הַדֶּרֶךְ פְּנוּיָה.",
    "הצוות מוכן לתנועה.": "הַצֶּוֶות מוּכָן לִתְנוּעָה.",
    "נעים לעמדה.": "נָעִים לָעֶמְדָּה.",
    "מטרה בטווח, יורים.": "מַטָּרָה בַּטְּוָוח, יוֹרִים.",
    "קיבלתי, מבצע.": "קִיבַּלְתִּי, מְבַצֵּעַ.",
    "צוות האוויר מוכן.": "צֶוֶות הָאֲוִויר מוּכָן.",
    "בדרך לנקודה.": "בַּדֶּרֶךְ לַנְּקוּדָּה.",
    "ננעלים על המטרה.": "נִנְעָלִים עַל הַמַּטָּרָה.",
    "קיבלתי, בקרה.": "קִיבַּלְתִּי, בַּקָּרָה.",
    "הספינה מוכנה.": "הַסְּפִינָה מוּכָנָה.",
    "משנים כיוון.": "מְשַׁנִּים כִּיוּוּן.",
    "מטרה ימית ננעלה.": "מַטָּרָה יַמִּית נִנְעֲלָה.",
    "הפקודה התקבלה.": "הַפְּקוּדָּה הִתְקַבְּלָה.",
}


def hebrew(prefix, role, speaker, phrases):
    return bilingual(prefix, "he-IL", "he", role, speaker, phrases)


def lebanese(prefix, role, speaker, phrases):
    return bilingual(prefix, "ar-LB", "ar", role, speaker, phrases)


ISRAEL = tuple(
    hebrew("il-inf", "generic infantry", "israel-infantry", {
        "select": ("הצוות מוכן.", "Rifle team ready."),
        "move": ("זזים עכשיו.", "Moving now."),
        "attack": ("פותחים באש.", "Opening fire."),
        "action": ("קיבלתי, מבצעים.", "Copy, on it."),
    })
    + hebrew("il-observer", "forward observer", "israel-infantry", {
        "select": ("תצפית בעמדה.", "Observer in position."),
        "move": ("עובר לנקודת תצפית.", "Moving to a new vantage point."),
        "attack": ("המטרה מסומנת.", "Target marked."),
        "action": ("מעביר נקודות ציון.", "Sending coordinates."),
    })
    + hebrew("il-recon", "fictional recon specialist", "israel-infantry", {
        "select": ("הסייר מוכן.", "Recon ready."),
        "move": ("נע בשקט.", "Moving quietly."),
        "attack": ("יש קשר עין עם המטרה.", "Eyes on target."),
        "action": ("הדרך פנויה.", "Path is clear."),
    })
    + hebrew("il-veh", "generic vehicle crew", "israel-crew", {
        "select": ("הצוות מוכן לתנועה.", "Crew ready to roll."),
        "move": ("נעים לעמדה.", "Moving to position."),
        "attack": ("מטרה בטווח, יורים.", "Target in range. Firing."),
        "action": ("קיבלתי, מבצע.", "Copy that."),
    })
    + hebrew("il-air", "generic aircrew", "israel-crew", {
        "select": ("צוות האוויר מוכן.", "Aircrew ready."),
        "move": ("בדרך לנקודה.", "En route to the waypoint."),
        "attack": ("ננעלים על המטרה.", "Locking on."),
        "action": ("קיבלתי, בקרה.", "Copy, control."),
    })
    + hebrew("il-naval", "generic naval crew", "israel-crew", {
        "select": ("הספינה מוכנה.", "Ship ready."),
        "move": ("משנים כיוון.", "Changing heading."),
        "attack": ("מטרה ימית ננעלה.", "Surface target locked."),
        "action": ("הפקודה התקבלה.", "Order received."),
    })
)

HEZBOLLAH = tuple(
    lebanese("hz-inf", "generic infantry", "hezbollah-infantry", {
        "select": ("نحنا جاهزين.", "We're ready."),
        "move": ("ماشيين هلق.", "Moving now."),
        "attack": ("عم نشتبك.", "Engaging."),
        "action": ("تمام، وصلت.", "Copy that."),
    })
    + lebanese("hz-spotter", "field spotter", "hezbollah-infantry", {
        "select": ("المراقب جاهز.", "Spotter ready."),
        "move": ("رايح عالتلة.", "Heading for high ground."),
        "attack": ("الهدف محدد.", "Target marked."),
        "action": ("عم ببعت الإحداثيات.", "Sending coordinates."),
    })
    + lebanese("hz-scout", "fictional scout", "hezbollah-infantry", {
        "select": ("جاهز، شو المهمة؟", "Ready. What's the task?"),
        "move": ("ماشي بهدوء.", "Moving quietly."),
        "attack": ("شايف الهدف.", "Eyes on target."),
        "action": ("الطريق مفتوح.", "Path is clear."),
    })
    + lebanese("hz-fpv", "FPV drone team", "hezbollah-infantry", {
        "select": ("فريق المسيرات جاهز.", "Drone team ready."),
        "move": ("رايحين عالموقع الجديد.", "Moving to a new position."),
        "attack": ("طلعنا المسيرات.", "Drones away."),
        "action": ("الإشارة منيحة.", "Signal's good."),
    })
    + lebanese("hz-veh", "generic vehicle crew", "hezbollah-crew", {
        "select": ("الطاقم جاهز.", "Crew ready."),
        "move": ("منتحرك هلق.", "Moving out."),
        "attack": ("الهدف بالمرمى، عم نضرب.", "Target in range. Firing."),
        "action": ("تمام، منفذين.", "Copy, executing."),
    })
    + lebanese("hz-drone", "generic drone operator", "hezbollah-crew", {
        "select": ("المسيرة جاهزة.", "Drone ready."),
        "move": ("المسيرة رايحة عالنقطة.", "Drone heading to the waypoint."),
        "attack": ("الهدف عالشاشة.", "Target on screen."),
        "action": ("الصورة واضحة.", "Picture is clear."),
    })
    + lebanese("hz-naval", "generic naval crew", "hezbollah-crew", {
        "select": ("الزورق جاهز.", "Boat ready."),
        "move": ("رايحين عالساحل.", "Heading along the coast."),
        "attack": ("الهدف قدامنا.", "Target dead ahead."),
        "action": ("وصلت، منغير الاتجاه.", "Copy, changing course."),
    })
)

LINES = ISRAEL + HEZBOLLAH

# Faction -> (ffmpeg chain, squelch tone in Hz, noise amplitude, character).
CHAINS = {
    "il": ("highpass=f=170,lowpass=f=6600,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,"
           "loudnorm=I=-18:TP=-2:LRA=7", 1180, 52, "clean tactical radio"),
    "hz": ("highpass=f=260,lowpass=f=4800,acompressor=threshold=-22dB:ratio=3.5:attack=4:release=70,"
           "loudnorm=I=-18:TP=-2:LRA=7", 900, 90, "handheld field radio"),
}


def radio_finish(path: Path, tone: int, noise: int) -> None:
    """Squelch tone, a low noise floor and fades, deterministic per file."""
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError(f"unexpected WAV layout for {path.name}")
        frames = source.readframes(source.getnframes())
    samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
    rng = random.Random(f"levant-radio:{path.name}")
    beep = [round(1100 * math.sin(math.tau * tone * i / rate)) for i in range(round(rate * .04))]
    finished = beep + [0] * round(rate * .025)
    for index, sample in enumerate(samples):
        fade = min(1.0, index / max(1, round(rate * .015)), (len(samples) - index) / max(1, round(rate * .025)))
        finished.append(round((sample + rng.randint(-noise, noise)) * max(0.0, fade)))
    peak = max(1, max(abs(value) for value in finished))
    gain = min(1.0, 26000 / peak)
    encoded = struct.pack("<" + "h" * len(finished),
                          *(max(-32768, min(32767, round(value * gain))) for value in finished))
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(encoded)


def synthesize(line: Line, ffmpeg: str, temporary: Path, synth: Synthesizer,
               output: Path = OUTPUT) -> dict[str, object]:
    filters, tone, noise, character = CHAINS[line.filename.split("-")[0]]
    raw = temporary / f"{Path(line.filename).stem}.raw.wav"
    destination = output / line.filename
    record = synth.render(line.spoken or line.text, line.language, line.voice, raw,
                          expressive=line.role.startswith("fictional"), script=line.text)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-af", filters,
                    "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(destination)], check=True)
    radio_finish(destination, tone, noise)
    with wave.open(str(destination), "rb") as check:
        return {
            **{key: value for key, value in asdict(line).items() if value != ""},
            **record,
            "processing": f"ffmpeg {filters}; {character}: squelch tone, noise floor and fades",
            "sample_rate": check.getframerate(),
            "channels": check.getnchannels(),
            "sample_width_bits": check.getsampwidth() * 8,
            "duration_seconds": round(check.getnframes() / check.getframerate(), 3),
            "synthetic_voice_disclosed": True,
            "real_person_imitation": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--provenance", type=Path, default=PROVENANCE)
    args = parser.parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required")
    selected = set(args.filenames)
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    synth = Synthesizer()
    try:
        with tempfile.TemporaryDirectory(prefix="levant-voices-") as directory:
            for line in LINES:
                if selected and line.filename not in selected:
                    continue
                print(line.filename, flush=True)
                records.append(synthesize(line, ffmpeg, Path(directory), synth, args.output.resolve()))
    finally:
        synth.close()
    args.provenance.parent.mkdir(parents=True, exist_ok=True)
    args.provenance.write_text(json.dumps({"generator": "voice_engines.py + ffmpeg", "engines": ENGINES, "qa": QA,
                                           "lines": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
