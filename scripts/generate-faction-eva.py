"""Generate a faction announcer (EVA) for each modern RA2 faction.

Every Speech notification clip of the RA2 mod gets one line per faction, so a
modern faction never falls back to a missing file. Each announcer is an English
Kokoro-82M voicepack (Apache-2.0) with its own mastering chain; English keeps
base alerts intelligible for every player. The wording is original, not a
transcript of the commercial Red Alert 2 announcer.

The output tree matches RTSAI-Mod's Speech prefixes,
`ra2|modern-factions/audio/eva/<faction>/<clip>.wav`: IMA ADPCM, 22.05 kHz mono,
the format RA2's own announcer uses and OpenRA's WAV loader reads.

    python scripts/generate-faction-eva.py --mod ../RTSAI-Mod [--factions china,iran] [--clips 048,062]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import soundfile as sf

from voice_engines import ENGINES, QA, Synthesizer

ROOT = Path(__file__).resolve().parents[1]

# Clip id (the RA2 notification number) -> announcer line.
EVA_TEXT = {
    "001": "Nuclear silo detected.",
    "002": "Nuclear missile launched.",
    "003": "Nuclear missile ready.",
    "004": "Iron Curtain detected.",
    "005": "Iron Curtain activated.",
    "006": "Iron Curtain ready.",
    "007": "Chronosphere detected.",
    "008": "Chronosphere activated.",
    "009": "Chronosphere ready.",
    "010": "Weather control device detected.",
    "011": "Lightning storm created.",
    "012": "Lightning storm ready.",
    "013": "Mission accomplished.",
    "014": "Mission failed.",
    "015": "Battle control terminated.",
    "016": "Establishing battlefield control. Stand by.",
    "017": "Primary objective achieved.",
    "018": "Secondary objective achieved.",
    "019": "Tertiary objective achieved.",
    "020": "Critical unit lost.",
    "021": "Critical structure lost.",
    "022": "You are victorious.",
    "023": "You have been defeated.",
    "024": "You have resigned.",
    "025": "A player has resigned.",
    "026": "A player has been defeated.",
    "027": "Twenty minutes remaining.",
    "028": "Ten minutes remaining.",
    "029": "Five minutes remaining.",
    "030": "Four minutes remaining.",
    "031": "Three minutes remaining.",
    "032": "Two minutes remaining.",
    "033": "One minute remaining.",
    "035": "Timer started.",
    "036": "Timer stopped.",
    "037": "Ore miner under attack.",
    "038": "Reinforcements have arrived.",
    "039": "New terrain discovered.",
    "040": "Incoming transmission.",
    "041": "Beacon detected.",
    "042": "Beacon placed.",
    "043": "Alliance formed.",
    "044": "Alliance broken.",
    "045": "Our ally is under attack.",
    "046": "Bridge repaired.",
    "047": "Unable to comply. Building in progress.",
    "048": "Construction complete.",
    "049": "New construction options.",
    "050": "Insufficient funds.",
    "051": "Canceled.",
    "052": "Building.",
    "053": "Low power.",
    "054": "Our base is under attack.",
    "055": "Primary building selected.",
    "056": "On hold.",
    "057": "Repairing.",
    "058": "Structure sold.",
    "059": "Base defenses offline.",
    "060": "Structure online.",
    "061": "Structure offline.",
    "062": "Unit ready.",
    "063": "Cannot deploy here.",
    "064": "Unit lost.",
    "065": "Select target.",
    "066": "Training.",
    "067": "Armor upgraded.",
    "068": "Firepower upgraded.",
    "069": "Speed upgraded.",
    "070": "Unit repaired.",
    "071": "Unit sold.",
    "072": "Building captured.",
    "073": "Building infiltrated.",
    "074": "New technology acquired.",
    "075": "Enemy base powered down.",
    "076": "Unit firepower upgraded.",
    "077": "Unit armor upgraded.",
    "078": "Unit speed upgraded.",
    "079": "Unit promoted.",
    "080": "Unit upgraded.",
    "081": "Firepower technology stolen.",
    "082": "Armor technology stolen.",
    "083": "New mission objective received.",
    "084": "Upgrade in progress.",
    "085": "Upgrade complete.",
    "086": "Ore miner offline.",
    "087": "Enemy power restored.",
    "088": "Building infiltrated. Technology stolen.",
    "089": "Building infiltrated. Radar sabotaged.",
    "090": "Building infiltrated. Cash stolen.",
    "091": "Building infiltrated. Power sabotaged.",
    "092": "Technology stolen.",
    "093": "Radar sabotaged.",
    "094": "Credits stolen.",
    "095": "Power sabotaged.",
    "096": "Enemy air armada detected.",
    "097": "Enemy fleet detected.",
    "098": "Enemy armor battalion detected.",
    "099": "Enemy infantry battalion detected.",
    "100": "New rally point established.",
    "101": "Alliance requested.",
    "102": "Requesting alliance.",
    "103": "Enemy alliance formed.",
    "104": "New objective received.",
    "105": "Tech building captured.",
    "106": "Tech building lost.",
    "107": "Structure garrisoned.",
    "108": "Structure abandoned.",
    "109": "Chrono miner offline.",
    "120": "Battle control online.",
    "121": "Reinforcements ready.",
    "122": "Weather control device offline.",
}

# Kokoro reads some game terms better with an explicit pronunciation (misaki markdown).
PRONUNCIATION = {
    "Chronosphere": "[Chronosphere](/kɹˈOnəsfɪɹ/)",
}

# Faction -> (speaker id in voice_engines.SPEAKERS, character, ffmpeg mastering chain).
LOUDNESS = "loudnorm=I=-16:TP=-1.5:LRA=6"
FACTIONS = {
    "china": ("china-eva", "crisp networked command voice",
              "highpass=f=120,lowpass=f=9000,acompressor=threshold=-20dB:ratio=3:attack=4:release=60,"
              "aecho=0.8:0.5:12:0.15," + LOUDNESS),
    "iran": ("iran-eva", "narrow-band command radio",
             "highpass=f=200,lowpass=f=6500,acompressor=threshold=-22dB:ratio=3.5:attack=5:release=80," + LOUDNESS),
    "turkey": ("turkey-eva", "clean broadcast command voice",
               "highpass=f=140,lowpass=f=8000,acompressor=threshold=-20dB:ratio=2.8:attack=5:release=70," + LOUDNESS),
    "saudi": ("saudi-eva", "operations-room voice with a short room tail",
              "highpass=f=110,lowpass=f=9500,acompressor=threshold=-20dB:ratio=2.5:attack=5:release=70,"
              "aecho=0.8:0.4:35:0.12," + LOUDNESS),
    "yemen": ("yemen-eva", "lo-fi field radio",
              "highpass=f=300,lowpass=f=4200,acompressor=threshold=-24dB:ratio=4:attack=4:release=60," + LOUDNESS),
}
SAMPLE_RATE = 22050


def mod_speech_clips(mod: Path) -> list[str]:
    """Every clip id in the Speech section of the mod's notifications.yaml."""
    text = (mod / "mods/rtsai/audio/notifications.yaml").read_text(encoding="utf-8")
    speech = text.split("\nSounds:")[0]
    section = speech.split("\tNotifications:", 1)[1]
    clips = {value for value in re.findall(r"^\t\t\w+:[ \t]*([^\s#]*)", section, flags=re.M) if value}
    return sorted(clips)


