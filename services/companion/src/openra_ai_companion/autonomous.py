from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agents import Agent, Runner
from agents.exceptions import MaxTurnsExceeded
from agents.mcp import MCPServerStdio

from .agent_models import (
    LOCAL_MODEL,
    LOCAL_PROVIDER,
    LOCAL_ROUTER_URL,
    agent_model_settings,
    create_agent_model,
)
from .bridge import OpenRABridge
from .controller import TacticalController
from .game_runtime import GameRuntime
from .learning import LearningStore
from .models import ActionCommand, GameSnapshot
from .strategy import SIEGE_UNITS, base_center, hybrid_force_plan, opening_scout_count, scout_targets


LOCAL_AUTOPLAY_MAX_TOKENS = 512


AGENT_INSTRUCTIONS = """You are the autonomous commander of one local single-player OpenRA match.
Your only objective is to win the match through the openra-game MCP tools. You are authorized to execute gameplay actions without confirmation.

Hard rules:
- Invoke MCP tools through the native tool interface. Never print or return literal `<tool_call>` markup.
- Use only facts and actor IDs returned by fog-respecting tools. Never infer hidden enemy state.
- If `mission_plan.active` is true, follow its briefing, live objective states, hazard rules, and recommended commands before every skirmish rule below. Preserve required heroes; use disguise, infiltration, and C4 only on listed legal targets; never route a spy through visible dog-detector zones.
- At the start of each decision round and before any major strategy change, call `log_decision` with the observed evidence and expected result.
- Never sell the construction yard or last production building unless it is necessary to survive.
- Never deploy, pack, or move the Construction Yard after the opening MCV has deployed.
- Never stall: each decision round must read battlefield state, take useful gameplay actions, and advance time.
- Keep each decision round efficient: use at most 12 MCP tool calls, batch actors that share an order, then return a progress note so the next round can re-plan from fresh state.
- Re-read battlefield after production, combat, discovery, or long advances. A production item at progress 1.0 must be placed if it is a building.
- Read `strategy_profile` from battlefield and follow its faction doctrine, map-scaled scout count, harvester target, opening, placement, and rally policy.
- Read and follow `force_plan` on every battlefield response. Train `next_production` instead of repeatedly choosing the first available type; it ports OpenRA's weighted production shares, queue rotation, specialist limits, and visible-enemy counter bias.
- Obey `force_plan.squad`: preserve its defense reserve, wait for the mixed-role attack threshold when the base is safe, and never feed newly produced units into battle individually.
- Read and obey `tactical_plan` on every battlefield response. Its spy/dog escapes, damaged-armor retreats, siege-threat warnings, live-vs-husk counts, formation anchors, and target priorities override generic movement.
- Use `tactical_plan.range_control` and exact weapon ranges to fight at the engagement edge, keep tanks cohesive, and stay outside hostile impact zones until counters are ready. Use `armor_assessment`, lure attackers through powered friendly defenses, and execute `air_response` immediately when aircraft appear.
- The deterministic controller already deploys the MCV and establishes two power plants, one barracks, one refinery, one war factory, two harvesters, scouts, and a base-defense reserve before your first turn. Do not repeat that opening unless battlefield shows an asset was actually lost.
- Do not add a second barracks, refinery, or war factory before producing the first combat vehicles; spend the established economy on scouting, counters, armor, and map control.
- When `storage_percent` exceeds 80, build and place exactly one silo only while below `storage_policy.maximum_silos`. At that limit, convert reserves into combat production and map control instead of adding passive storage. Re-read capacity after every placement.
- Omit coordinates for normal structure placement so the engine can optimize legal sites. It scores explored ore distance for refineries and reserves open production lanes for barracks and war factories.
- Set barracks and war-factory rally points in open staging space beyond their doors; never route produced units back through the base or across ore.
- Train the map-scaled opening quota of 2-4 Rifle Infantry, then send them with separate attack-move orders toward reachable hidden cells in different directions.
- The opening scouts are a finite quota, not a stream. Once they locate an enemy base, pull surviving scouts back or use them as vision; do not feed lone infantry into defenses.
- Maintain the map-scaled harvester target from `strategy_profile`. Build another refinery or train another harvester when income is weak.
- Prioritize a second harvester before mass production. Do not queue more than three infantry or two vehicles at once; long queues starve more important production.
- Produce a faction-appropriate mixed combat force. Correct any overrepresented unit type toward `force_plan` before adding more of it, keep the main force concentrated, and use attack-move toward known contacts.
- Adapt the screen to observed composition: against infantry-heavy contact, add anti-infantry units (Soviet Grenadiers/e2, Allied Rifle Infantry or Rangers) and stop overproducing anti-armor rockets; against vehicle-heavy contact, add anti-armor infantry and tanks. Keep fragile V2s behind that screen.
- Against expected infantry, increase anti-infantry weight only after contact confirms it; retain Rifle and Rocket Soldiers in the screen so the force is not helpless against armor or aircraft.
- If armor is unlocked but temporarily absent from `available_production` because resources are low, bank for it instead of spending the income on repeated cheap vehicles. Skip optional air tech until the first enemy production or economy structure is destroyed.
- Before committing the main force, gather at least two tanks and six infantry unless the base is under immediate threat.
- Explore until every enemy is found. Send fast scouts to `exploration_targets` first (largest hidden-cell components first), then use the lowest-percentage `exploration_sectors`; do not repeatedly revisit explored empty cells.
- When visible enemies have actor IDs, focus fire with attack. Repair important damaged buildings.
- Once enemy buildings are visible, prioritize destroying barracks/war factories, the construction yard, power, and refineries with the concentrated force. Do not let disposable infantry distract armor from the base.
- After the enemy Construction Yard is destroyed, surviving armor must press remembered/visible War Factories and Barracks so they cannot replace MCVs and APCs. Focus anti-tank infantry or a blocking defense, but do not grind indefinitely through low-value APCs and riflemen while enemy production remains active.
- A visible enemy MCV after its Construction Yard falls is the highest-priority mobile target: give every available tank/anti-armor unit a direct attack on the same MCV until it is destroyed. Do not split that focus across APCs, and do not allow the MCV to deploy a replacement Yard.
- Against a cluster of two or more static defenses, stage outside their range and assemble at least two protected siege units before probing. Keep a replacement siege unit queued. Focus every siege weapon on one visible defense actor at a time while infantry and armor screen outside Tesla/Flame/Pillbox/Turret range. Use attack-move only to reach the staging area and direct attack orders for the siege shots. A spotter should reveal the target and immediately withdraw; do not feed the screen or single siege units into the defense pocket.
- Continue until match_status or battlefield reports done=true and result=win. Never call or request surrender.
- If an assault is aborted while enemy production remains active, retreat the entire surviving force behind the base-side War Factory/Service Depot before rebuilding. A midpoint staging line is not safe because the enemy reinforcement stream will reach it first.

Red Alert IDs commonly include: mcv (deploys to fact), powr/apwr (power), proc (refinery), tent/barr (barracks), weap (war factory), harv (harvester), e1/e3 (infantry), jeep, 1tnk/2tnk/3tnk/4tnk (armor). Always prefer exact IDs in available_production. Avoid building IDs that end in `f`; they are fake/decoy structures and waste money.
Exact faction tech facts: for Soviets, `dome` unlocks V2 launchers and `fix` after `weap` unlocks `3tnk` Heavy Tanks. For Allies, `dome` unlocks `arty` and `fix` after `weap` unlocks `2tnk` Medium Tanks. `afld` unlocks aircraft only and never unlocks armor. Build `fix`, not `afld`, when the plan needs durable tanks.
Game time is 25 ticks per second. Use advances of 100-700 ticks while building or moving; event interrupts will stop early when attention is needed.
At the end of a decision round, return one terse progress note for the next round. Do not merely give advice—the tools must be used."""


