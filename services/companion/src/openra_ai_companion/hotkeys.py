from __future__ import annotations

import ctypes
import platform
import threading
import time
from collections.abc import Callable

from .core import Companion
from .voice import AudioPlayer, record_while


class VoiceHotkeys:
    """Global, dialog-free controls for the live companion on Windows."""

    PUSH_TO_TALK = 0x77  # F8
    TOGGLE_MUTE = 0x78  # F9
    TOGGLE_ENABLED = 0x79  # F10

    def __init__(self, companion: Companion, player: AudioPlayer, speak: Callable[[str], None]) -> None:
        self.companion = companion
        self.player = player
        self.speak = speak
        self.active = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @staticmethod
    def supported() -> bool:
        return platform.system() == "Windows"

    @staticmethod
    def _pressed(key: int) -> bool:
        return bool(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000)

    def start(self) -> bool:
        if not self.supported():
            print("Global voice hotkeys are currently available on Windows only.")
            return False
        self._thread = threading.Thread(target=self._run, name="OpenRA-AI-Voice-Hotkeys", daemon=True)
        self._thread.start()
        print("Voice controls: hold F8 to ask, tap F9 to mute, tap F10 to disable or enable.")
        return True

    def stop(self) -> None:
        self._stop.set()
        self.companion.interrupt()
        self.player.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

    def _wait_for_release(self, key: int) -> None:
        while self._pressed(key) and not self._stop.is_set():
            time.sleep(0.03)

    def _voice_question(self) -> None:
        self.active.set()
        self.companion.interrupt()
        self.player.stop()
        try:
            if not self.companion.enabled:
                print("Companion is disabled. Tap F10 to enable it.")
                self._wait_for_release(self.PUSH_TO_TALK)
                return
            if self.companion.muted:
                print("Companion is muted. Tap F9 to unmute it.")
                self._wait_for_release(self.PUSH_TO_TALK)
                return

            print("Listening... release F8 when you finish speaking.")
            audio = record_while(lambda: self._pressed(self.PUSH_TO_TALK) and not self._stop.is_set())
            if not audio or self._stop.is_set():
                return
            transcript = self.companion.transcribe(audio).text
            print(f"You: {transcript}")
            if not transcript.strip():
                return
            answer = self.companion.ask(transcript)
            if answer.text and not answer.interrupted:
                print(f"Companion: {answer.text}")
                self.speak(answer.text)
        except Exception as exc:  # Keep the match running if microphone or routing fails.
            print(f"Voice question failed: {exc}")
        finally:
            self.active.clear()

    def _run(self) -> None:
        previous_mute = False
        previous_enabled = False
        while not self._stop.is_set():
            push_to_talk = self._pressed(self.PUSH_TO_TALK)
            mute = self._pressed(self.TOGGLE_MUTE)
            enabled = self._pressed(self.TOGGLE_ENABLED)

            if push_to_talk:
                self._voice_question()
            if mute and not previous_mute:
                state = self.companion.configure(muted=not self.companion.muted)
                if state["muted"]:
                    self.player.stop()
                print("Companion muted." if state["muted"] else "Companion unmuted.")
            if enabled and not previous_enabled:
                state = self.companion.configure(enabled=not self.companion.enabled)
                if not state["enabled"]:
                    self.player.stop()
                print("Companion enabled." if state["enabled"] else "Companion disabled.")

            previous_mute = mute
            previous_enabled = enabled
            time.sleep(0.03)
