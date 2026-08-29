from __future__ import annotations

import argparse
import asyncio
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
from .hotkeys import VoiceHotkeys, console_print, response_hud_state
from .models import CompanionResponse, GameSnapshot
from .server import create_server as create_companion_server, serve
from .strategy_contracts import strategy_contract
from .strategy_director import StrategyDirector
from .voice import AudioPlayer, microphone_status, playback_hold_seconds, play_wav, record_question
from .agent_models import default_agent_model, default_agent_provider, default_agent_router_url


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
    watch.add_argument(
        "--parent-pid",
        type=int,
        default=0,
        help="exit when the owning launcher exits (used when the control server starts before the game)",
    )
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
    voice_check = commands.add_parser("voice-check", help="verify local microphone capture support")
    voice_check.add_argument(
        "--dependencies-only",
        action="store_true",
        help="verify bundled capture libraries without requiring microphone hardware",
    )
    agent_provider = default_agent_provider()
    autoplay = commands.add_parser("autoplay", help="run an autonomous AI-controlled headless match")
    autoplay.add_argument("--provider", default=agent_provider)
    autoplay.add_argument("--model", default=default_agent_model(agent_provider))
    autoplay.add_argument("--router-url", default=default_agent_router_url())
    autoplay.add_argument("--map", dest="map_name", default="singles.oramap")
    autoplay.add_argument("--opponent", default="beginner")
    autoplay.add_argument("--seed", type=int, default=20260810)
    autoplay.add_argument("--port", type=int, default=9997)
    autoplay.add_argument("--max-rounds", type=int, default=40)
    autoplay.add_argument("--max-turns", type=int, default=24)
    autoplay.add_argument("--evidence-dir", type=Path)
    autoplay.add_argument("--engine", type=Path)
    autoplay.add_argument("--reuse-engine", action="store_true")
    learn = commands.add_parser("learn", help="run reviewed autonomous attempts until a verified win")
    learn.add_argument("--provider", default=agent_provider)
    learn.add_argument("--model", default=default_agent_model(agent_provider))
    learn.add_argument("--router-url", default=default_agent_router_url())
    learn.add_argument("--map", dest="map_name", default="singles.oramap")
    learn.add_argument("--opponent", default="beginner")
    learn.add_argument("--seed", type=int, default=20260810)
    learn.add_argument("--port", type=int, default=9997)
    learn.add_argument("--attempts", type=int, default=5)
    learn.add_argument("--max-rounds", type=int, default=40)
    learn.add_argument("--max-turns", type=int, default=24)
    learn.add_argument("--evidence-root", type=Path)
    learn.add_argument("--engine", type=Path)
    mission_eval = commands.add_parser("mission-eval", help="evaluate the assistant against the Red Alert mission corpus")
    mission_eval.add_argument("--campaign", default="", help="optional case-insensitive campaign-name filter")
    mission_eval.add_argument("--mission", dest="missions", action="append", default=[], help="evaluate one mission id; repeat to select several")
    mission_eval.add_argument("--seed", type=int, default=20260811)
    mission_eval.add_argument("--port", type=int, default=9997)
    mission_eval.add_argument("--max-ticks", type=int, default=30_000)
    mission_eval.add_argument("--stall-ticks", type=int, default=1_000)
    mission_eval.add_argument("--advance-ticks", type=int, default=125)
    mission_eval.add_argument("--evidence-root", type=Path)
    mission_eval.add_argument("--engine", type=Path)
    return parser


def _speak(companion: Companion, text: str, player: AudioPlayer | None = None) -> float | bool:
    try:
        audio, metadata = companion.speech(text)
        if metadata.get("interrupted"):
            return False
        if player:
            duration = player.play(audio)
            return duration if duration else bool(audio)
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


def _auto_planner_interval(threat_level: str) -> float:
    return {"critical": 4.0, "high": 10.0}.get(threat_level, 60.0)


def _restart_auto_deadlines(now: float, threat_level: str) -> tuple[float, float]:
    """Restart periodic work after an event-driven planning/execution cycle."""
    return now + 3.0, now + _auto_planner_interval(threat_level)


def _companion_action_loop_enabled(*, mission_mode: bool, native_brain_available: bool) -> bool:
    """Use scripted companion control in missions and native control in skirmishes."""
    return mission_mode or not native_brain_available


