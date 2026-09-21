from __future__ import annotations

import array
import atexit
import io
import math
import platform
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable


def microphone_status(*, check_device: bool = True) -> dict[str, object]:
    """Report whether microphone capture is bundled and usable.

    Package verification uses the dependency-only mode because build hosts do
    not necessarily have an input device. Runtime diagnostics also inspect the
    actual PortAudio device list so a missing dependency and a missing
    microphone are reported as different failures.
    """
    try:
        import sounddevice as sd
    except ImportError as exc:
        return {
            "available": False,
            "dependency_available": False,
            "device_available": False,
            "device_name": "",
            "reason": f"Microphone capture dependency is missing: {exc}",
        }

    if not check_device:
        return {
            "available": True,
            "dependency_available": True,
            "device_available": False,
            "device_name": "",
            "reason": "",
        }

    try:
        devices = list(sd.query_devices())
        input_devices = [device for device in devices if device["max_input_channels"] > 0]
        if not input_devices:
            return {
                "available": False,
                "dependency_available": True,
                "device_available": False,
                "device_name": "",
                "reason": "No input microphone is available to the local audio runtime.",
            }

        default_input = sd.default.device[0]
        selected = (
            devices[default_input]
            if isinstance(default_input, int) and default_input >= 0
            else input_devices[0]
        )
        return {
            "available": True,
            "dependency_available": True,
            "device_available": True,
            "device_name": str(selected["name"]),
            "reason": "",
        }
    except Exception as exc:
        return {
            "available": False,
            "dependency_available": True,
            "device_available": False,
            "device_name": "",
            "reason": f"Microphone device discovery failed: {exc}",
        }


def _wav_bytes(frames: list[bytes], sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(frames))
    return output.getvalue()


def prepare_voice_audio(
    audio: bytes,
    *,
    target_peak: int = 12_000,
    maximum_gain: float = 8.0,
) -> tuple[bytes, dict[str, object]]:
    """Measure a microphone WAV and safely lift quiet speech for Whisper.

    Device discovery alone cannot prove that macOS is delivering useful audio.
    These measurements let the UI distinguish an installed Whisper model from
    an actually audible recording.  Quiet captures are amplified before local
    transcription, while true digital silence is left untouched.
    """
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frame_count = wav.getnframes()
            frames = wav.readframes(frame_count)

        if channels != 1 or sample_width != 2:
            raise ValueError("voice capture must be mono 16-bit PCM")

        samples = array.array("h")
        samples.frombytes(frames)
        if sys.byteorder != "little":
            samples.byteswap()
        peak = max((abs(value) for value in samples), default=0)
        rms = math.sqrt(sum(value * value for value in samples) / max(1, len(samples)))
        duration = frame_count / max(1, sample_rate)
        audible = peak >= 64 and rms >= 8
        gain = 1.0

        if audible and peak < target_peak:
            gain = min(maximum_gain, target_peak / peak)
            if gain > 1.05:
                samples = array.array(
                    "h",
                    (max(-32_768, min(32_767, round(value * gain))) for value in samples),
                )
                output_frames = array.array("h", samples)
                if sys.byteorder != "little":
                    output_frames.byteswap()
                audio = _wav_bytes([output_frames.tobytes()], sample_rate)

        return audio, {
            "valid_wav": True,
            "audible": audible,
            "duration_seconds": round(duration, 2),
            "rms": round(rms, 1),
            "peak": peak,
            "gain": round(gain, 2),
        }
    except (EOFError, ValueError, wave.Error):
        # Tests and third-party callers may supply encoded/non-WAV audio. Keep
        # the existing transcription behavior instead of rejecting it here.
        return audio, {
            "valid_wav": False,
            "audible": True,
            "duration_seconds": 0.0,
            "rms": 0.0,
            "peak": 0,
            "gain": 1.0,
        }