def spoken(text: str) -> str:
    for word, markup in PRONUNCIATION.items():
        text = text.replace(word, markup)
    return text


def render(faction: str, clip: str, synth: Synthesizer, ffmpeg: str, output: Path, temporary: Path) -> dict[str, object]:
    speaker, character, filters = FACTIONS[faction]
    text = EVA_TEXT[clip]
    raw = temporary / f"{faction}-{clip}.raw.wav"
    record = synth.render(spoken(text), "en-US", speaker, raw, script=text)
    destination = output / faction / f"{clip}.wav"
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-af", filters,
                    "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "adpcm_ima_wav", str(destination)], check=True)
    duration = sf.info(str(destination)).duration
    return {
        "filename": f"eva/{faction}/{clip}.wav",
        "faction": faction,
        "clip": clip,
        "role": f"{faction} announcer (EVA): {character}",
        **record,
        "processing": "ffmpeg " + filters + f"; IMA ADPCM {SAMPLE_RATE} Hz mono",
        "sample_rate": SAMPLE_RATE,
        "channels": 1,
        "codec": "IMA ADPCM WAV",
        "duration_seconds": round(duration, 3),
        "synthetic_voice_disclosed": True,
        "real_person_imitation": False,
    }


def generate(output: Path, provenance: Path | None, factions: list[str], clips: list[str],
             synth: Synthesizer | None = None) -> list[dict[str, object]]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required")
    missing = [clip for clip in clips if clip not in EVA_TEXT]
    if missing:
        raise SystemExit(f"No announcer text for Speech clips: {missing}")
    owned = synth is None
    synth = synth or Synthesizer()
    records = []
    try:
        with tempfile.TemporaryDirectory(prefix="rtsai-eva-") as temporary:
            for faction in factions:
                for clip in clips:
                    print(f"EVA {faction} {clip}: {EVA_TEXT[clip]}")
                    records.append(render(faction, clip, synth, ffmpeg, output, Path(temporary)))
    finally:
        if owned:
            synth.close()
    if provenance:
        provenance.parent.mkdir(parents=True, exist_ok=True)
        provenance.write_text(json.dumps({"generator": "generate-faction-eva.py (voice_engines.py + ffmpeg)",
                                          "engines": {"kokoro": ENGINES["kokoro"]}, "qa": QA, "lines": records},
                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", type=Path, default=ROOT.parent / "RTSAI-Mod", help="RTSAI-Mod checkout")
    parser.add_argument("--factions", default=",".join(FACTIONS))
    parser.add_argument("--clips", help="comma-separated clip ids (default: every Speech clip in the mod)")
    parser.add_argument("--output", type=Path, help="default: <mod>/mods/rtsai/modern-factions/audio/eva")
    parser.add_argument("--provenance", type=Path)
    args = parser.parse_args()
    clips = args.clips.split(",") if args.clips else mod_speech_clips(args.mod)
    output = args.output or args.mod / "mods/rtsai/modern-factions/audio/eva"
    generate(output.resolve(), args.provenance, [f for f in args.factions.split(",") if f], clips)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