def _match_started(
    previous_signature: tuple[str, int, int] | None,
    previous_tick: int,
    snapshot: GameSnapshot,
) -> bool:
    """Detect the first actionable snapshot of every distinct match."""
    signature = (snapshot.map_name, snapshot.map_width, snapshot.map_height)
    return (
        previous_signature is None
        or signature != previous_signature
        or snapshot.tick < previous_tick
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "serve":
        serve(args.host, args.port)
        return 0
    if args.command == "voice-check":
        status = microphone_status(check_device=not args.dependencies_only)
        print(json.dumps(status, ensure_ascii=False))
        return 0 if status["available"] else 2
    if args.command == "autoplay":
        from dataclasses import asdict
        from .autonomous import autoplay

        result = asyncio.run(autoplay(
            provider=args.provider,
            model=args.model,
            router_url=args.router_url,
            map_name=args.map_name,
            opponent=args.opponent,
            seed=args.seed,
            port=args.port,
            max_rounds=args.max_rounds,
            max_turns_per_round=args.max_turns,
            evidence_dir=args.evidence_dir,
            engine_executable=args.engine,
            reuse_engine=args.reuse_engine,
        ))
        print(json.dumps(asdict(result), indent=2))
        return 0 if result.won else 2
    if args.command == "learn":
        from .autonomous import learn_until_win

        result = asyncio.run(learn_until_win(
            provider=args.provider,
            model=args.model,
            router_url=args.router_url,
            map_name=args.map_name,
            opponent=args.opponent,
            seed=args.seed,
            port=args.port,
            max_attempts=args.attempts,
            max_rounds=args.max_rounds,
            max_turns_per_round=args.max_turns,
            evidence_root=args.evidence_root,
            engine_executable=args.engine,
        ))
        print(json.dumps(result, indent=2))
        return 0 if result["won"] else 2
    if args.command == "mission-eval":
        from .mission_eval import evaluate_all_missions

        result = evaluate_all_missions(
            evidence_root=args.evidence_root,
            engine_executable=args.engine,
            port=args.port,
            seed=args.seed,
            max_ticks=args.max_ticks,
            stall_ticks=args.stall_ticks,
            advance_ticks=args.advance_ticks,
            campaign=args.campaign,
            mission_names=tuple(args.missions),
        )
        print(json.dumps({key: value for key, value in result.items() if key != "results"}, indent=2))
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
        console_print(f"You: {transcript}")
        answer = companion.ask(transcript).text
        console_print(f"Companion: {answer}")
        _speak(companion, answer)
        return 0

    player = AudioPlayer() if args.speak else None
    control_server = create_companion_server("127.0.0.1", args.control_port, companion, player)
    worldgen_server = create_worldgen_server(
        "127.0.0.1",
        args.worldgen_port,
        args.mission_output,
        args.mission_install,
        f"http://127.0.0.1:{args.control_port}",
    )
    for name, server in (("control", control_server), ("worldgen", worldgen_server)):
        threading.Thread(
            target=server.serve_forever,
            name=f"OpenRA-AI-{name}-server",
            daemon=True,
        ).start()
    print("Native AI settings and diagnostics are ready in OpenRA.")
    print("Native Earth Mission Studio is ready in OpenRA World Tools.")
    with OpenRABridge(args.bridge) as bridge:
        from .interactive_agent import InteractiveMCPPlanner

        planner = InteractiveMCPPlanner(args.bridge)
        companion.set_action_planner(planner.plan)
        companion.set_action_executor(bridge.execute_actions)
        companion.set_snapshot_provider(bridge.observe)
        companion.set_frame_provider(bridge.capture_frame)
        def publish_status(state: str, message: str) -> None:
            bridge.update_companion_status(
                state,
                message,
                enabled=companion.enabled,
                muted=companion.muted,
            )

        def switch_native_strategy(profile: str) -> bool:
            name = strategy_contract(companion.native_strategy)["name"].upper()
            state = f"auto-active:{profile}" if companion.auto_act_enabled else f"ready:{profile}"
            mission = companion.latest_snapshot is not None and companion.latest_snapshot.mission_mode
            message = (
                "AUTO ASSISTANT ON  •  SCRIPTED MISSION BRAIN"
                if companion.auto_act_enabled and mission
                else
                f"AUTO ASSISTANT ON  •  {name}  •  {profile.upper()} NATIVE BRAIN"
                if companion.auto_act_enabled
                else "AI READY  •  HOLD ASK KEY TO SPEAK OR SET STRATEGY"
            )
            return bridge.update_companion_status(
                state,
                message,
                enabled=companion.enabled,
                muted=companion.muted,
            )

        control_server.status_publisher = publish_status
        companion.set_strategy_controller(switch_native_strategy)
        publish_status(*companion.idle_status())
        director = StrategyDirector(companion.router)

        hotkeys = (
            VoiceHotkeys(companion, player, lambda text: _speak(companion, text, player), publish_status)
            if args.voice_hotkeys and player
            else None
        )
        if hotkeys:
            # OpenRA owns the remappable bindings and calls the local voice endpoints.
            hotkeys.start(global_listener=False)
            control_server.voice_controller = hotkeys
        print("Watching OpenRA. Press Ctrl+C to stop.")
        waiting_reported = False
        capabilities_announced = False
        insight_expires_at = 0.0
        last_threat_signature: tuple[int, str, str] | None = None
        last_auto_act_enabled = companion.auto_act_enabled
        auto_routine_due_at = 0.0
        auto_planner_due_at = 0.0
        last_auto_message_at = -1_000_000.0
        strategy_review_due_at = 0.0
        previous_match_signature: tuple[str, int, int] | None = None
        previous_match_tick = -1
        try:
            while True:
                lifecycle_pid = args.parent_pid or args.game_pid
                if not _pid_alive(lifecycle_pid):
                    owner = "launcher" if args.parent_pid else "OpenRA"
                    print(f"{owner} exited; stopping companion.")
                    break
                try:
                    snapshot = bridge.observe()
                    reconnected = waiting_reported
                    if waiting_reported:
                        print("Connected to the live match.")
                        waiting_reported = False
                    match_started = _match_started(
                        previous_match_signature,
                        previous_match_tick,
                        snapshot,
                    )
                    previous_match_signature = (snapshot.map_name, snapshot.map_width, snapshot.map_height)
                    previous_match_tick = snapshot.tick
                    if not capabilities_announced:
                        publish_status(
                            "capabilities",
                            "AI  •  MCP TOOLSET ONLINE: 26 GAME TOOLS  •  ASK FOR A SUGGESTION OR ACTION",
                        )
                        capabilities_announced = True
                        time.sleep(0.15)
                    if match_started or reconnected:
                        # The pre-match AUTO status cannot reach a bridge that does not exist yet.
                        # Resend it on the first live snapshot so native control starts immediately,
                        # without waiting for an insight, strategy-model call, or periodic timer.
                        publish_status(*companion.idle_status(snapshot))
                        auto_routine_due_at = 0.0
                        auto_planner_due_at = 0.0
                    if match_started:
                        strategy_review_due_at = 0.0
                except RuntimeError:
                    if not waiting_reported:
                        print("Waiting for a match with the companion bridge enabled...")
                        waiting_reported = True
                    time.sleep(max(0.25, args.interval))
                    continue
                response = companion.observe(snapshot)
                threat = companion.current_threat
                threat_signature = (threat.score, threat.level, threat.reason)
                if threat_signature != last_threat_signature:
                    bridge.update_threat_status(threat.score, threat.level, threat.reason)
                    last_threat_signature = threat_signature
                now = time.monotonic()
                user_priority = companion.user_turn_active or bool(hotkeys and hotkeys.active.is_set())
                if user_priority:
                    # Keep the freshest event queued until the player's answer is complete.
                    response = None
                    event_context = None
                else:
                    event_context = companion.take_event_context()
                if match_started and event_context is None:
                    event_context = {
                        "type": "match_started",
                        "tick": snapshot.tick,
                        "fact": "The first live battlefield snapshot is ready.",
                        "importance": "important",
                        "threat": threat.as_dict(),
                        "battlefield": snapshot.action_context(),
                        "planner_instruction": "Begin the opening immediately; do not wait for another event or interval.",
                    }
                scheduled_planner_due_at = auto_planner_due_at
                if companion.auto_act_enabled != last_auto_act_enabled:
                    last_auto_act_enabled = companion.auto_act_enabled
                    auto_routine_due_at = 0.0
                    auto_planner_due_at = now + 2.0
                auto_response = None
                voice_busy = user_priority
                strategic_event = bool(event_context) and (
                    event_context["type"] in {
                        "enemy_spotted",
                        "structure_spotted",
                        "own_building_destroyed",
                        "enemy_building_destroyed",
                        "no_harvester",
                    }
                    or event_context["threat"]["level"] in {"high", "critical"}
                )
                if (
                    companion.native_brain_available
                    and companion.auto_act_enabled
                    and companion.native_strategy == "adaptive"
                    and not snapshot.mission_mode
                    and not voice_busy
                    and not snapshot.done
                    and now >= strategy_review_due_at
                    and (strategic_event or strategy_review_due_at <= 0)
                ):
                    publish_status("thinking", "AI STRATEGY DIRECTOR  •  REVIEWING NATIVE DOCTRINE")
                    decision = director.choose(snapshot, threat, companion.native_profile, event_context)
                    chosen = str(decision["profile"])
                    changed = chosen != companion.native_profile and companion.apply_adaptive_profile(chosen)
                    strategy_review_due_at = now + (60.0 if threat.heated else 180.0)
                    if changed:
                        name = strategy_contract(chosen)["name"]
                        response = CompanionResponse(
                            f"Strategy shift: {name}. {decision['reason']}",
                            "strategy-director",
                            metadata={"strategy": decision, "native_active": True},
                        )
                        last_auto_message_at = now
                    else:
                        publish_status(*companion.idle_status())

                if (
                    companion.auto_act_enabled
                    and companion.enabled
                    and _companion_action_loop_enabled(
                        mission_mode=snapshot.mission_mode,
                        native_brain_available=companion.native_brain_available,
                    )
                    and not voice_busy
                    and not snapshot.done
                ):
                    planner_event = bool(event_context) and (
                        event_context["type"] in {"enemy_spotted", "structure_spotted"}
                        or event_context["threat"]["level"] in {"high", "critical"}
                    )
                    if event_context:
                        # Priority events preempt both calm intervals. Do not let an unrelated,
                        # older AUTO proposal consume this event cycle.
                        auto_routine_due_at = now
                        auto_planner_due_at = now
                        pending = companion.pending_action()
                        expected_instruction = f"contextual:{event_context['type']}"
                        if pending is not None and pending.get("instruction") != expected_instruction:
                            companion.cancel_action()
                    if companion.pending_action() is not None:
                        auto_response = companion.auto_act_once(event_context)
                        auto_routine_due_at = now + 3.0
                        if auto_planner_due_at <= 0:
                            auto_planner_due_at = now + 12.0
                    elif now >= auto_routine_due_at and not planner_event:
                        routine = companion.propose_routine_action()
                        auto_routine_due_at = now + 3.0
                        if routine is not None:
                            auto_response = companion.auto_act_once(event_context)
                            if auto_planner_due_at <= 0:
                                auto_planner_due_at = now + 12.0
                    if auto_response is None and now >= auto_planner_due_at:
                        publish_status("thinking", "AUTO COMMANDER  •  PLANNING WITH 26 GAME TOOLS")
                        auto_response = companion.auto_act_once(event_context)
                        auto_planner_due_at = now + _auto_planner_interval(threat.level)
                    if event_context:
                        auto_routine_due_at, next_planner_due_at = _restart_auto_deadlines(now, threat.level)
                        if event_context["type"] == "storage_pressure":
                            auto_planner_due_at = (
                                scheduled_planner_due_at
                                if scheduled_planner_due_at > now
                                else now + 3.0
                            )
                        else:
                            auto_planner_due_at = next_planner_due_at
                    if auto_response is not None:
                        instruction = str(auto_response.metadata.get("action", {}).get("instruction", ""))
                        user_requested = bool(instruction) and (
                            not instruction.startswith("contextual:")
                            and not instruction.startswith("Autonomous commander mode")
                        )
                        if (
                            threat.heated
                            or user_requested
                            or response is not None
                            or now - last_auto_message_at >= 60.0
                        ):
                            response = auto_response
                            last_auto_message_at = now
                # Recheck at publication time: a question may have started while an
                # event model call was finishing in this loop iteration.
                if companion.user_turn_active or bool(hotkeys and hotkeys.active.is_set()):
                    response = None
                if response and response.metadata.get("clear"):
                    publish_status(*companion.idle_status())
                    insight_expires_at = 0.0
                elif response and response.text:
                    response_key = response.insight.key if response.insight else response.source
                    print(f"[{response_key}] {response.text}")
                    speak = bool(player and companion.should_speak(response.insight))
                    importance = response.insight.importance if response.insight else "routine"
                    default_state = f"speaking-{importance}" if speak else importance
                    publish_status(
                        response_hud_state(response, default_state),
                        f"AI  •  {response.text}",
                    )
                    playback = _speak(companion, response.text, player) if speak else None
                    insight_expires_at = time.monotonic() + playback_hold_seconds(playback, 8.0)
                elif insight_expires_at and time.monotonic() >= insight_expires_at:
                    if not hotkeys or not hotkeys.active.is_set():
                        if companion.pending_action() is not None:
                            insight_expires_at = time.monotonic() + 1
                        else:
                            publish_status(*companion.idle_status())
                            insight_expires_at = 0.0
                time.sleep(max(0.1, args.interval))
        except KeyboardInterrupt:
            companion.interrupt()
        finally:
            companion.set_action_planner(None)
            companion.set_strategy_controller(None)
            companion.set_action_executor(None)
            companion.set_snapshot_provider(None)
            companion.set_frame_provider(None)
            if hotkeys:
                control_server.voice_controller = None
                hotkeys.stop()
            elif player:
                player.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
