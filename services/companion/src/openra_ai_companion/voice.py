from __future__ import annotations

import atexit
import io
import platform
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable


def _wav_bytes(frames: list[bytes], sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(frames))
    return output.getvalue()


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

    def play(self, audio: bytes) -> None:
        if not audio:
            return
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

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()


def play_wav(audio: bytes) -> None:
    if not audio:
        return
    if platform.system() == "Windows":
        import winsound

        winsound.PlaySound(audio, winsound.SND_MEMORY)
        return
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        handle.write(audio)
        path = Path(handle.name)
    try:
        command = ["afplay", str(path)] if platform.system() == "Darwin" else ["aplay", "-q", str(path)]
        subprocess.run(command, check=False)
    finally:
        path.unlink(missing_ok=True)