_TEXT_TOOL_ALLOWLIST = frozenset({
    "battlefield", "match_status", "log_decision", "advance", "move", "attack_move", "attack", "stop",
    "harvest", "build", "train", "deploy", "place_building", "cancel_production", "repair", "sell",
    "set_rally_point", "guard", "set_stance", "enter_transport", "unload", "power_down", "set_primary",
    "disguise", "infiltrate", "demolish",
})


def _extract_text_tool_calls(output: str, limit: int = 4) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Recover tool calls that a small local model emitted as literal markup."""
    if "<tool_call" not in output.lower():
        return ()
    decoder = json.JSONDecoder()
    calls: list[tuple[str, dict[str, Any]]] = []
    cursor = 0
    while len(calls) < limit:
        start = output.find("{", cursor)
        if start < 0:
            break
        try:
            value, consumed = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        cursor = start + consumed
        if not isinstance(value, dict):
            continue
        name = str(value.get("name", "")).strip()
        arguments = value.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        if name in _TEXT_TOOL_ALLOWLIST and isinstance(arguments, dict):
            calls.append((name, arguments))
    return tuple(calls)


async def _recover_text_tool_calls(game_server: MCPServerStdio, output: str) -> list[dict[str, str]]:
    recovered: list[dict[str, str]] = []
    for name, arguments in _extract_text_tool_calls(output):
        try:
            result = await game_server.call_tool(name, arguments)
            status = "error" if bool(getattr(result, "isError", False)) else "executed"
        except Exception as exc:
            status = f"error:{type(exc).__name__}"
        recovered.append({"name": name, "status": status})
    return recovered


def _opponent_guidance(opponent: str) -> str:
    difficulty = opponent.strip().lower()
    if difficulty == "normal":
        return (
            "Normal/Medium commitment threshold: do not launch the main base assault before assembling at least "
            "four durable tanks, ten faction-appropriate screening infantry, and one protected siege unit. If two "
            "or more static defenses are observed, regroup until two siege units are ready. Queue replacement armor "
            "and siege before contact. Keep damaged armor alive and "
            "route it back to the Service Depot instead of trading it. After the Construction Yard falls, immediately "
            "drive the surviving group onto MCVs and production structures."
        )
    if difficulty in {"hard", "tough"}:
        return (
            "Hard commitment threshold: establish redundant economy/production and attack with at least six durable "
            "tanks, twelve screening infantry, and two protected siege units; preserve a defensive reserve."
        )
    return "Use the map-scaled force threshold from the strategy profile and exploit safe opportunities decisively."


def _game_child_environment() -> dict[str, str]:
    """Keep model/provider credentials out of the engine and gameplay tool processes."""
    sensitive_markers = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    return {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in sensitive_markers)
    }


@dataclass(frozen=True)
class AutoplayResult:
    won: bool
    result: str
    session_id: str
    tick: int
    rounds: int
    provider: str
    model: str
    map_name: str
    opponent: str
    seed: int
    state: dict[str, Any]
    snapshot: dict[str, Any]
    evidence_dir: str


class EngineProcess:
    def __init__(self, executable: Path, engine_dir: Path, port: int, log_dir: Path) -> None:
        self.executable = executable
        self.engine_dir = engine_dir
        self.port = port
        self.log_dir = log_dir
        self.process: subprocess.Popen[bytes] | None = None
        self._stdout = None
        self._stderr = None

    def start(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        support_dir = self.log_dir / "openra-support"
        support_dir.mkdir(parents=True, exist_ok=True)
        self._stdout = (self.log_dir / "engine.stdout.log").open("wb")
        self._stderr = (self.log_dir / "engine.stderr.log").open("wb")
        environment = _game_child_environment()
        environment["DOTNET_ROLL_FORWARD"] = "LatestMajor"
        arguments = [
            str(self.executable),
            "Engine.EngineDir=../.." if self.executable.parent.name == "win-x64" else "Engine.EngineDir=..",
            f"Engine.SupportDir={support_dir}",
            "Game.Mod=ra",
            "Game.Platform=Null",
            f"Launch.MultiSession={self.port}",
        ]
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW
        self.process = subprocess.Popen(
            arguments,
            cwd=self.engine_dir,
            env=environment,
            stdout=self._stdout,
            stderr=self._stderr,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"OpenRA headless engine exited with code {self.process.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.25):
                    return
            except OSError:
                time.sleep(0.25)
        raise RuntimeError(f"OpenRA headless engine did not open port {self.port}")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self._stdout, self._stderr):
            if stream is not None:
                stream.close()


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_engine() -> Path:
    root = _workspace_root() / "engine" / "openra" / "bin"
    packaged = root / "win-x64" / "OpenRA.exe"
    fallback = root / ("OpenRA.exe" if os.name == "nt" else "OpenRA")
    # Development builds are written directly to bin. Prefer them when they are
    # newer than the last self-contained package so gameplay/evaluation never
    # silently runs stale bridge code.
    if fallback.is_file() and (
        not packaged.is_file() or fallback.stat().st_mtime >= packaged.stat().st_mtime
    ):
        return fallback
    if packaged.is_file():
        return packaged
    if fallback.is_file():
        return fallback
    raise RuntimeError("A built OpenRA executable was not found under engine/openra/bin")


def _reuse_project_key() -> None:
    if os.environ.get("OPENAI_API_KEY"):
        return
    root = _workspace_root()
    for directory in (root, *root.parents):
        path = directory / ".env"
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "OPENAI_API_KEY":
                secret = value.strip().strip('"').strip("'")
                if secret:
                    os.environ["OPENAI_API_KEY"] = secret
                    return
        break
    raise RuntimeError("OPENAI_API_KEY is not available in the environment or project .env")


def _wait_for_session(bridge: OpenRABridge, attempts: int = 120) -> GameSnapshot:
    for attempt in range(attempts):
        try:
            return bridge.fast_advance(1, check_events_every=0, enabled_interrupts=())
        except RuntimeError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.5)
    raise RuntimeError("OpenRA session did not become ready")


def _kind(value: str) -> str:
    return value.lower().split(".", 1)[0]


def _bootstrap_opening(address: str, session_id: str, evidence_log: Path) -> dict[str, Any]:
    """Execute the universal economy opening without spending model turns."""
    runtime = GameRuntime(address, session_id, evidence_log=evidence_log)
    start_tick = 0
    steps = 0
    try:
        snapshot = runtime.observe()
        start_tick = snapshot.tick
        runtime.log_decision(
            "Execute the deterministic economy opening",
            "A fresh match always starts with one MCV and no functioning economy.",
            "Establish optimized power, infantry production, refinery income, reserve power, and vehicle production before strategic model control.",
        )
        targets = (
            ("power", frozenset({"powr", "apwr"}), 1),
            ("barracks", frozenset({"tent", "barr"}), 1),
            ("refinery", frozenset({"proc"}), 1),
            ("reserve power", frozenset({"powr", "apwr"}), 2),
            ("war factory", frozenset({"weap"}), 1),
        )

        for steps in range(1, 121):
            snapshot = runtime.observe()
            if snapshot.done or snapshot.tick - start_tick > 7_500:
                break

            mcvs = [unit for unit in snapshot.units if _kind(unit.kind) == "mcv"]
            if mcvs:
                runtime.issue((ActionCommand("deploy", actor_id=mcvs[0].actor_id),))
                runtime.advance(50)
                continue

            completed = next((
                item for item in snapshot.production
                if str(item.get("queue_type", "")).lower() == "building"
                and (
                    float(item.get("progress", 0)) >= 0.999
                    or int(item.get("remaining_ticks", 1)) <= 0
                )
            ), None)
            if completed is not None:
                item = str(completed.get("item", "")).strip().lower()
                if item:
                    runtime.issue((ActionCommand("place_building", item_type=item),))
                    runtime.advance(25)
                    continue

            building_kinds = [_kind(building.kind) for building in snapshot.buildings]
            queued_buildings = {
                _kind(str(item.get("item", "")))
                for item in snapshot.production
                if str(item.get("queue_type", "")).lower() == "building"
            }
            if queued_buildings:
                runtime.advance(200)
                continue

            missing = next((
                (label, kinds, count)
                for label, kinds, count in targets
                if sum(kind in kinds for kind in building_kinds) < count
            ), None)
            if missing is None:
                break

            label, kinds, _ = missing
            available = next((
                item for item in snapshot.available_production
                if _kind(item) in kinds
            ), None)
            if available:
                runtime.log_decision(
                    f"Queue opening {label}",
                    f"The required {label} is absent and {available} is currently available.",
                    f"Add the {label} through the deterministic placement optimizer.",
                )
                runtime.issue((ActionCommand("build", item_type=available, queued=True),))
                # Give the engine time to publish the new queue before the next
                # observation, which prevents duplicate opening structures.
                runtime.advance(50)
            else:
                runtime.advance(50)

        # The local model should begin strategic control with income, vision,
        # and enough defenders to survive the Beginner AI's first infantry wave.
        snapshot = runtime.observe()
        scout_quota = opening_scout_count(snapshot)
        available = {_kind(item): item for item in snapshot.available_production}
        opening_units: list[ActionCommand] = []
        rifle_count = sum(_kind(unit.kind) == "e1" for unit in snapshot.units)
        for _ in range(max(0, scout_quota - rifle_count)):
            if "e1" in available:
                opening_units.append(ActionCommand("train", item_type=available["e1"], queued=True))
        if snapshot.harvester_count < 2 and "harv" in available:
            opening_units.append(ActionCommand("train", item_type=available["harv"], queued=True))
        if opening_units:
            runtime.log_decision(
                "Train opening scouts and second harvester",
                f"The base has {rifle_count} scouts and {snapshot.harvester_count} harvester; the map calls for {scout_quota} scouts and at least two harvesters.",
                "Reveal separate map approaches while establishing resilient income.",
            )
            runtime.issue(tuple(opening_units), ticks=8)

        for _ in range(40):
            snapshot = runtime.observe()
            rifle_count = sum(_kind(unit.kind) == "e1" for unit in snapshot.units)
            if rifle_count >= scout_quota and snapshot.harvester_count >= 2:
                break
            runtime.advance(100)
            steps += 1

        snapshot = runtime.observe()
        scouts = [unit for unit in snapshot.units if _kind(unit.kind) == "e1"][:scout_quota]
        targets = scout_targets(snapshot, base_center(snapshot), len(scouts))
        if targets:
            runtime.log_decision(
                "Dispatch opening scouts in separate directions",
                f"{len(scouts)} rifle infantry are ready and reachable hidden approaches were calculated from the live map.",
                "Gain early warning without feeding the entire scout group down one route.",
            )
            runtime.issue(tuple(
                ActionCommand("attack_move", actor_id=scout.actor_id, target_x=target[0], target_y=target[1])
                for scout, target in zip(scouts, targets)
            ))
            steps += 1

        snapshot = runtime.observe()
        available = {_kind(item): item for item in snapshot.available_production}
        defenders: list[ActionCommand] = []
        if "e1" in available:
            defenders.extend(ActionCommand("train", item_type=available["e1"], queued=True) for _ in range(2))
        counter_kind = next((kind for kind in ("jeep", "ftrk", "1tnk") if kind in available), None)
        if counter_kind is not None:
            defenders.append(ActionCommand("train", item_type=available[counter_kind], queued=True))
        if defenders:
            runtime.log_decision(
                "Prepare the first base-defense reserve",
                "Opening scouts are leaving the base and an early infantry raid is expected.",
                "Keep two rifle defenders and a mobile anti-infantry counter near production and the refinery.",
            )
            runtime.issue(tuple(defenders), ticks=8)

        target_rifles = scout_quota + 2
        for _ in range(40):
            snapshot = runtime.observe()
            rifle_count = sum(_kind(unit.kind) == "e1" for unit in snapshot.units)
            counter_ready = counter_kind is None or any(_kind(unit.kind) == counter_kind for unit in snapshot.units)
            if rifle_count >= target_rifles and counter_ready:
                break
            runtime.advance(100)
            steps += 1

        snapshot = runtime.observe()
        return {
            "phase": "deterministic_opening",
            "steps": steps,
            "start_tick": start_tick,
            "tick": snapshot.tick,
            "done": snapshot.done,
            "result": snapshot.result,
            "economy": {
                "cash": snapshot.cash,
                "harvesters": snapshot.harvester_count,
                "power_balance": snapshot.power_provided - snapshot.power_drained,
            },
            "buildings": GameRuntime._display_type_counts(snapshot.buildings, buildings=True),
        }
    finally:
        runtime.close()


def _priority_production_cancellations(
    snapshot: GameSnapshot,
    *,
    target: str,
) -> tuple[ActionCommand, ...]:
    """Refund expendable queues when a critical tech/siege item is starved."""
    if snapshot.cash + snapshot.ore >= 600:
        return ()

    candidates: list[tuple[float, str]] = []
    for item in snapshot.production:
        raw_kind = str(item.get("item", "")).strip().lower()
        kind = _kind(raw_kind)
        queue_type = str(item.get("queue_type", "")).strip().lower()
        if not raw_kind or kind in {"harv", "dome"} or kind in SIEGE_UNITS:
            continue
        if target == "dome" and queue_type == "building":
            continue
        progress = float(item.get("progress", 0) or 0)
        candidates.append((progress, raw_kind))

    # Cancel unstarted items before sunk-cost active production. Three refunds
    # are enough to unblock a tech structure or siege unit without gutting the
    # whole defensive queue.
    candidates.sort(key=lambda item: (item[0] > 0, item[0], item[1]))
    return tuple(
        ActionCommand("cancel_production", item_type=item_type)
        for _, item_type in candidates[:3]
    )


def _native_autoplay_step(
    runtime: GameRuntime,
    snapshot: GameSnapshot,
    tactical_controller: TacticalController,
) -> dict[str, Any]:
    """Execute one bounded real-time/native decision before slow LLM strategy.

    The local model remains responsible for doctrine and adaptation. Placement,
    safety, reconnaissance, mixed production, and force concentration use the
    deterministic OpenRA-derived controllers so model latency cannot stall the
    match or split the army into disposable trickles.
    """
    # Synchronize the runtime's validation baseline with actors and production
    # created by the LLM/MCP process since the prior native step.
    snapshot = runtime.observe()
    if snapshot.done:
        return {"phase": "terminal", "tick": snapshot.tick}

    completed = next((
        item for item in snapshot.production
        if str(item.get("queue_type", "")).lower() == "building"
        and (
            float(item.get("progress", 0)) >= 0.999
            or int(item.get("remaining_ticks", 1)) <= 0
        )
    ), None)
    if completed is not None:
        item = str(completed.get("item", "")).strip().lower()
        if item:
            runtime.log_decision(
                f"Place completed {item}",
                "The construction queue is complete and waiting for placement.",
                "Resume the build queue immediately without waiting for the strategic model.",
            )
            result = runtime.issue((ActionCommand("place_building", item_type=item),), ticks=8)
            return {"phase": "placement", "item": item, "tick": result["tick"]}

    tactical = tactical_controller.decide(snapshot)
    if tactical is not None and tactical.priority >= 80:
        runtime.log_decision(tactical.summary, json.dumps(tactical.evidence, separators=(",", ":"))[:500], "Preserve the force before strategic planning.")
        result = runtime.issue(tactical.commands, ticks=8)
        return {"phase": "tactical", "decision": tactical.key, "orders": len(tactical.commands), "tick": result["tick"]}

    enemy_structures = (*snapshot.visible_enemy_buildings, *snapshot.remembered_enemy_buildings)
    siege_count = sum(_kind(unit.kind) in SIEGE_UNITS for unit in snapshot.units)
    queued_siege = sum(
        _kind(str(item.get("item", ""))) in SIEGE_UNITS
        for item in snapshot.production
    )
    if enemy_structures and siege_count + queued_siege < 2:
        available = {_kind(item): item for item in snapshot.available_production}
        siege_kind = next((kind for kind in ("ymlr", "v2rl", "arty") if kind in available), None)
        if siege_kind is not None and not queued_siege:
            runtime.log_decision(
                f"Produce protected siege ({siege_kind})",
                "An enemy base is known but fewer than two long-range siege units are ready or queued.",
                "Break static defenses from range before committing another infantry and armor wave.",
            )
            result = runtime.issue((ActionCommand("train", item_type=available[siege_kind], queued=True),), ticks=8)
            return {"phase": "siege-production", "item": siege_kind, "tick": result["tick"]}

        dome_queued = any(_kind(str(item.get("item", ""))) == "dome" for item in snapshot.production)
        dome_built = any(_kind(building.kind) == "dome" for building in snapshot.buildings)
        if not dome_built and not dome_queued and "dome" in available:
            runtime.log_decision(
                "Unlock long-range siege production",
                "An enemy base is known, no siege is ready, and the radar dome is available.",
                "Build the faction tech prerequisite for Artillery, V2, or the Yemen launcher.",
            )
            result = runtime.issue((ActionCommand("build", item_type=available["dome"], queued=True),), ticks=8)
            return {"phase": "siege-tech", "item": "dome", "tick": result["tick"]}

        priority_target = "dome" if dome_queued and not dome_built else "siege"
        cancellations = _priority_production_cancellations(snapshot, target=priority_target)
        if (dome_queued or queued_siege) and cancellations:
            runtime.log_decision(
                f"Fund priority {priority_target} production",
                "Critical production is queued but the shared resource pool is exhausted by expendable queues.",
                "Refund low-priority units so the strategy-unlocking item completes without a deadlock.",
            )
            result = runtime.issue(cancellations, ticks=8)
            return {
                "phase": "priority-funding",
                "target": priority_target,
                "cancelled": [command.item_type for command in cancellations],
                "tick": result["tick"],
            }

        if dome_queued or queued_siege:
            return {"phase": "siege-wait", "ready": siege_count, "queued": queued_siege, "tick": snapshot.tick}

    plan = hybrid_force_plan(snapshot, batch_size=2)
    for phase, commands, evidence in (
        ("assault", plan["assault"]["commands"], plan["assault"]),
        ("recon", plan["recon"]["commands"], plan["recon"]),
        ("production", plan["next_production"], {"types": plan["next_production_types"]}),
    ):
        if not commands:
            continue
        native_commands = tuple(ActionCommand.from_dict(command) for command in commands)
        runtime.log_decision(
            f"Native {phase} step",
            json.dumps(evidence, separators=(",", ":"))[:500],
            "Apply the OpenRA-derived bounded action batch, then let the strategic model reassess.",
        )
        result = runtime.issue(native_commands, ticks=8)
        return {"phase": phase, "orders": len(native_commands), "tick": result["tick"]}

    return {"phase": "observe", "tick": snapshot.tick}


async def autoplay(
    *,
    provider: str = LOCAL_PROVIDER,
    model: str = LOCAL_MODEL,
    router_url: str = LOCAL_ROUTER_URL,
    map_name: str = "singles.oramap",
    opponent: str = "beginner",
    seed: int = 20260810,
    port: int = 9997,
    max_rounds: int = 40,
    max_turns_per_round: int = 24,
    evidence_dir: Path | None = None,
    engine_executable: Path | None = None,
    reuse_engine: bool = False,
) -> AutoplayResult:
    provider = provider.strip().lower()
    if provider != LOCAL_PROVIDER:
        _reuse_project_key()
        os.environ.setdefault("OPENAI_AGENTS_DONT_LOG_MODEL_DATA", "1")
        os.environ.setdefault("OPENAI_AGENTS_DONT_LOG_TOOL_DATA", "1")
    model_runtime = create_agent_model(provider=provider, model=model, router_url=router_url)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    evidence_dir = (evidence_dir or (_workspace_root() / ".artifacts" / "autoplay" / stamp)).resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    tool_log = evidence_dir / "tool-events.jsonl"
    controller_log = evidence_dir / "agent-rounds.jsonl"

    engine: EngineProcess | None = None
    if not reuse_engine:
        executable = (engine_executable or _default_engine()).resolve()
        engine = EngineProcess(executable, _workspace_root() / "engine" / "openra", port, evidence_dir)
        engine.start()

    bridge = OpenRABridge(f"127.0.0.1:{port}", timeout=10)
    native_runtime: GameRuntime | None = None
    session_id = ""
    rounds = 0
    latest = GameSnapshot(tick=0)
    state: dict[str, Any] = {}
    previous_note = "Start the match decisively."
    learning_store = LearningStore()
    learned_context = learning_store.context(map_name, opponent)
    try:
        session_id = bridge.create_session(
            map_name,
            f"Multi0:rl-agent,Multi1:{opponent}",
            seed,
        )
        latest = _wait_for_session(bridge)

        bootstrap_record = _bootstrap_opening(f"127.0.0.1:{port}", session_id, tool_log)
        with controller_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(bootstrap_record, separators=(",", ":")) + "\n")
        print(json.dumps(bootstrap_record, separators=(",", ":")), flush=True)
        previous_note = (
            "Deterministic opening complete: the Construction Yard, two power plants, barracks, refinery, war factory, "
            "two harvesters, separate opening scouts, and a defensive reserve are already established. Do not rebuild "
            "the opening; use current production for counters, armor, exploration, and an eventual concentrated attack."
        )
        native_runtime = GameRuntime(f"127.0.0.1:{port}", session_id, evidence_log=tool_log)
        tactical_controller = TacticalController()
        latest = bridge.observe()
        if latest.done:
            state = bridge.state()

        mcp_params = {
            "command": sys.executable,
            "args": [
                "-m",
                "openra_ai_companion.game_mcp",
                "--bridge",
                f"127.0.0.1:{port}",
                "--session-id",
                session_id,
                "--evidence-log",
                str(tool_log),
            ],
            "cwd": str(_workspace_root()),
            "env": _game_child_environment(),
        }
        async with MCPServerStdio(
            mcp_params,
            cache_tools_list=True,
            name="openra-game",
            client_session_timeout_seconds=30,
            use_structured_content=True,
        ) as game_server:
            agent = Agent(
                name="OpenRA autonomous commander",
                model=model_runtime.model,
                instructions=(
                    AGENT_INSTRUCTIONS
                    + "\n\nOpponent-specific doctrine:\n"
                    + _opponent_guidance(opponent)
                    + "\n\nPersistent lessons from prior attempts on this map and difficulty:\n"
                    + learned_context
                    + "\nUse these as evidence-backed corrections, but always obey the current battlefield."
                ),
                mcp_servers=[game_server],
                model_settings=agent_model_settings(
                    local=model_runtime.local,
                    # local-coder has a 32K context. The MCP gameplay schemas
                    # consume most of it, so reserve a bounded output window
                    # with enough headroom for the complete prompt.
                    max_tokens=LOCAL_AUTOPLAY_MAX_TOKENS if model_runtime.local else 1800,
                    reasoning_effort="medium",
                ),
            )

            for rounds in range(1, max_rounds + 1):
                latest = bridge.observe()
                state = bridge.state()
                if latest.done:
                    break
                native_step: dict[str, Any]
                try:
                    native_step = _native_autoplay_step(native_runtime, latest, tactical_controller)
                except (RuntimeError, ValueError) as exc:
                    native_step = {"phase": "deferred", "error": str(exc)[:300], "tick": latest.tick}
                latest = bridge.observe()
                if latest.done:
                    break
                prompt = (
                    f"Decision round {rounds}/{max_rounds}. Previous commander note: {previous_note[:600]}\n"
                    f"The native controller just completed this bounded step: {json.dumps(native_step, separators=(',', ':'))}. "
                    "Do not duplicate it. Choose only the next strategic correction or advance to verify it.\n"
                    "Use MCP gameplay tools now. Make concrete progress, advance enough time to observe results, "
                    "and keep acting through immediate production/combat events. If the game is over, verify the result."
                )
                started = time.perf_counter()
                turn_budget_exhausted = False
                round_error = ""
                recovered_text_tools: list[dict[str, str]] = []
                try:
                    result = await Runner.run(
                        agent,
                        prompt,
                        max_turns=max_turns_per_round,
                        run_config=model_runtime.run_config,
                    )
                    previous_note = str(result.final_output or "No note returned")
                    recovered_text_tools = await _recover_text_tool_calls(game_server, previous_note)
                except MaxTurnsExceeded:
                    turn_budget_exhausted = True
                    previous_note = "The prior round used its tool budget; re-read battlefield state and continue the winning plan."
                except Exception as exc:
                    round_error = f"{type(exc).__name__}: {str(exc)[:300]}"
                    previous_note = "The prior model round failed transiently; re-read battlefield state and resume useful actions."
                latest = bridge.observe()
                state = bridge.state()
                record = {
                    "round": rounds,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "tick": latest.tick,
                    "done": latest.done,
                    "result": latest.result,
                    "turn_budget_exhausted": turn_budget_exhausted,
                    "error": round_error,
                    "native_step": native_step,
                    "recovered_text_tools": recovered_text_tools,
                    "note": previous_note[:1000],
                }
                with controller_log.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, separators=(",", ":")) + "\n")
                print(json.dumps(record, separators=(",", ":")), flush=True)
                if latest.done:
                    break

        latest = bridge.observe()
        state = bridge.state()
        result = AutoplayResult(
            won=latest.done and latest.result.lower() == "win",
            result=latest.result,
            session_id=session_id,
            tick=latest.tick,
            rounds=rounds,
            provider=provider,
            model=model,
            map_name=map_name,
            opponent=opponent,
            seed=seed,
            state=state,
            snapshot=latest.compact(),
            evidence_dir=str(evidence_dir),
        )
        outcome_payload = asdict(result)
        outcome_path = evidence_dir / "outcome.json"
        outcome_path.write_text(json.dumps(outcome_payload, indent=2) + "\n", encoding="utf-8")
        learning_record = learning_store.record(evidence_dir, outcome_payload)
        outcome_payload["learning_review"] = {
            "attempt_id": learning_record["attempt_id"],
            "strengths": learning_record["assessment"]["strengths"],
            "improvements": learning_record["assessment"]["improvements"],
        }
        outcome_path.write_text(json.dumps(outcome_payload, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        if native_runtime is not None:
            native_runtime.close()
        if session_id:
            try:
                bridge.destroy_session(session_id)
            except RuntimeError:
                pass
        bridge.close()
        if engine is not None:
            engine.stop()
        await model_runtime.close()


def run_autoplay(**kwargs: Any) -> AutoplayResult:
    return asyncio.run(autoplay(**kwargs))


async def learn_until_win(
    *,
    provider: str = LOCAL_PROVIDER,
    model: str = LOCAL_MODEL,
    router_url: str = LOCAL_ROUTER_URL,
    map_name: str = "singles.oramap",
    opponent: str = "beginner",
    seed: int = 20260810,
    port: int = 9997,
    max_attempts: int = 5,
    max_rounds: int = 40,
    max_turns_per_round: int = 24,
    evidence_root: Path | None = None,
    engine_executable: Path | None = None,
) -> dict[str, Any]:
    if not 1 <= max_attempts <= 20:
        raise ValueError("max_attempts must be between 1 and 20")
    root = (evidence_root or (_workspace_root() / ".artifacts" / "autoplay" / "learning-runs")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    attempts: list[dict[str, Any]] = []
    for index in range(max_attempts):
        attempt_seed = seed + index
        attempt_dir = root / f"{time.strftime('%Y%m%d-%H%M%S')}-attempt-{index + 1}-seed-{attempt_seed}"
        result = await autoplay(
            provider=provider,
            model=model,
            router_url=router_url,
            map_name=map_name,
            opponent=opponent,
            seed=attempt_seed,
            port=port,
            max_rounds=max_rounds,
            max_turns_per_round=max_turns_per_round,
            evidence_dir=attempt_dir,
            engine_executable=engine_executable,
        )
        attempt = asdict(result)
        attempts.append(attempt)
        if result.won:
            break
    return {
        "won": bool(attempts and attempts[-1]["won"]),
        "opponent": opponent,
        "map_name": map_name,
        "attempts": attempts,
        "learning": LearningStore().dashboard(),
    }