def _normalize_wav(audio: bytes) -> bytes:
    """Replace streaming WAV sentinel sizes with concrete file lengths."""
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise ValueError("speech audio is not a valid RIFF/WAVE file")

    normalized = bytearray(audio)
    struct.pack_into("<I", normalized, 4, len(normalized) - 8)
    offset = 12
    while offset + 8 <= len(normalized):
        chunk_id = normalized[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", normalized, offset + 4)[0]
        data_offset = offset + 8
        if chunk_id == b"data":
            struct.pack_into("<I", normalized, offset + 4, len(normalized) - data_offset)
            return bytes(normalized)
        if chunk_size == 0xFFFFFFFF or data_offset + chunk_size > len(normalized):
            break
        offset = data_offset + chunk_size + (chunk_size & 1)
    raise ValueError("speech WAV does not contain a readable data chunk")


def playback_hold_seconds(
    playback: float | bool | None,
    fallback_seconds: float,
    *,
    grace_seconds: float = 0.35,
) -> float:
    """Keep the matching HUD message visible through asynchronous speech playback."""
    if isinstance(playback, (int, float)) and not isinstance(playback, bool) and playback > 0:
        return max(fallback_seconds, float(playback) + max(0.0, grace_seconds))
    return fallback_seconds


def record_question(seconds: float = 4.0, sample_rate: int = 16_000) -> bytes:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("Install the companion's voice extra to record the microphone") from exc
    frames: list[bytes] = []

    def callback(indata, frame_count, time_info, status) -> None:  # noqa: ANN001
        if status:
            print(f"microphone: {status}")
        frames.append(bytes(indata))

    with sd.RawInputStream(samplerate=sample_rate, channels=1, dtype="int16", callback=callback):
        time.sleep(seconds)
    return _wav_bytes(frames, sample_rate)


def record_while(
    is_pressed: Callable[[], bool],
    *,
    sample_rate: int = 16_000,
    maximum_seconds: float = 15.0,
    minimum_seconds: float = 0.25,
) -> bytes:
    """Record mono WAV audio while a push-to-talk control remains pressed."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("Install the companion's voice extra to record the microphone") from exc

    frames: list[bytes] = []
    started = time.monotonic()

    def callback(indata, frame_count, time_info, status) -> None:  # noqa: ANN001
        if status:
            print(f"microphone: {status}")
        frames.append(bytes(indata))

    with sd.RawInputStream(samplerate=sample_rate, channels=1, dtype="int16", callback=callback):
        while is_pressed() and time.monotonic() - started < maximum_seconds:
            time.sleep(0.02)

    if time.monotonic() - started < minimum_seconds or not frames:
        return b""
    return _wav_bytes(frames, sample_rate)


class AudioPlayer:
    """Asynchronous speech playback that can be stopped immediately."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._path: Path | None = None
        self._process: subprocess.Popen | None = None
        atexit.register(self.stop)

    def _stop_locked(self) -> None:
        if platform.system() == "Windows":
            import winsound

            winsound.PlaySound(None, 0)
        elif self._process and self._process.poll() is None:
            self._process.terminate()
        self._process = None
        if self._path:
            self._path.unlink(missing_ok=True)
            self._path = None

    def play(self, audio: bytes) -> float:
        if not audio:
            return 0.0
        audio = _normalize_wav(audio)
        with wave.open(io.BytesIO(audio), "rb") as wav:
            duration = wav.getnframes() / max(1, wav.getframerate())
        with self._lock:
            self._stop_locked()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                handle.write(audio)
                self._path = Path(handle.name)

            if platform.system() == "Windows":
                import winsound

                winsound.PlaySound(
                    str(self._path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
            else:
                command = ["afplay", str(self._path)] if platform.system() == "Darwin" else ["aplay", "-q", str(self._path)]
                self._process = subprocess.Popen(command)
        return duration

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()


def play_wav(audio: bytes) -> None:
    if not audio:
        return
    audio = _normalize_wav(audio)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        handle.write(audio)
        path = Path(handle.name)
    try:
        if platform.system() == "Windows":
            import winsound

            # SND_MEMORY rejects WAV variants that Windows accepts from a file.
            # The live AudioPlayer uses the same filename-based path.
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_NODEFAULT)
        else:
            command = ["afplay", str(path)] if platform.system() == "Darwin" else ["aplay", "-q", str(path)]
            subprocess.run(command, check=False)
    finally:
        path.unlink(missing_ok=True)
