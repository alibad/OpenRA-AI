from __future__ import annotations

import ctypes
import platform
import threading
import time
from collections.abc import Callable

from .core import Companion
from .voice import AudioPlayer, playback_hold_seconds, record_while


def console_print(message: str) -> None:
    """Keep redirected Windows logs from crashing on non-CP1252 transcripts."""
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", errors="backslashreplace").decode("ascii"))


def response_hud_state(response: object, default_state: str) -> str:
    """Map action receipts onto durable, player-readable tactical-feed states."""
    metadata = getattr(response, "metadata", {})
    action = metadata.get("action") if isinstance(metadata, dict) else None
    action_state = str(action.get("state", "")) if isinstance(action, dict) else ""
    return {
        "pending": "action-pending",
        "executed": "action-executed",
        "rejected": "action-rejected",
        "failed": "action-rejected",
        "unavailable": "action-rejected",
        "expired": "action-rejected",
        "cancelled": "action-cancelled",
    }.get(action_state, default_state)


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
        speak: Callable[[str], float | bool | None],
        publish_status: Callable[[str, str], None],
    ) -> None:
        self.companion = companion
        self.player = player
        self.speak = speak
        self.publish_status = publish_status
        self.active = threading.Event()
        self._external_hold = threading.Event()
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

    def start(self, *, global_listener: bool = True) -> bool:
        if not self.supported():
            print("Global voice hotkeys are currently available on Windows only.")
            return False
        if global_listener:
            self._thread = threading.Thread(target=self._run, name="OpenRA-AI-Voice-Hotkeys", daemon=True)
            self._thread.start()
        self._set_status(*self.companion.idle_status())
        print("AI controls are active and remappable under Settings > Hotkeys > AI Assistant.")
        return True

    def stop(self) -> None:
        self._stop.set()
        self._external_hold.clear()
        self.companion.interrupt()
        self.player.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        if self._question_thread and self._question_thread.is_alive():
            self._question_thread.join(timeout=1)

    def _wait_for_release(self, key: int) -> None:
        while self._pressed(key) and not self._stop.is_set():
            time.sleep(0.03)

    def _voice_question(self, is_pressed: Callable[[], bool] | None = None) -> None:
        self.active.set()
        self.companion.begin_user_turn()
        self.player.stop()
        try:
            if not self.companion.enabled:
                print("Companion is disabled. Enable it under Settings > AI > Assistant.")
                self._wait_for_release(self.PUSH_TO_TALK)
                return

            self._set_status("listening", "● LISTENING  •  RELEASE TO ASK")
            print("Listening... release the Ask AI key when you finish speaking.")
            held = is_pressed or (lambda: self._combo_pressed(self.PUSH_TO_TALK))
            audio = record_while(lambda: held() and not self._stop.is_set())
            if not audio or self._stop.is_set():
                return
            self._set_status("transcribing", "AI TRANSCRIBING  •  PRESS ASK AGAIN TO INTERRUPT")
            transcript = self.companion.transcribe(audio).text
            if not transcript.strip():
                return
            transcript_started = time.monotonic()
            self._set_status("transcript", f"YOU  •  {transcript.strip()}")
            console_print(f"You: {transcript}")
            answer = self.companion.handle_player_input(transcript)
            self._stop.wait(max(0.0, 1.25 - (time.monotonic() - transcript_started)))
            if answer.text and not answer.interrupted:
                console_print(f"Companion: {answer.text}")
                default_state = "insight" if self.companion.muted else "speaking"
                self._set_status(
                    response_hud_state(answer, default_state),
                    f"AI  •  {answer.text}",
                )
                if not self.companion.muted:
                    playback = self.speak(answer.text)
                    answer_hold = playback_hold_seconds(
                        playback,
                        min(20.0, max(2.0, len(answer.text) / 14)),
                    )
                else:
                    answer_hold = min(8.0, max(2.0, len(answer.text) / 18))
                self._stop.wait(answer_hold)
        except Exception as exc:  # Keep the match running if microphone or routing fails.
            console_print(f"Voice question failed: {exc}")
            self._set_status("error", "AI UNAVAILABLE  •  GAMEPLAY UNAFFECTED")
            self._stop.wait(3)
        finally:
            self.companion.end_user_turn()
            self.active.clear()
            if self.companion.enabled:
                self._set_status(*self.companion.idle_status())

    def _launch_question(self, is_pressed: Callable[[], bool]) -> bool:
        if self.active.is_set():
            self.companion.interrupt()
            self.player.stop()
            self._external_hold.clear()
            self._set_status("ready", "AI INTERRUPTED  •  HOLD ASK KEY TO SPEAK")
            return False
        self._question_thread = threading.Thread(
            target=lambda: self._voice_question(is_pressed),
            name="OpenRA-AI-Voice-Question",
            daemon=True,
        )
        self._question_thread.start()
        return True

    def start_question(self) -> bool:
        """Start push-to-talk from the native, remappable OpenRA hotkey."""
        self._external_hold.set()
        started = self._launch_question(self._external_hold.is_set)
        if not started:
            self._external_hold.clear()
        return started

    def stop_question(self) -> bool:
        """Release native push-to-talk without interrupting answer generation."""
        was_held = self._external_hold.is_set()
        self._external_hold.clear()
        return was_held

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
                    self._set_status("ready", "AI INTERRUPTED  •  HOLD ASK KEY TO SPEAK")
                else:
                    self._launch_question(
                        lambda: self._combo_pressed(self.PUSH_TO_TALK),
                    )
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
                    "AI READY  •  HOLD ASK KEY TO SPEAK"
                    if state["enabled"]
                    else "AI OFF  •  ENABLE THE COMPANION IN SETTINGS",
                )
                print("Companion enabled." if state["enabled"] else "Companion disabled.")

            previous_push_to_talk = push_to_talk
            previous_mute = mute
            previous_enabled = enabled
            time.sleep(0.03)
