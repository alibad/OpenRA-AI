from __future__ import annotations

import io
import platform
import subprocess
import tempfile
import time
import wave
from pathlib import Path


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
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(frames))
    return output.getvalue()


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
