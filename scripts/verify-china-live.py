"""Run live multi-direction China movement/combat verification and capture evidence."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from openra_ai_companion.autonomous import EngineProcess
from openra_ai_companion.bridge import OpenRABridge
from openra_ai_companion.models import ActionCommand, GameSnapshot


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / ".artifacts" / "china-faction" / "live"
MISSION_SOURCE = ROOT / "missions" / "china-faction" / "haitan-network"


def wait_for_session(bridge: OpenRABridge, seconds: float = 45) -> GameSnapshot:
    deadline = time.monotonic() + seconds
    last_error = "session was not ready"
    while time.monotonic() < deadline:
        try:
            return bridge.fast_advance(1, check_events_every=0, enabled_interrupts=())
        except RuntimeError as exc:
            last_error = str(exc)
            time.sleep(0.1)
    raise RuntimeError(last_error)


def compact(snapshot: GameSnapshot) -> dict[str, object]:
    return {
        "tick": snapshot.tick,
        "map": snapshot.map_name,
        "cash": snapshot.cash,
        "ore": snapshot.ore,
        "power": snapshot.power_provided - snapshot.power_drained,
        "army_value": snapshot.army_value,
        "orders": snapshot.order_count,
        "kills": snapshot.units_killed,
        "losses": snapshot.units_lost,
        "explored_percent": round(snapshot.explored_percent, 2),
        "done": snapshot.done,
        "result": snapshot.result,
        "objectives": [objective.as_dict() for objective in snapshot.objectives],
        "units": [
            {
                "id": unit.actor_id,
                "type": unit.kind,
                "cell": [unit.cell_x, unit.cell_y],
                "hp": round(unit.hp_percent, 3),
                "activity": unit.current_activity,
                "facing": unit.facing,
                "ammo": unit.ammo,
                "weapon": unit.weapon,
                "target": unit.current_target_actor_id,
            }
            for unit in snapshot.units
        ],
        "visible_enemies": [
            {"id": unit.actor_id, "type": unit.kind, "cell": [unit.cell_x, unit.cell_y], "hp": round(unit.hp_percent, 3)}
            for unit in snapshot.visible_enemies
        ],
        "visible_enemy_buildings": [
            {"id": unit.actor_id, "type": unit.kind, "cell": [unit.cell_x, unit.cell_y], "hp": round(unit.hp_percent, 3)}
            for unit in snapshot.visible_enemy_buildings
        ],
    }


def actors(snapshot: GameSnapshot, kind: str) -> list:
    return [unit for unit in snapshot.units if unit.kind.lower() == kind]


def render_telemetry_frame(snapshot: GameSnapshot, path: Path) -> dict[str, object]:
    """Render a screenshot-like tactical frame from live engine observation."""
    preview = Image.open(MISSION_SOURCE / "map.png").convert("RGB").resize((768, 768), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (768, 816), (15, 20, 22))
    canvas.paste(preview, (0, 48))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((10, 8), f"LIVE OPENRA TELEMETRY — {snapshot.map_name} — TICK {snapshot.tick}", fill=(235, 240, 225), font=font)
    draw.text((10, 25), f"ORDERS {snapshot.order_count}  KILLS {snapshot.units_killed}  LOSSES {snapshot.units_lost}  EXPLORED {snapshot.explored_percent:.1f}%", fill=(125, 210, 220), font=font)

    def point(cell_x: int, cell_y: int) -> tuple[int, int]:
        return round(cell_x / 96 * 768), 48 + round(cell_y / 96 * 768)

    for building in snapshot.buildings:
        x, y = point(building.cell_x, building.cell_y)
        draw.rectangle((x - 5, y - 5, x + 5, y + 5), fill=(210, 55, 48), outline=(255, 220, 150))
    for unit in snapshot.units:
        x, y = point(unit.cell_x, unit.cell_y)
        radius = 5 if unit.kind.lower() in {"cnluyang", "cnhaiwang", "cnskyspear", "cncloud", "cncrane"} else 3
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(240, 70, 55), outline=(255, 235, 160))
        if unit.kind.lower() in {"cnnetwork", "redspear", "cnzbd", "cnluyang", "cnhaiwang"}:
            draw.text((x + 5, y - 7), unit.kind.upper(), fill=(255, 245, 205), font=font)
    for enemy in (*snapshot.visible_enemies, *snapshot.visible_enemy_buildings):
        x, y = point(enemy.cell_x, enemy.cell_y)
        draw.rectangle((x - 4, y - 4, x + 4, y + 4), fill=(74, 84, 98), outline=(235, 235, 235))

    canvas.save(path)
    return {"path": str(path.resolve()), "tick": snapshot.tick, "width": canvas.width, "height": canvas.height,
            "scope": "live-engine-telemetry-fallback"}


def save_frame(bridge: OpenRABridge, snapshot: GameSnapshot, path: Path) -> dict[str, object]:
    try:
        frame = bridge.capture_frame()
        path.write_bytes(frame.png)
        return {"path": str(path.resolve()), "tick": frame.tick, "width": frame.width, "height": frame.height, "scope": frame.scope}
    except RuntimeError:
        # Multi-session Null-platform matches do not expose the local companion
        # renderer. Preserve exact live positions and events in a tactical frame.
        return render_telemetry_frame(snapshot, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9996)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--engine", type=Path, default=ROOT / "engine" / "openra" / "bin" / "OpenRA.exe")
    args = parser.parse_args()

    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    engine = EngineProcess(args.engine.resolve(), ROOT / "engine" / "openra", args.port, evidence)
    engine.start()
    bridge = OpenRABridge(f"127.0.0.1:{args.port}", timeout=15)
    session_id = ""
    try:
        session_id = bridge.create_session("haitan-network-2026.oramap", "China:rl-agent", 8122026)
        start = wait_for_session(bridge)
        required = {
            "cnrifle", "cnnetwork", "cnportable", "redspear", "cnqilin", "cnlynx", "cnzbd", "cnphl",
            "cnskyspear", "cncloud", "cncrane", "cnluyang", "cnhaiwang",
        }
        present = {unit.kind.lower() for unit in start.units}
        missing = sorted(required - present)
        if missing:
            raise RuntimeError(f"live mission is missing China roster actors: {missing}")

        frames = [save_frame(bridge, start, evidence / "01-china-deployment.png")]
        start_positions = {unit.actor_id: (unit.cell_x, unit.cell_y) for unit in start.units}

        destinations = {
            "cnrifle": [(39, 38), (40, 44), (35, 47)],
            "cnportable": [(42, 40), (42, 46)],
            "cnnetwork": [(44, 44)],
            "cnqilin": [(48, 40), (48, 45)],
            "cnlynx": [(50, 43)],
            "cnphl": [(44, 37)],
            "cnzbd": [(66, 44), (68, 43), (65, 42)],
            "cnskyspear": [(78, 54)],
            "cncloud": [(82, 57)],
            "cncrane": [(72, 51)],
            "cnluyang": [(69, 40)],
            "cnhaiwang": [(72, 42)],
            "redspear": [(52, 44)],
        }
        commands = []
        for kind, targets in destinations.items():
            for unit, (x, y) in zip(actors(start, kind), targets):
                action = "attack_move" if unit.can_attack and kind != "cnnetwork" else "move"
                commands.append(ActionCommand(action, actor_id=unit.actor_id, target_x=x, target_y=y))
        moved = bridge.fast_advance(950, tuple(commands), check_events_every=0, enabled_interrupts=())

        deploy_commands = []
        for kind in ("cnnetwork", "cnportable"):
            deploy_commands.extend(ActionCommand("deploy", actor_id=unit.actor_id) for unit in actors(moved, kind))
        deployed = bridge.fast_advance(150, tuple(deploy_commands), check_events_every=0, enabled_interrupts=())
        landing_commands = tuple(
            ActionCommand("move", actor_id=unit.actor_id, target_x=72 + index, target_y=50 + index)
            for index, unit in enumerate(actors(deployed, "cnzbd"))
        )
        maneuver = bridge.fast_advance(500, landing_commands, check_events_every=0, enabled_interrupts=())
        frames.append(save_frame(bridge, maneuver, evidence / "02-network-and-amphibious-maneuver.png"))

        objective_states = {objective.objective_id: objective.state for objective in maneuver.objectives}
        if objective_states.get(0) != "completed" or objective_states.get(1) != "completed":
            zbd_cells = [(unit.actor_id, unit.cell_x, unit.cell_y) for unit in actors(maneuver, "cnzbd")]
            raise RuntimeError(f"network/amphibious objectives did not complete live: {objective_states}; cnzbd={zbd_cells}")

        attack_commands = []
        targets = list(maneuver.visible_enemies) + list(maneuver.visible_enemy_buildings)
        combatants = [unit for unit in maneuver.units if unit.can_attack and unit.kind.lower() not in {"cnnetwork"}]
        if targets:
            for index, unit in enumerate(combatants):
                attack_commands.append(ActionCommand("attack", actor_id=unit.actor_id,
                                                    target_actor_id=targets[index % len(targets)].actor_id))
        else:
            for unit in combatants:
                attack_commands.append(ActionCommand("attack_move", actor_id=unit.actor_id, target_x=76, target_y=55))
        combat = bridge.fast_advance(1800, tuple(attack_commands), check_events_every=0, enabled_interrupts=())
        frames.append(save_frame(bridge, combat, evidence / "03-combined-arms-contact.png"))

        end_positions = {unit.actor_id: (unit.cell_x, unit.cell_y) for unit in maneuver.units}
        actual_vectors = {}
        for actor_id, start_cell in start_positions.items():
            if actor_id not in end_positions:
                continue
            end_cell = end_positions[actor_id]
            vector = (end_cell[0] - start_cell[0], end_cell[1] - start_cell[1])
            if vector != (0, 0):
                actual_vectors[str(actor_id)] = [*vector]
        if len(actual_vectors) < 8:
            raise RuntimeError(f"only {len(actual_vectors)} actors showed live movement")
        if combat.units_killed + combat.units_lost <= start.units_killed + start.units_lost:
            raise RuntimeError("live combat produced no kill/loss telemetry")
        if combat.tick <= start.tick + 2_000:
            raise RuntimeError("live combat did not advance far enough")

        telemetry = {
            "schema": "openra-ai.china-live-verification/v1",
            "session_id": session_id,
            "engine": str(args.engine.resolve()),
            "seed": 8122026,
            "required_roster": sorted(required),
            "actual_movement_vectors": actual_vectors,
            "frames": frames,
            "snapshots": {
                "start": compact(start),
                "maneuver": compact(maneuver),
                "combat": compact(combat),
            },
        }
        telemetry_path = evidence / "telemetry.json"
        telemetry_path.write_text(json.dumps(telemetry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({
            "ok": True,
            "map": combat.map_name,
            "start_tick": start.tick,
            "combat_tick": combat.tick,
            "orders": combat.order_count,
            "kills": combat.units_killed,
            "losses": combat.units_lost,
            "moved_actors": len(actual_vectors),
            "visible_enemies": len(combat.visible_enemies),
            "frames": frames,
            "telemetry": str(telemetry_path),
        }, ensure_ascii=False))
        return 0
    finally:
        if session_id:
            try:
                bridge.destroy_session(session_id)
            except RuntimeError:
                pass
        bridge.close()
        engine.stop()


if __name__ == "__main__":
    raise SystemExit(main())
