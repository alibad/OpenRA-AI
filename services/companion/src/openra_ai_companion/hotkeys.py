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

    PUSH_TO_TALK = 0x20  # Space
    TOGGLE_MUTE = 0x4D  # M
    TOGGLE_ENABLED = 0x41  # A
    CONTROL = 0x11
    SHIFT = 0x10

    def __init__(
        self,
        companion: Companion,
        player: AudioPlayer,
        speak: Callable[[str], None],
        publish_status: Callable[[str, str], None],
    ) -> None:
        self.companion = companion
        self.player = player
        self.speak = speak
        self.publish_status = publish_status
        self.active = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._question_thread: threading.Thread | None = None

    @staticmethod
    def supported() -> bool:
        return platform.system() == "Windows"

    @staticmethod
    def _pressed(key: int) -> bool:
        return bool(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000)

    def _combo_pressed(self, key: int, *, shift: bool = False) -> bool:
        return (
            self._pressed(key)
            and self._pressed(self.CONTROL)
            and self._pressed(self.SHIFT) == shift
        )

    def _set_status(self, state: str, message: str) -> None:
        try:
            self.publish_status(state, message)
        except Exception:
            pass

    def start(self) -> bool:
        if not self.supported():
            print("Global voice hotkeys are currently available on Windows only.")
            return False
        self._thread = threading.Thread(target=self._run, name="OpenRA-AI-Voice-Hotkeys", daemon=True)
        self._thread.start()
        self._set_status("ready", "AI READY  •  HOLD CTRL+SPACE TO ASK")
        print("Voice controls: hold Ctrl+Space to ask, Ctrl+Shift+M to mute, Ctrl+Shift+A to disable or enable.")
        return True

    def stop(self) -> None:
        self._stop.set()
        self.companion.interrupt()
        self.player.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        if self._question_thread and self._question_thread.is_alive():
            self._question_thread.join(timeout=1)

    def _wait_for_release(self, key: int) -> None:
        while self._pressed(key) and not self._stop.is_set():
            time.sleep(0.03)

    def _voice_question(self) -> None:
        self.active.set()
        self.companion.interrupt()
        self.player.stop()
        try:
            if not self.companion.enabled:
                print("Companion is disabled. Press Ctrl+Shift+A to enable it.")
                self._wait_for_release(self.PUSH_TO_TALK)
                return

            self._set_status("listening", "● LISTENING  •  RELEASE TO ASK")
            print("Listening... release Ctrl+Space when you finish speaking.")
            audio = record_while(lambda: self._combo_pressed(self.PUSH_TO_TALK) and not self._stop.is_set())
            if not audio or self._stop.is_set():
                return
            self._set_status("transcribing", "AI TRANSCRIBING  •  CTRL+SPACE TO INTERRUPT")
            transcript = self.companion.transcribe(audio).text
            print(f"You: {transcript}")
            if not transcript.strip():
                return
            transcript_started = time.monotonic()
            self._set_status("transcript", f"YOU  •  {transcript.strip()}")
            answer = self.companion.ask(transcript)
            self._stop.wait(max(0.0, 1.25 - (time.monotonic() - transcript_started)))
            if answer.text and not answer.interrupted:
                print(f"Companion: {answer.text}")
                self._set_status(
                    "insight" if self.companion.muted else "speaking",
                    f"AI  •  {answer.text}",
                )
                if not self.companion.muted:
                    self.speak(answer.text)
                self._stop.wait(min(6.0, max(2.0, len(answer.text) / 14)))
        except Exception as exc:  # Keep the match running if microphone or routing fails.
            print(f"Voice question failed: {exc}")
            self._set_status("error", "AI UNAVAILABLE  •  GAMEPLAY UNAFFECTED")
            self._stop.wait(3)
        finally:
            self.active.clear()
            if self.companion.enabled:
                self._set_status(*self.companion.idle_status())

    def _run(self) -> None:
        previous_push_to_talk = False
        previous_mute = False
        previous_enabled = False
        while not self._stop.is_set():
            push_to_talk = self._combo_pressed(self.PUSH_TO_TALK)
            mute = self._combo_pressed(self.TOGGLE_MUTE, shift=True)
            enabled = self._combo_pressed(self.TOGGLE_ENABLED, shift=True)

            if push_to_talk and not previous_push_to_talk:
                if self.active.is_set():
                    self.companion.interrupt()
                    self.player.stop()
                    self._set_status("ready", "AI INTERRUPTED  •  HOLD CTRL+SPACE TO ASK")
                else:
                    self._question_thread = threading.Thread(
                        target=self._voice_question,
                        name="OpenRA-AI-Voice-Question",
                        daemon=True,
                    )
                    self._question_thread.start()
            if mute and not previous_mute:
                state = self.companion.configure(muted=not self.companion.muted)
                if state["muted"]:
                    self.player.stop()
                self._set_status(*self.companion.idle_status())
                print("Companion voice off." if state["muted"] else "Companion voice on.")
            if enabled and not previous_enabled:
                state = self.companion.configure(enabled=not self.companion.enabled)
                if not state["enabled"]:
                    self.player.stop()
                self._set_status(
                    "ready" if state["enabled"] else "disabled",
                    "AI READY  •  HOLD CTRL+SPACE TO ASK"
                    if state["enabled"]
                    else "AI OFF  •  CTRL+SHIFT+A TO ENABLE",
                )
                print("Companion enabled." if state["enabled"] else "Companion disabled.")

            previous_push_to_talk = push_to_talk
            previous_mute = mute
            previous_enabled = enabled
            time.sleep(0.03)
