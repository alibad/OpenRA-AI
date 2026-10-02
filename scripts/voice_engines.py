"""Local, redistributable text-to-speech for the RTS AI faction voices.

This replaces edge-tts (an unofficial client for Microsoft Edge's Read Aloud
service, whose output carries no redistribution grant). Every engine below runs
locally, and its code, weights and voice allow shipping the generated audio in a
GPL game, commercial use included. The license evidence is in ENGINES and in
RTSAI-Mod/docs/audio-provenance.md.

Speaker identity never comes from a real person:
  * English is spoken directly by a Kokoro-82M voicepack (or the mean of two).
  * The same voicepack speaks a ~9 s English reference sentence. For Arabic,
    Turkish and Mandarin, Chatterbox Multilingual clones that clip with
    cfg_weight 0 (the model card's setting against carrying the reference
    accent across) to speak a native reference sentence; the lines are then
    cloned from that native clip at the default cfg_weight 0.5, so reference
    and target language match, as the model card recommends.
  * Persian uses MOSS-TTS-Nano with its Common Voice (CC0) Persian fine-tune,
    cloned from the English reference (the fine-tune's documented use).

Every take that can vary is sampled with several seeds. Whisper transcribes each
take; audio outside the recognized words (trailing breaths or babble) is cut,
and the take with the lowest character error rate against the script is kept.
The transcript and error rate go into the provenance record.

Environment, plus ffmpeg on PATH. Models download from Hugging Face at the
pinned revisions.
  * Main Python 3.12 venv (on an RTX 50xx, install chatterbox-tts with --no-deps
    on top of a CUDA 12.8 torch, because it pins torch 2.6):
      pip install kokoro==0.9.4 "misaki[en]==0.9.4" chatterbox-tts==0.1.7 \\
          transformers==5.2.0 faster-whisper==1.2.1 soundfile huggingface_hub
  * Persian worker (RTSAI_MOSS_PYTHON, default: the main interpreter), because the
    MOSS remote code speaks gibberish under transformers 5.x:
      pip install torch transformers==4.57.1 sentencepiece soundfile huggingface_hub
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

GENERATOR_VERSION = "rtsai-voices-1"

ENGINES: dict[str, dict[str, object]] = {
    "kokoro": {
        "engine": "Kokoro-82M v1.0 (StyleTTS 2 + ISTFTNet)",
        "package": "kokoro 0.9.4 + misaki 0.9.4 (Apache-2.0)",
        "model": "hexgrad/Kokoro-82M",
        "revision": "f3ff3571791e39611d31c381e3a41a3af07b4987",
        "checkpoint": "kokoro-v1_0.pth",
        "license": "Apache-2.0",
        "license_evidence": "https://huggingface.co/hexgrad/Kokoro-82M (model card: license apache-2.0; "
                            "voicepacks ship in the same repository under the same license; the card lists its "
                            "training data as permissive/non-copyrighted audio, including synthetic audio from "
                            "closed TTS providers)",
    },
    "chatterbox": {
        "engine": "Chatterbox Multilingual V2 (0.5B)",
        "package": "chatterbox-tts 0.1.7 (MIT)",
        "model": "ResembleAI/chatterbox",
        "revision": "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18",
        "checkpoint": "t3_mtl23ls_v2.safetensors + s3gen.pt + ve.pt",
        "license": "MIT",
        "license_evidence": "https://huggingface.co/ResembleAI/chatterbox (model card: license mit; languages "
                            "include ar, tr, zh). Output carries Resemble's inaudible Perth watermark.",
    },
    "moss-fa": {
        "engine": "MOSS-TTS-Nano (0.1B) with the Persian fine-tune",
        "package": "Hugging Face remote code at the pinned revision (Apache-2.0)",
        "model": "nimaaaAI/MOSS-TTS-Nano-Persian",
        "revision": "dcfd7f2baab4bb69434895f51eae6a0c0059c59f",
        "base_model": "OpenMOSS-Team/MOSS-TTS-Nano@44502f80dbf9743528fa921cc544d662c685ebec",
        "codec": "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano@6aa02b01e445cc585582cf0ba480bc3ea6c8dd68",
        "checkpoint": "pytorch_model.bin (loaded with torch.load(weights_only=True))",
        "license": "Apache-2.0",
        "license_evidence": "https://huggingface.co/nimaaaAI/MOSS-TTS-Nano-Persian/blob/main/LICENSE (Apache-2.0; "
                            "fine-tuned only on Mozilla Common Voice Persian v13, CC0); base and codec model "
                            "cards: license apache-2.0; https://github.com/OpenMOSS/MOSS-TTS-Nano LICENSE Apache-2.0",
    },
}
QA = {
    "asr": "faster-whisper 1.2.1, Systran/faster-whisper-large-v3@edaa852ec7e145841d8ffdb056a99866b5f0a478 "
           "(int8_float16, word timestamps)",
    "metric": "character error rate against the script after punctuation/diacritic normalization",
}

LANGUAGE_ENGINE = {"en": "kokoro", "zh": "chatterbox", "ar": "chatterbox", "tr": "chatterbox", "fa": "moss-fa"}
REFERENCE_TEXT = ("Command, this is the forward element. We hold the ridge line and the road is clear. "
                  "Awaiting your orders, ready to move on your signal.")
# The same field-radio sentence in each Chatterbox language: the native reference clip.
NATIVE_REFERENCE_TEXT = {
    "ar": "القيادة، هنا الوحدة الأمامية. نحن نسيطر على خط التلال والطريق آمن. ننتظر أوامركم وجاهزون للتحرك.",
    "tr": "Komuta, burası ileri birlik. Sırt hattını tutuyoruz ve yol açık. Emirlerinizi bekliyoruz, "
          "işaretinizle harekete hazırız.",
    "zh": "指挥部，这里是前沿分队。我们控制着山脊线，道路畅通。等待你的命令，随时准备行动。",
}
CHATTERBOX_CFG = 0.5
REFERENCE_SEEDS = 6


@dataclass(frozen=True)
class Speaker:
    """A synthetic speaker: one Kokoro voicepack, or the mean of several."""

    voicepacks: tuple[str, ...]
    accent: str = "a"  # Kokoro G2P: a = American English, b = British English

    @property
    def label(self) -> str:
        return "+".join(self.voicepacks)


SPEAKERS: dict[str, Speaker] = {
    # Unit crews: one infantry-side and one crew-side speaker per faction.
    "china-infantry": Speaker(("am_puck",)),
    "china-crew": Speaker(("am_fenrir", "am_puck")),
    "iran-infantry": Speaker(("am_michael",)),
    "iran-crew": Speaker(("am_michael", "bm_george")),
    "turkey-infantry": Speaker(("am_fenrir",)),
    "turkey-crew": Speaker(("bm_lewis",), "b"),
    "saudi-infantry": Speaker(("bm_george",), "b"),
    "saudi-crew": Speaker(("bm_fable",), "b"),
    "yemen-infantry": Speaker(("am_fenrir", "bm_fable")),
    "yemen-crew": Speaker(("bm_lewis", "am_michael"), "b"),
    # Classic mission controllers (not shipped in the RA2 mod).
    "china-control": Speaker(("am_michael", "am_puck")),
    "turkey-control": Speaker(("bm_george", "am_fenrir"), "b"),
    "redsea-control": Speaker(("am_michael", "bm_fable")),
    # Faction announcers (EVA), English only so alerts stay intelligible.
    "china-eva": Speaker(("af_bella",)),
    "iran-eva": Speaker(("af_sarah",)),
    "turkey-eva": Speaker(("af_heart",)),
    "saudi-eva": Speaker(("af_kore",)),
    "yemen-eva": Speaker(("af_aoede",)),
}


def base_language(code: str) -> str:
    return code.split("-")[0].lower()


def _cache_dir() -> str | None:
    return os.environ.get("RTSAI_TTS_CACHE") or None


def _hub_file(repo: str, filename: str, revision: str) -> str:
    from huggingface_hub import hf_hub_download

    return hf_hub_download(repo, filename, revision=revision, cache_dir=_cache_dir())


def _seed_everything(seed: int) -> None:
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
         "seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _english_number(match: re.Match) -> str:
    value = int(match.group())
    if value < 20:
        return _ONES[value]
    if value < 100:
        return _TENS[value // 10] + ("" if value % 10 == 0 else " " + _ONES[value % 10])
    return match.group()


def normalize_for_cer(text: str, language: str = "") -> str:
    text = unicodedata.normalize("NFKC", text)
    if language == "en":  # Whisper writes "20 minutes" and British spellings for the scripted words
        text = re.sub(r"\d+", _english_number, text.lower()).replace("cancelled", "canceled")
    text = re.sub("[ً-ْٰـ]", "", text)  # Arabic harakat and tatweel
    for source, target in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ی"),
                           ("ي", "ی"), ("ة", "ه"), ("ك", "ک"), ("‌", "")):
        text = text.replace(source, target)
    return re.sub(r"[^\w]", "", text.lower())


def character_error_rate(reference: str, hypothesis: str) -> float:
    if not reference:
        return 0.0 if not hypothesis else 1.0
    previous = list(range(len(hypothesis) + 1))
    for i, ref_char in enumerate(reference, 1):
        current = [i]
        for j, hyp_char in enumerate(hypothesis, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ref_char != hyp_char)))
        previous = current
    return previous[-1] / len(reference)


def trim_silence(audio: np.ndarray, rate: int, threshold_db: float = -42.0,
                 head: float = 0.03, tail: float = 0.09) -> np.ndarray:
    if audio.size == 0:
        return audio
    window = max(1, int(rate * 0.01))
    frames = len(audio) // window
    if frames == 0:
        return audio
    energy = np.sqrt(np.mean(audio[: frames * window].reshape(frames, window) ** 2, axis=1) + 1e-12)
    peak = float(np.max(np.abs(audio))) or 1.0
    loud = np.nonzero(20 * np.log10(energy / peak) > threshold_db)[0]
    if loud.size == 0:
        return audio
    start = max(0, loud[0] * window - int(rate * head))
    end = min(len(audio), (loud[-1] + 1) * window + int(rate * tail))
    return audio[start:end]


def fade(audio: np.ndarray, rate: int, seconds: float = 0.015) -> np.ndarray:
    count = min(len(audio) // 2, int(rate * seconds))
    if count:
        ramp = np.linspace(0.0, 1.0, count, dtype=np.float32)
        audio = audio.copy()
        audio[:count] *= ramp
        audio[-count:] *= ramp[::-1]
    return audio


@dataclass
class Take:
    audio: np.ndarray
    rate: int
    seed: int | None
    transcript: str
    cer: float

    @property
    def duration(self) -> float:
        return len(self.audio) / self.rate


@dataclass
class Reference:
    path: Path
    record: dict[str, object] = field(default_factory=dict)


class Synthesizer:
    """Lazily loads each engine once and renders lines to mono WAV files."""

    def __init__(self, device: str | None = None, verify: bool = True, seeds: int = 6, moss_seeds: int = 8,
                 accept_cer: float = 0.05) -> None:
        import torch

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.verify = verify
        self.seeds = seeds
        self.moss_seeds = moss_seeds
        self.accept_cer = accept_cer
        self.ffmpeg = shutil.which("ffmpeg")
        if not self.ffmpeg:
            raise RuntimeError("ffmpeg is required")
        self._work = Path(tempfile.mkdtemp(prefix="rtsai-tts-"))
        self._kokoro_model = None
        self._kokoro_pipelines: dict[str, object] = {}
        self._voicepacks: dict[str, object] = {}
        self._references: dict[tuple[str, str], Reference] = {}
        self._chatterbox = None
        self._chatterbox_conds: dict[tuple[str, float], object] = {}
        self._moss = None  # worker process
        self._whisper = None

    def close(self) -> None:
        if self._moss is not None:
            self._moss.stdin.close()
            self._moss.wait(timeout=60)
            self._moss = None
        shutil.rmtree(self._work, ignore_errors=True)

    # Kokoro -------------------------------------------------------------
    def _kokoro(self, accent: str):
        from kokoro import KModel, KPipeline

        spec = ENGINES["kokoro"]
        if self._kokoro_model is None:
            self._kokoro_model = KModel(
                repo_id=spec["model"],
                config=_hub_file(spec["model"], "config.json", spec["revision"]),
                model=_hub_file(spec["model"], spec["checkpoint"], spec["revision"]),
            ).to(self.device).eval()
        if accent not in self._kokoro_pipelines:
            self._kokoro_pipelines[accent] = KPipeline(lang_code=accent, repo_id=spec["model"], model=self._kokoro_model)
        return self._kokoro_pipelines[accent]

    def _voicepack(self, speaker: Speaker):
        import torch

        if speaker.label not in self._voicepacks:
            spec = ENGINES["kokoro"]
            packs = [torch.load(_hub_file(spec["model"], f"voices/{name}.pt", spec["revision"]), weights_only=True)
                     for name in speaker.voicepacks]
            self._voicepacks[speaker.label] = torch.mean(torch.stack(packs), dim=0)
        return self._voicepacks[speaker.label]

    def kokoro(self, text: str, speaker: Speaker, speed: float = 1.0) -> tuple[np.ndarray, int]:
        import torch

        pipeline = self._kokoro(speaker.accent)
        with torch.no_grad():
            chunks = [audio.detach().cpu().numpy() for _, _, audio in
                      pipeline(text, voice=self._voicepack(speaker), speed=speed) if audio is not None]
        return np.concatenate(chunks).astype(np.float32), 24000

    # Reference clips ----------------------------------------------------
    def reference(self, speaker_id: str, language: str = "en") -> Reference:
        """The cloning reference for a speaker: English from Kokoro, or a bootstrapped native clip."""
        key = (speaker_id, language)
        if key in self._references:
            return self._references[key]
        if language == "en":
            audio, rate = self.kokoro(REFERENCE_TEXT, SPEAKERS[speaker_id])
            path = self._work / f"reference-{speaker_id}-en.wav"
            sf.write(path, trim_silence(audio, rate), rate)
            reference = Reference(path, {"language": "en", "text": REFERENCE_TEXT,
                                         "engine": "kokoro", "kokoro_voicepacks": list(SPEAKERS[speaker_id].voicepacks)})
        else:
            english = self.reference(speaker_id, "en").path
            text = NATIVE_REFERENCE_TEXT[language]
            takes = []
            for seed in range(1, REFERENCE_SEEDS + 1):
                audio, rate = self.chatterbox(text, language, english, seed, cfg_weight=0.0)
                takes.append(self._take(audio, rate, seed, text, language))
                if takes[-1].cer <= self.accept_cer:
                    break
            best = min(takes, key=lambda take: (round(take.cer / 0.05), take.duration))
            path = self._work / f"reference-{speaker_id}-{language}.wav"
            sf.write(path, best.audio, best.rate)
            reference = Reference(path, {"language": language, "text": text, "engine": "chatterbox",
                                         "cfg_weight": 0.0, "cloned_from": "the speaker's English reference",
                                         "seed": best.seed, "asr_transcript": best.transcript,
                                         "cer": round(best.cer, 3)})
            print(f"  reference {speaker_id}/{language}: seed {best.seed}, CER {best.cer:.2f}", flush=True)
        self._references[key] = reference
        return reference

    # Chatterbox ---------------------------------------------------------
    def chatterbox(self, text: str, language: str, reference: Path, seed: int, exaggeration: float = 0.5,
                   cfg_weight: float = CHATTERBOX_CFG) -> tuple[np.ndarray, int]:
        import torch
        from huggingface_hub import snapshot_download

        spec = ENGINES["chatterbox"]
        if self._chatterbox is None:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS

            local = snapshot_download(spec["model"], revision=spec["revision"], cache_dir=_cache_dir(),
                                      allow_patterns=["ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt",
                                                      "grapheme_mtl_merged_expanded_v1.json", "conds.pt",
                                                      "Cangjie5_TC.json"])
            self._chatterbox = ChatterboxMultilingualTTS.from_local(local, self.device)
        key = (str(reference), exaggeration)
        if key not in self._chatterbox_conds:
            with torch.no_grad():
                self._chatterbox.prepare_conditionals(str(reference), exaggeration=exaggeration)
            self._chatterbox_conds[key] = self._chatterbox.conds
        # generate() only rewrites conds when the exaggeration differs, which the key rules out.
        self._chatterbox.conds = self._chatterbox_conds[key]
        _seed_everything(seed)
        with torch.no_grad():
            wav = self._chatterbox.generate(text, language_id=language, exaggeration=exaggeration,
                                            cfg_weight=cfg_weight, temperature=0.8)
        return wav.squeeze(0).detach().cpu().numpy().astype(np.float32), self._chatterbox.sr

    # MOSS-TTS-Nano Persian ---------------------------------------------
    def moss(self, text: str, reference: Path, seed: int) -> tuple[np.ndarray, int]:
        """Persian through a MOSS worker process (see _moss_worker for why it is separate)."""
        if self._moss is None:
            python = os.environ.get("RTSAI_MOSS_PYTHON") or sys.executable
            self._moss = subprocess.Popen([python, str(Path(__file__).resolve()), "--moss-worker", self.device],
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                          encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
        target = self._work / f"moss-{seed}.wav"
        request = {"text": text, "reference": str(reference), "seed": seed, "output": str(target)}
        self._moss.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self._moss.stdin.flush()
        reply = self._moss.stdout.readline()
        if not reply:
            raise SystemExit("MOSS worker exited; set RTSAI_MOSS_PYTHON to a Python with transformers 4.57.x")
        reply = json.loads(reply)
        if "error" in reply:
            raise RuntimeError(reply["error"])
        data, rate = sf.read(str(target), dtype="float32", always_2d=True)
        return data.mean(axis=1).astype(np.float32), rate

    # Verification -------------------------------------------------------
    def _asr(self):
        if self._whisper is None:
            from faster_whisper import WhisperModel
            from huggingface_hub import snapshot_download

            local = snapshot_download("Systran/faster-whisper-large-v3",
                                      revision="edaa852ec7e145841d8ffdb056a99866b5f0a478", cache_dir=_cache_dir())
            self._whisper = WhisperModel(local, device=self.device,
                                         compute_type="int8_float16" if self.device == "cuda" else "int8")
        return self._whisper

    def transcribe(self, audio: np.ndarray, rate: int, language: str) -> tuple[str, list[tuple[float, float]]]:
        """Transcript and the (start, end) seconds of each recognized word."""
        path = self._work / "asr.wav"
        sf.write(path, audio, rate)
        segments, _ = self._asr().transcribe(str(path), language=language, beam_size=5, word_timestamps=True,
                                             condition_on_previous_text=False, vad_filter=False)
        segments = list(segments)
        words = [(word.start, word.end) for segment in segments for word in (segment.words or [])]
        return "".join(segment.text for segment in segments).strip(), words

    def detect_speech(self, audio: np.ndarray, rate: int) -> str:
        """Speech in a sound effect, if any: voice-activity filtered, confident segments only."""
        path = self._work / "detect.wav"
        sf.write(path, audio, rate)
        segments, _ = self._asr().transcribe(str(path), beam_size=5, vad_filter=True,
                                             condition_on_previous_text=False)
        return " ".join(segment.text.strip() for segment in segments
                        if segment.no_speech_prob < 0.5 and segment.avg_logprob > -1.0).strip()

    def _take(self, audio: np.ndarray, rate: int, seed: int | None, text: str, language: str) -> Take:
        audio = trim_silence(audio, rate)
        if not self.verify:
            return Take(fade(audio, rate), rate, seed, "", 0.0)
        transcript, words = self.transcribe(audio, rate, language)
        if words:
            # Keep the recognized speech plus a margin; cloned engines sometimes add babble or breath after it.
            start = max(0, int((words[0][0] - 0.08) * rate))
            end = min(len(audio), int((words[-1][1] + 0.25) * rate))
            if end - start > rate * 0.2:
                audio = trim_silence(audio[start:end], rate)
        cer = character_error_rate(normalize_for_cer(text, language), normalize_for_cer(transcript, language))
        return Take(fade(audio, rate), rate, seed, transcript, cer)

    # Public API ---------------------------------------------------------
    def render(self, text: str, language: str, speaker_id: str, destination: Path, rate: float = 1.0,
               expressive: bool = False, script: str | None = None) -> dict[str, object]:
        """Speak `text` and write a mono WAV (engine sample rate) to `destination`.

        `rate` is a tempo factor (1.0 = engine default); Kokoro applies it natively,
        the cloned engines through ffmpeg's atempo. `script` is the plain wording
        when `text` carries pronunciation markup. Returns the provenance record.
        """
        script = script or text
        lang = base_language(language)
        engine = LANGUAGE_ENGINE[lang]
        speaker = SPEAKERS[speaker_id]
        exaggeration = 0.7 if expressive else 0.5
        takes: list[Take] = []
        reference = None
        if engine == "kokoro":
            audio, sample_rate = self.kokoro(text, speaker, speed=rate)
            takes.append(self._take(audio, sample_rate, None, script, lang))
        else:
            reference = self.reference(speaker_id, lang if engine == "chatterbox" else "en")
            attempts = self.moss_seeds if engine == "moss-fa" else self.seeds
            for seed in range(1, attempts + 1):
                try:
                    if engine == "moss-fa":
                        audio, sample_rate = self.moss(text, reference.path, seed)
                    else:
                        audio, sample_rate = self.chatterbox(text, lang, reference.path, seed, exaggeration)
                except RuntimeError as error:  # e.g. a sampled take that ends before its first audio frame
                    print(f"  seed {seed} failed: {error}", flush=True)
                    continue
                if len(audio) < sample_rate * 0.2:
                    continue
                takes.append(self._take(audio, sample_rate, seed, script, lang))
                if not self.verify or sum(take.cer <= self.accept_cer for take in takes) >= 2:
                    break
            if not takes:
                raise RuntimeError(f"{engine} produced no usable take for {script!r}")
        # Lowest error first; among equally good takes, the shortest (no trailing breath or mumble).
        best = min(takes, key=lambda take: (round(take.cer / 0.05), take.duration))
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = self._work / "take.wav"
        # Peak at -1 dBFS, like the edge-tts MP3s the processing chains were tuned on
        # (the Iran chain has no loudness normalization of its own).
        peak = float(np.max(np.abs(best.audio))) or 1.0
        sf.write(raw, best.audio * (0.89 / peak), best.rate, subtype="FLOAT")
        if engine != "kokoro" and abs(rate - 1.0) > 1e-3:
            subprocess.run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw),
                            "-af", f"atempo={rate:.4f}", "-c:a", "pcm_f32le", str(destination)], check=True)
        else:
            shutil.copyfile(raw, destination)
        spec = ENGINES[engine]
        if engine == "kokoro":
            method = "Kokoro voicepack"
        elif engine == "chatterbox":
            method = (f"Chatterbox clone (cfg_weight {CHATTERBOX_CFG}) of a synthetic {lang} reference clip, itself "
                      "cloned from the speaker's Kokoro English reference; no real person")
        else:
            method = "MOSS clone of the speaker's Kokoro English reference clip; no real person"
        record: dict[str, object] = {
            "engine": spec["engine"],
            "engine_id": engine,
            "model": spec["model"],
            "model_revision": spec["revision"],
            "license": spec["license"],
            "voice": {
                "speaker": speaker_id,
                "kokoro_voicepacks": list(speaker.voicepacks),
                "method": method,
                **({"reference": reference.record} if reference else {}),
            },
            "language": language,
            "text": script,
            "tempo": rate,
            "seed": best.seed,
            "takes": len(takes),
            "qa": {"asr_transcript": best.transcript, "cer": round(best.cer, 3)} if self.verify else None,
            "generated_at": _dt.date.today().isoformat(),
            "generator_version": GENERATOR_VERSION,
        }
        if engine == "chatterbox":
            record["exaggeration"] = exaggeration
        if engine == "moss-fa":
            record["base_model"] = spec["base_model"]
            record["codec"] = spec["codec"]
        return record


def _moss_worker(device: str) -> None:
    """Serve MOSS-TTS-Nano requests, one JSON object per line on stdin and stdout.

    MOSS ships as Hugging Face remote code written for transformers 4.57; under
    transformers 5.x (which chatterbox-tts 0.1.7 pins) it loads without error but
    produces unintelligible speech. It therefore runs in its own interpreter,
    RTSAI_MOSS_PYTHON, which needs torch, transformers==4.57.1, sentencepiece,
    soundfile and huggingface_hub.
    """
    import torch
    import torchaudio
    import transformers
    from transformers import AutoModel, AutoModelForCausalLM

    if not transformers.__version__.startswith("4."):
        raise SystemExit(f"MOSS worker needs transformers 4.57.x, found {transformers.__version__}; "
                         "point RTSAI_MOSS_PYTHON at such an interpreter")
    protocol = sys.stdout
    sys.stdout = sys.stderr  # model code may print; keep the protocol channel clean

    # The remote code reads and writes audio through torchaudio, which now needs torchcodec.
    def _load(path, *args, **kwargs):
        data, rate = sf.read(str(path), dtype="float32", always_2d=True)
        return torch.from_numpy(data.T.copy()), rate

    def _save(path, tensor, sample_rate, *args, **kwargs):
        sf.write(str(path), tensor.detach().cpu().numpy().T, sample_rate)

    torchaudio.load, torchaudio.save = _load, _save
    spec = ENGINES["moss-fa"]
    base_repo, base_revision = str(spec["base_model"]).split("@")
    codec_repo, codec_revision = str(spec["codec"]).split("@")
    model = AutoModelForCausalLM.from_pretrained(base_repo, revision=base_revision, trust_remote_code=True,
                                                 attn_implementation="sdpa", dtype=torch.float32,
                                                 cache_dir=_cache_dir())
    state = torch.load(_hub_file(str(spec["model"]), "pytorch_model.bin", str(spec["revision"])),
                       map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    model.tie_weights()
    for module in model.modules():
        if hasattr(module, "attn_implementation"):
            module.attn_implementation = "sdpa"  # no flash-attn dependency
    model = model.to(device).eval()
    codec = AutoModel.from_pretrained(codec_repo, revision=codec_revision, trust_remote_code=True,
                                      cache_dir=_cache_dir()).to(device).eval()
    for line in sys.stdin:
        request = json.loads(line)
        try:
            _seed_everything(int(request["seed"]))
            model.inference(text=request["text"], output_audio_path=request["output"], mode="voice_clone",
                            prompt_audio_path=request["reference"], audio_tokenizer=codec, device=device,
                            do_sample=True)
            reply = {"ok": True}
        except RuntimeError as error:  # e.g. a sampled take that ends before its first audio frame
            reply = {"error": str(error)}
        protocol.write(json.dumps(reply) + "\n")
        protocol.flush()


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--moss-worker":
    _moss_worker(sys.argv[2] if len(sys.argv) > 2 else "cuda")
