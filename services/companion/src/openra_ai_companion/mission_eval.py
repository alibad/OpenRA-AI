from __future__ import annotations

import json
import os
import re
import shutil
import time
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .autonomous import EngineProcess, _default_engine, _workspace_root
from .bridge import OpenRABridge
from .game_runtime import GameRuntime
from .models import ActionCommand, GameSnapshot
from .strategy import mission_plan


@dataclass(frozen=True)
class MissionSpec:
    campaign: str
    map_name: str
    request_name: str
    player_slot: str
    title: str
    package_path: str
    available: bool
    availability_reason: str = ""


@dataclass(frozen=True)
class MissionEvalResult:
    campaign: str
    map_name: str
    title: str
    player_slot: str
    seed: int
    status: str
    result: str
    tick: int
    wall_seconds: float
    decisions: int
    commands: int
    initial_phase: str
    final_phase: str
    briefing: str
    objectives: tuple[dict[str, Any], ...]
    failure_reason: str
    evidence_dir: str

    @property
    def won(self) -> bool:
        return self.status == "win"


def _read_map_yaml(path: Path) -> str:
    if path.is_dir():
        return (path / "map.yaml").read_text(encoding="utf-8-sig")
    with zipfile.ZipFile(path) as package:
        return package.read("map.yaml").decode("utf-8-sig")


def _map_metadata(text: str) -> tuple[str, str]:
    title_match = re.search(r"(?m)^Title:\s*(.+?)\s*$", text)
    title = title_match.group(1).strip() if title_match else ""

    players: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_players = False
    for line in text.splitlines():
        if line == "Players:":
            in_players = True
            continue
        if in_players and line and not line.startswith("\t"):
            break
        if not in_players:
            continue
        player_match = re.match(r"^\tPlayerReference@([^:]+):", line)
        if player_match:
            current = {
                "slot": player_match.group(1),
                "name": player_match.group(1),
                "playable": False,
                "required": False,
            }
            players.append(current)
            continue
        if current is None:
            continue
        property_match = re.match(r"^\t\t(Name|Playable|Required):\s*(.+?)\s*$", line)
        if property_match:
            key = property_match.group(1).lower()
            value = property_match.group(2).strip()
            current[key] = value if key == "name" else value.lower() == "true"

    playable = [player for player in players if player["playable"]]
    required = [player for player in playable if player["required"]]
    slot = str((required or playable or [{"name": ""}])[0]["name"])
    return title, slot


