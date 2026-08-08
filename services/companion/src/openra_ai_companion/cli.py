from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import threading
import time
from pathlib import Path

from openra_ai_worldgen.server import create_server as create_worldgen_server

from .bridge import OpenRABridge
from .core import Companion
from .hotkeys import VoiceHotkeys
from .server import create_server as create_companion_server, serve
from .voice import AudioPlayer, play_wav, record_question


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openra-ai-companion")
    commands = parser.add_subparsers(dest="command", required=True)
    server = commands.add_parser("serve", help="start the local companion API")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8787)
    watch = commands.add_parser("watch", help="watch a running OpenRA match")
    watch.add_argument("--bridge", default="127.0.0.1:9998")
    watch.add_argument("--interval", type=float, default=0.5)
    watch.add_argument(
        "--speak",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="speak companion responses (enabled by default; use --no-speak to disable)",
    )
    watch.add_argument("--voice-hotkeys", action="store_true")
    watch.add_argument("--game-pid", type=int, default=0)
    watch.add_argument("--control-port", type=int, default=8787)
    watch.add_argument("--worldgen-port", type=int, default=8788)
    watch.add_argument("--mission-output", type=Path, default=Path("generated/missions"))
    watch.add_argument("--mission-install", type=Path)
    ask = commands.add_parser("ask", help="ask about a supplied snapshot")
    ask.add_argument("question")
    ask.add_argument("--snapshot", required=True, help="path to a JSON GameSnapshot")
    voice = commands.add_parser("voice", help="record one voice question and answer aloud")
    voice.add_argument("--bridge", default="127.0.0.1:9998")
    voice.add_argument("--seconds", type=float, default=4.0)
    return parser


def _speak(companion: Companion, text: str, player: AudioPlayer | None = None) -> bool:
    try:
        audio, metadata = companion.speech(text)
        if metadata.get("interrupted"):
            return False
        if player:
            player.play(audio)
        else:
            play_wav(audio)
    except Exception as exc:
        print(f"Speech unavailable: {exc}")
        return False
    return bool(audio)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    if platform.system() == "Windows":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "serve":
        serve(args.host, args.port)
        return 0
    companion = Companion()
    if args.command == "ask":
        from pathlib import Path
        from .models import GameSnapshot

        companion.latest_snapshot = GameSnapshot.from_dict(json.loads(Path(args.snapshot).read_text(encoding="utf-8")))
        response = companion.ask(args.question)
        print(response.text)
        return 0
    if args.command == "voice":
        with OpenRABridge(args.bridge) as bridge:
            companion.latest_snapshot = bridge.observe()
        print("Listening...")
        transcript = companion.transcribe(record_question(args.seconds)).text
        print(f"You: {transcript}")
        answer = companion.ask(transcript).text
        print(f"Companion: {answer}")
        _speak(companion, answer)
        return 0

    player = AudioPlayer() if args.speak else None
    control_server = create_companion_server("127.0.0.1", args.control_port, companion, player)
    worldgen_server = create_worldgen_server(
        "127.0.0.1",
        args.worldgen_port,
        args.mission_output,
        args.mission_install,
    )
    for name, server in (("control", control_server), ("worldgen", worldgen_server)):
        threading.Thread(
            target=server.serve_forever,
            name=f"OpenRA-AI-{name}-server",
            daemon=True,
        ).start()
    print(f"AI Console: http://127.0.0.1:{args.control_port}/")
    print(f"Earth Mission Studio: http://127.0.0.1:{args.worldgen_port}/")
    with OpenRABridge(args.bridge) as bridge:
        def publish_status(state: str, message: str) -> None:
            bridge.update_companion_status(
                state,
                message,
                enabled=companion.enabled,
                muted=companion.muted,
            )

        control_server.status_publisher = publish_status

        hotkeys = (
            VoiceHotkeys(companion, player, lambda text: _speak(companion, text, player), publish_status)
            if args.voice_hotkeys and player
            else None
        )
        if hotkeys:
            hotkeys.start()
        print("Watching OpenRA. Press Ctrl+C to stop.")
        waiting_reported = False
        insight_expires_at = 0.0
        try:
            while True:
                if not _pid_alive(args.game_pid):
                    print("OpenRA exited; stopping companion.")
                    break
                try:
                    snapshot = bridge.observe()
                    if waiting_reported:
                        print("Connected to the live match.")
                        waiting_reported = False
                except RuntimeError:
                    if not waiting_reported:
                        print("Waiting for a match with the companion bridge enabled...")
                        waiting_reported = True
                    time.sleep(max(0.25, args.interval))
                    continue
                if hotkeys and hotkeys.active.is_set():
                    companion.latest_snapshot = snapshot
                    response = None
                else:
                    response = companion.observe(snapshot)
                if response and response.text:
                    print(f"[{response.insight.key}] {response.text}")
                    publish_status(
                        "speaking" if player and not companion.muted else "insight",
                        f"AI  •  {response.text}",
                    )
                    if player:
                        _speak(companion, response.text, player)
                    insight_expires_at = time.monotonic() + 8
                elif insight_expires_at and time.monotonic() >= insight_expires_at:
                    if not hotkeys or not hotkeys.active.is_set():
                        publish_status(*companion.idle_status())
                        insight_expires_at = 0.0
                time.sleep(max(0.1, args.interval))
        except KeyboardInterrupt:
            companion.interrupt()
        finally:
            if hotkeys:
                hotkeys.stop()
            elif player:
                player.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
