"""Regenerate every voice line and announcer clip that RTSAI-Mod ships.

Finds each `ra2|modern-factions/audio/<name>` reference in the mod's rules,
renders the voice lines through their faction generator (same text, same
processing chain, new licensed engines), renders the faction announcers, and
writes `mods/rtsai/modern-factions/audio/PROVENANCE.json`. References that no
voice generator owns must be listed in SFX (procedural sound effects); each is
checked with speech recognition so no synthetic speech can slip in unrecorded.

    python scripts/generate-rtsai-mod-audio.py --mod ../RTSAI-Mod
    python scripts/generate-rtsai-mod-audio.py --mod ../RTSAI-Mod --only rcn-air-select-zh.wav --skip-eva
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from voice_engines import ENGINES, QA, SPEAKERS, Synthesizer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GENERATORS = ("china", "iran", "turkey", "red-sea", "air-warfare")
# Shipped files that are procedural sound effects, with the script or source that made them.
SFX = {
    "china-network-deploy": "OpenRA-AI scripts/generate-china-sfx.py (procedural)",
    "china-network-fold": "OpenRA-AI scripts/generate-china-sfx.py (procedural)",
    "china-role-aa": "OpenRA-AI scripts/generate-china-sfx.py (procedural)",
    "china-role-at": "OpenRA-AI scripts/generate-china-sfx.py (procedural)",
    **{f"redsea-{name}": "OpenRA-AI scripts/generate-red-sea-sfx.py (procedural)" for name in (
        "ah64-cannon", "ah64-rocket", "atgm-launch", "drone-impact", "drone-loiter", "drone-strike", "f15-missile",
        "guard-rifle", "interceptor", "m1-fire", "mobile-launch", "mountain-rifle", "remote-charge", "rpg-launch",
        "suppressed")},
    **{f"naval-{name}": "alibad/OpenRA fork mods/ra/bits/naval (1d76c546f1, 'Add Saudi and Yemen naval systems')"
       for name in ("ciws-burst", "missile-launch", "naval-alarm", "radar-sweep")},
}
REJECTED = [
    {"candidate": "edge-tts (Microsoft Edge Read Aloud)", "reason": "Unofficial client of a Microsoft service; no "
     "license grants redistribution of its output. Removed from the mod."},
    {"candidate": "Piper fa_IR voices (amir, ganji, ganji_adabi, reza_ibrahim)", "reason": "Each is fine-tuned from "
     "the en_US lessac voice, whose Blizzard 2013 dataset license is research-only and forbids commercial use "
     "(https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html)."},
    {"candidate": "Piper fa_IR gyro", "reason": "Model card gives no dataset license ('See URL'); the URL states none."},
    {"candidate": "Thomcles/Chatterbox-TTS-Persian-Farsi", "reason": "CC BY-NC 4.0 (non-commercial)."},
    {"candidate": "mazrba/Chatterbox-TTS-Persian-gguf", "reason": "Labelled MIT, but it is a quantization of the "
     "CC BY-NC 4.0 Thomcles model, so the label cannot be relied on."},
    {"candidate": "Kamtera/persian-tts-*-vits", "reason": "OpenRAIL model on a Kaggle dataset with no stated license."},
    {"candidate": "facebook/mms-tts-*", "reason": "CC BY-NC 4.0 (non-commercial)."},
    {"candidate": "Coqui XTTS-v2", "reason": "Coqui Public Model License (non-commercial)."},
    {"candidate": "Kokoro zh voicepacks (zm_*/zf_*)", "reason": "License-compatible (Apache-2.0) but graded D by "
     "the model card; Chatterbox Multilingual (MIT) speaks Mandarin instead."},
]


def load_script(filename: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


def load_generator(name: str):
    return load_script(f"generate-{name}-voices.py")


def load_eva():
    return load_script("generate-faction-eva.py")


def voice_lines():
    """filename -> (generator name, module, line) for every line a generator can make."""
    owners = {}
    for name in GENERATORS:
        module = load_generator(name)
        lines = list(module.LINES) + list(getattr(module, "RA2_LINES", ()))
        for line in lines:
            filename = line["file"] if isinstance(line, dict) else line.filename
            owners[filename] = (name, module, line)
    return owners


def referenced_audio(mod: Path) -> set[str]:
    names = set()
    for path in (mod / "mods/rtsai").rglob("*.yaml"):
        names.update(re.findall(r"ra2\|modern-factions/audio/([\w.-]+)(?![\w.-]|/)", path.read_text(encoding="utf-8")))
    return {Path(name).stem for name in names}


def render_voice(name: str, module, line, synth: Synthesizer, ffmpeg: str, output: Path, temporary: Path):
    if isinstance(line, dict):  # air-warfare lines are dicts
        record = module.synthesize(line, output / line["file"], ffmpeg, temporary, synth)
        record["filename"] = record.pop("file")
        with sf.SoundFile(output / record["filename"]) as check:
            record.update(sample_rate=check.samplerate, channels=check.channels, sample_width_bits=16,
                          duration_seconds=round(check.frames / check.samplerate, 3))
    else:
        record = module.synthesize(line, ffmpeg, temporary, synth, output)
    record["generator"] = f"OpenRA-AI scripts/generate-{name}-voices.py"
    return record


def check_sfx(name: str, path: Path, synth: Synthesizer) -> dict[str, object]:
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    speech = synth.detect_speech(data.mean(axis=1), rate)
    if speech:
        raise SystemExit(f"{name}.wav is listed as a sound effect but contains speech: {speech!r}")
    return {"filename": f"{name}.wav", "source": SFX[name],
            "speech_check": "no speech detected (Whisper large-v3 with voice-activity filter)"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mod", type=Path, default=ROOT.parent / "RTSAI-Mod")
    parser.add_argument("--only", help="comma-separated voice filenames to regenerate (merged into PROVENANCE.json)")
    parser.add_argument("--skip-eva", action="store_true")
    parser.add_argument("--eva-only", action="store_true")
    parser.add_argument("--eva-clips", help="comma-separated EVA clip ids (default: all)")
    args = parser.parse_args()

    mod = args.mod.resolve()
    audio = mod / "mods/rtsai/modern-factions/audio"
    provenance_path = audio / "PROVENANCE.json"
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required")

    owners = voice_lines()
    referenced = referenced_audio(mod)
    voices = sorted(name for name in referenced if f"{name}.wav" in owners)
    unknown = sorted(name for name in referenced if f"{name}.wav" not in owners and name not in SFX)
    if unknown:
        raise SystemExit(f"Shipped audio with no voice generator and no SFX entry: {unknown}")
    selected = set(args.only.split(",")) if args.only else None

    previous = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.exists() else {}
    records = {record["filename"]: record for record in previous.get("voice_lines", [])}
    eva_records = {record["filename"]: record for record in previous.get("announcers", [])}

    synth = Synthesizer()
    try:
        with tempfile.TemporaryDirectory(prefix="rtsai-mod-audio-") as temporary:
            if not args.eva_only:
                for name in voices:
                    filename = f"{name}.wav"
                    if selected and filename not in selected:
                        continue
                    generator, module, line = owners[filename]
                    print(f"[voice] {filename}", flush=True)
                    records[filename] = render_voice(generator, module, line, synth, ffmpeg, audio, Path(temporary))
            if not args.skip_eva and not selected:
                eva = load_eva()
                clips = args.eva_clips.split(",") if args.eva_clips else eva.mod_speech_clips(mod)
                for record in eva.generate(audio / "eva", None, list(eva.FACTIONS), clips, synth):
                    eva_records[record["filename"]] = record
            sfx = [check_sfx(name, audio / f"{name}.wav", synth) for name in sorted(n for n in referenced if n in SFX)]
    finally:
        synth.close()

    stale = sorted(set(records) - {f"{name}.wav" for name in voices})
    for filename in stale:
        del records[filename]
    payload = {
        "schema": "rtsai-audio-provenance/1",
        "updated": dt.date.today().isoformat(),
        "policy": ("Every shipped voice and announcer line is generated locally by an engine whose code, weights and "
                   "voice allow redistribution of the output in a GPL game, commercial use included. No real person's "
                   "voice is cloned: non-English speakers are cloned from English clips spoken by Kokoro voicepacks."),
        "reproduce": "OpenRA-AI: python scripts/generate-rtsai-mod-audio.py --mod <RTSAI-Mod>",
        "engines": ENGINES,
        "speakers": {key: {"kokoro_voicepacks": list(value.voicepacks), "accent": value.accent}
                     for key, value in SPEAKERS.items()},
        "qa": QA,
        "rejected": REJECTED,
        "voice_lines": [records[key] for key in sorted(records)],
        "announcers": [eva_records[key] for key in sorted(eva_records)],
        "sound_effects": sfx,
    }
    provenance_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    flagged = [r["filename"] for r in list(records.values()) + list(eva_records.values())
               if r.get("qa") and r["qa"]["cer"] > 0.2]
    print(f"{len(records)} voice lines, {len(eva_records)} announcer clips, {len(sfx)} SFX checked; "
          f"{len(flagged)} above 20% CER: {flagged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