def _mission_entries(path: Path) -> list[tuple[str, str]]:
    campaign = ""
    entries: list[tuple[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        if not raw_line.strip():
            continue
        if not raw_line.startswith(("\t", " ")) and raw_line.rstrip().endswith(":"):
            campaign = raw_line.rstrip()[:-1]
            continue
        name = raw_line.strip()
        if campaign and name and not name.startswith("#"):
            entries.append((campaign, name))
    return entries


def inventory_missions(root: Path | None = None) -> list[MissionSpec]:
    root = root or _workspace_root()
    maps_dir = root / "engine" / "openra" / "mods" / "ra" / "maps"
    generated_dir = root / "generated" / "missions"
    manifest = root / "engine" / "openra" / "mods" / "ra" / "missions.yaml"
    specs: list[MissionSpec] = []
    for campaign, map_name in _mission_entries(manifest):
        system_package = maps_dir / map_name
        generated_package = generated_dir / f"{map_name}.oramap"
        package = system_package if (system_package / "map.yaml").is_file() else generated_package
        available = package.is_dir() or package.is_file()
        title = ""
        slot = ""
        reason = ""
        request_name = map_name
        if available:
            try:
                title, slot = _map_metadata(_read_map_yaml(package))
                if package.suffix.lower() == ".oramap":
                    request_name = package.name
                if not slot:
                    available = False
                    reason = "map has no playable player slot"
            except (OSError, KeyError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
                available = False
                reason = f"map package could not be read: {exc}"
        else:
            reason = "map package is not present"
        specs.append(MissionSpec(
            campaign=campaign,
            map_name=map_name,
            request_name=request_name,
            player_slot=slot,
            title=title or map_name,
            package_path=str(package),
            available=available,
            availability_reason=reason,
        ))
    return specs


def _support_maps_dir() -> Path | None:
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "OpenRA" / "maps" / "ra" / "{DEV_VERSION}"
    return None


def _install_generated_packages(specs: Iterable[MissionSpec]) -> list[Path]:
    """Expose generated campaign packages to the dev engine, returning files to remove."""
    destination = _support_maps_dir()
    if destination is None:
        return []
    created: list[Path] = []
    for spec in specs:
        source = Path(spec.package_path)
        if source.suffix.lower() != ".oramap" or not source.is_file():
            continue
        target = destination / source.name
        if target.exists():
            continue
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        created.append(target)
    return created


def _objective_signature(snapshot: GameSnapshot) -> tuple[tuple[int, str], ...]:
    return tuple((objective.objective_id, objective.state) for objective in snapshot.objectives)


def _objective_summary(snapshot: GameSnapshot) -> tuple[dict[str, Any], ...]:
    return tuple(objective.as_dict() for objective in snapshot.objectives)


def _wait_for_session(bridge: OpenRABridge, timeout_seconds: float = 45.0) -> GameSnapshot:
    deadline = time.monotonic() + timeout_seconds
    last_error = "session did not become ready"
    while time.monotonic() < deadline:
        try:
            return bridge.fast_advance(1, check_events_every=0, enabled_interrupts=())
        except RuntimeError as exc:
            last_error = str(exc)
            time.sleep(0.1)
    raise RuntimeError(last_error)


def _append_jsonl(path: Path, event: str, **payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time": time.time(), "event": event, **payload}, separators=(",", ":")) + "\n")


def _result_status(snapshot: GameSnapshot) -> str:
    result = snapshot.result.strip().lower()
    if result in {"win", "won", "victory"}:
        return "win"
    if result in {"lose", "loss", "lost", "defeat"}:
        return "loss"
    return "finished"


def evaluate_mission(
    spec: MissionSpec,
    *,
    address: str,
    seed: int,
    evidence_dir: Path,
    max_ticks: int = 30_000,
    stall_ticks: int = 1_000,
    advance_ticks: int = 125,
) -> MissionEvalResult:
    started = time.monotonic()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    events_path = evidence_dir / "tool-events.jsonl"
    observations_path = evidence_dir / "observations.jsonl"
    if not spec.available:
        return MissionEvalResult(
            campaign=spec.campaign,
            map_name=spec.map_name,
            title=spec.title,
            player_slot=spec.player_slot,
            seed=seed,
            status="unavailable",
            result="",
            tick=0,
            wall_seconds=round(time.monotonic() - started, 3),
            decisions=0,
            commands=0,
            initial_phase="",
            final_phase="",
            briefing="",
            objectives=(),
            failure_reason=spec.availability_reason,
            evidence_dir=str(evidence_dir),
        )

    session_id = ""
    bridge = OpenRABridge(address, timeout=2.0)
    runtime: GameRuntime | None = None
    snapshot = GameSnapshot(tick=0)
    status = "init_error"
    failure_reason = ""
    decision_count = 0
    command_count = 0
    initial_phase = ""
    final_phase = ""
    last_plan_signature = ""
    no_command_since = 0
    last_objectives: tuple[tuple[int, str], ...] = ()
    repeated_errors: Counter[str] = Counter()
    try:
        session_id = bridge.create_session(spec.request_name, f"{spec.player_slot}:rl-agent", seed)
        snapshot = _wait_for_session(bridge)
        if not snapshot.mission_mode:
            raise RuntimeError("the selected map did not expose mission briefing/objectives")

        # Some expansion missions contain hundreds of scripted actors and can
        # legitimately take longer than the interactive 15-second RPC floor to
        # simulate a 125-tick evidence interval on a cold map.
        runtime = GameRuntime(address, session_id, evidence_log=events_path, timeout=60.0)
        snapshot = runtime.observe()
        _append_jsonl(observations_path, "observation", phase="mission-start", state=snapshot.action_context())
        runtime.capture_tactical_evidence("mission-start", force=True)
        last_objectives = _objective_signature(snapshot)
        no_command_since = snapshot.tick

        while not snapshot.done and snapshot.tick < max_ticks:
            plan = mission_plan(snapshot)
            final_phase = str(plan.get("phase", ""))
            if not initial_phase:
                initial_phase = final_phase
            raw_commands = plan.get("recommended_commands") or []
            plan_signature = json.dumps(
                {
                    "phase": final_phase,
                    "commands": raw_commands,
                    "objectives": _objective_signature(snapshot),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            if plan_signature != last_plan_signature:
                next_step = str(plan.get("next_step") or "Re-evaluate the live mission objectives.")
                runtime.log_decision(
                    next_step[:500],
                    (
                        f"Mission phase {final_phase or 'unknown'}; "
                        f"{len([o for o in snapshot.objectives if o.state == 'incomplete'])} incomplete objectives."
                    )[:500],
                    "Advance the live objective without sacrificing required mission units."[:500],
                )
                decision_count += 1
                last_plan_signature = plan_signature

            if raw_commands:
                try:
                    commands = tuple(ActionCommand.from_dict(dict(command)) for command in raw_commands)
                    runtime.issue(commands)
                    command_count += len(commands)
                    no_command_since = snapshot.tick
                except (TypeError, ValueError, RuntimeError) as exc:
                    error = f"{final_phase}: {exc}"
                    repeated_errors[error] += 1
                    _append_jsonl(events_path, "command_error", tick=snapshot.tick, phase=final_phase, error=str(exc))
                    if repeated_errors[error] >= 3:
                        status = "action_error"
                        failure_reason = error
                        break

            remaining = max_ticks - snapshot.tick
            if remaining <= 0:
                break
            runtime.advance(min(max(1, advance_ticks), remaining, 1_500))
            snapshot = runtime.observe()
            _append_jsonl(observations_path, "observation", phase=final_phase, state=snapshot.action_context())
            runtime.capture_tactical_evidence("periodic")

            objectives = _objective_signature(snapshot)
            if objectives != last_objectives:
                no_command_since = snapshot.tick
                last_objectives = objectives

            waiting_for_order = final_phase == "mission-order-in-progress"
            if not raw_commands and not waiting_for_order and snapshot.tick - no_command_since >= stall_ticks:
                status = "unsupported"
                failure_reason = (
                    f"No executable action for {snapshot.tick - no_command_since} ticks "
                    f"during phase '{final_phase or 'unknown'}'."
                )
                break

        if snapshot.done:
            status = _result_status(snapshot)
        elif status == "init_error":
            status = "timeout"
            failure_reason = f"Mission did not finish within the {max_ticks}-tick evaluation horizon."
    except Exception as exc:  # A corpus run must record one broken map and continue.
        failure_reason = str(exc)
        if "DEADLINE_EXCEEDED" in failure_reason:
            status = "engine_timeout"
        elif snapshot.tick > 0:
            status = "engine_error"
        _append_jsonl(events_path, "evaluation_error", error=failure_reason)
    finally:
        if runtime is not None:
            try:
                snapshot = runtime.observe()
                _append_jsonl(observations_path, "observation", phase="mission-end", state=snapshot.action_context())
                runtime.capture_tactical_evidence("mission-end", force=True)
                # Campaign victory scripts can transition the world while a
                # FastAdvance RPC is still waiting for its requested tick count.
                # The authoritative terminal observation wins over that transport
                # timeout; otherwise a proven victory is mislabeled as an engine
                # failure in the corpus report.
                if snapshot.done or snapshot.result.strip():
                    status = _result_status(snapshot)
                    failure_reason = ""
            except Exception:
                pass
            runtime.close()
        if session_id:
            try:
                bridge.destroy_session(session_id)
            except Exception as exc:
                _append_jsonl(events_path, "cleanup_error", error=str(exc))
        bridge.close()

    result = MissionEvalResult(
        campaign=spec.campaign,
        map_name=spec.map_name,
        title=spec.title,
        player_slot=spec.player_slot,
        seed=seed,
        status=status,
        result=snapshot.result,
        tick=snapshot.tick,
        wall_seconds=round(time.monotonic() - started, 3),
        decisions=decision_count,
        commands=command_count,
        initial_phase=initial_phase,
        final_phase=final_phase,
        briefing=snapshot.mission_briefing,
        objectives=_objective_summary(snapshot),
        failure_reason=failure_reason,
        evidence_dir=str(evidence_dir),
    )
    (evidence_dir / "result.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def _report_markdown(results: list[MissionEvalResult], generated_at: str) -> str:
    counts = Counter(result.status for result in results)
    actionful = sum(result.commands > 0 for result in results)
    frames = sum(1 for result in results for _ in (Path(result.evidence_dir) / "frames").glob("*.png"))
    capability_patterns = {
        "Combat and target selection": r"\b(destroy|defeat|eliminate|kill|raze|gas)\b",
        "Escort, rescue, and extraction": r"\b(escort|evacuate|rescue|extraction|convoy|bring|save)\b",
        "Capture, infiltrate, and sabotage": r"\b(capture|infiltrate|sabotage|engineer|explosive|charge|cut power|offline|low power|repair)\b",
        "Defense and required-unit preservation": r"\b(defend|protect|hold|survive|keep|withstand|fortify|must not)\b",
        "Exploration and trigger navigation": r"\b(find|locate|reach|secure|waystation|foothold)\b",
        "Base building and power state": r"\b(build|redeploy|power|naval yard)\b",
    }
    incomplete_text = [
        str(objective.get("description", "")).lower()
        for result in results
        for objective in result.objectives
        if str(objective.get("state", "")).lower() == "incomplete"
    ]
    gaps = {
        label: sum(bool(re.search(pattern, description)) for description in incomplete_text)
        for label, pattern in capability_patterns.items()
    }
    timeouts = [result.map_name for result in results if result.status == "engine_timeout"]
    lines = [
        "# OpenRA mission AI evaluation",
        "",
        f"Generated: {generated_at}",
        "",
        f"Missions evaluated: {len(results)}. " + ", ".join(f"{key}: {counts[key]}" for key in sorted(counts)),
        "",
        "## Baseline finding",
        "",
        f"The current mission brain won **{counts.get('win', 0)} of {len(results)}** missions. "
        f"It issued at least one action in **{actionful}** missions; the remaining missions stalled before producing an executable order. "
        f"The run preserved **{frames}** fog-respecting tactical frames plus per-decision and per-command JSONL evidence.",
        "",
        "## Highest-impact missing capabilities",
        "",
    ]
    lines.extend(f"- {label}: {count} unresolved objective references" for label, count in sorted(gaps.items(), key=lambda item: item[1], reverse=True))
    if timeouts:
        lines.extend([
            "",
            "## Engine simulation timeouts",
            "",
            "These maps loaded, but one headless fast-advance call did not complete before the RPC deadline: "
            + ", ".join(f"`{name}`" for name in timeouts)
            + ". They are engine-harness defects, not verified planner outcomes.",
        ])
    lines.extend([
        "",
        "## Mission matrix",
        "",
        "| Campaign | Mission | Status | Tick | AI actions | Final phase | Failure reason |",
        "|---|---|---:|---:|---:|---|---|",
    ])
    for result in results:
        reason = result.failure_reason.replace("|", "\\|").replace("\n", " ")
        phase = result.final_phase.replace("|", "\\|")
        lines.append(
            f"| {result.campaign} | {result.map_name} | {result.status} | {result.tick} | "
            f"{result.commands} | {phase} | {reason} |"
        )
    return "\n".join(lines) + "\n"


def evaluate_all_missions(
    *,
    evidence_root: Path | None = None,
    engine_executable: Path | None = None,
    port: int = 9997,
    seed: int = 20260811,
    max_ticks: int = 30_000,
    stall_ticks: int = 1_000,
    advance_ticks: int = 125,
    campaign: str = "",
    mission_names: tuple[str, ...] = (),
) -> dict[str, Any]:
    root = _workspace_root()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_root = evidence_root or root / "artifacts" / f"mission-eval-{timestamp}"
    evidence_root.mkdir(parents=True, exist_ok=True)
    specs = inventory_missions(root)
    if campaign:
        specs = [spec for spec in specs if campaign.lower() in spec.campaign.lower()]
    if mission_names:
        selected = {name.lower() for name in mission_names}
        specs = [spec for spec in specs if spec.map_name.lower() in selected]
    if not specs:
        raise ValueError("No missions matched the requested filters")

    (evidence_root / "inventory.json").write_text(
        json.dumps([asdict(spec) for spec in specs], indent=2),
        encoding="utf-8",
    )
    created_packages = _install_generated_packages(specs)
    engine_path = (engine_executable or _default_engine()).resolve()
    engine = EngineProcess(engine_path, root / "engine" / "openra", port, evidence_root / "engine")
    results: list[MissionEvalResult] = []
    try:
        engine.start()
        address = f"127.0.0.1:{port}"
        for index, spec in enumerate(specs, start=1):
            mission_dir = evidence_root / f"{index:02d}-{spec.map_name}"
            result = evaluate_mission(
                spec,
                address=address,
                seed=seed + index - 1,
                evidence_dir=mission_dir,
                max_ticks=max_ticks,
                stall_ticks=stall_ticks,
                advance_ticks=advance_ticks,
            )
            results.append(result)
            print(
                f"[{index:02d}/{len(specs):02d}] {spec.map_name}: {result.status} "
                f"at tick {result.tick} ({result.commands} actions)",
                flush=True,
            )
    finally:
        engine.stop()
        for path in created_packages:
            try:
                path.unlink()
            except OSError:
                pass

    generated_at = datetime.now(timezone.utc).isoformat()
    counts = Counter(result.status for result in results)
    summary = {
        "generated_at": generated_at,
        "seed": seed,
        "max_ticks": max_ticks,
        "stall_ticks": stall_ticks,
        "advance_ticks": advance_ticks,
        "missions": len(results),
        "counts": dict(sorted(counts.items())),
        "all_accounted_for": len(results) == len(specs),
        "results": [asdict(result) for result in results],
        "evidence_root": str(evidence_root),
    }
    (evidence_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (evidence_root / "report.md").write_text(_report_markdown(results, generated_at), encoding="utf-8")
    return summary
