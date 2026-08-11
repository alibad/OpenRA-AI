from __future__ import annotations

import argparse
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .game_runtime import GameRuntime
from .models import ActionCommand


mcp = FastMCP("openra-game", instructions="Fog-respecting tools for controlling one local OpenRA match.")
runtime: GameRuntime | None = None
proposal_mode = False


def _game() -> GameRuntime:
    if runtime is None:
        raise RuntimeError("OpenRA game MCP runtime is not configured")
    return runtime


def _group(action: str, actor_ids: list[int], **values: object) -> dict:
    if not actor_ids:
        raise ValueError("actor_ids must not be empty")
    commands = tuple(ActionCommand(action=action, actor_id=actor_id, **values) for actor_id in actor_ids)
    return _submit(commands)


def _submit(commands: tuple[ActionCommand, ...]) -> dict:
    if proposal_mode:
        return _game().propose(commands)
    # Production commands are applied asynchronously by the OpenRA order
    # pipeline. Settle a few ticks so the returned snapshot exposes the new
    # queue/building and a fast local model does not repeat the same command.
    production_actions = {"build", "train", "place_building", "cancel_production"}
    settle_ticks = 8 if any(command.action in production_actions for command in commands) else 1
    return _game().issue(commands, ticks=settle_ticks)


@mcp.tool()
def battlefield() -> dict:
    """Read current fog-respecting state plus faction/map-specific strategy, scout, placement, and economy guidance."""
    return _game().battlefield()


@mcp.tool()
def match_status() -> dict:
    """Read the selected match phase, tick, factions, and winner without advancing time."""
    return _game().state()


@mcp.tool()
def log_decision(decision: str, evidence: str, expected_result: str) -> dict:
    """Persist a concise strategic decision, the observed evidence behind it, and its expected result for post-match learning."""
    return _game().log_decision(decision, evidence, expected_result)


@mcp.tool()
def advance(ticks: int = 250) -> dict:
    """Advance 1-1500 game ticks at CPU speed, stopping early for threats, discoveries, completed production, or game over."""
    if proposal_mode:
        state = _game().state()
        return {
            "proposal_mode": True,
            "advanced": False,
            "reason": "Live player matches continue in real time; the interactive planner cannot advance them.",
            "state": state,
        }
    return _game().advance(ticks)


@mcp.tool()
def move(actor_ids: list[int], target_x: int, target_y: int, queued: bool = False) -> dict:
    """Move owned units to a map cell."""
    return _group("move", actor_ids, target_x=target_x, target_y=target_y, queued=queued)


@mcp.tool()
def attack_move(actor_ids: list[int], target_x: int, target_y: int, queued: bool = False) -> dict:
    """Move owned combat units toward a cell while engaging enemies along the route."""
    return _group("attack_move", actor_ids, target_x=target_x, target_y=target_y, queued=queued)


@mcp.tool()
def attack(actor_ids: list[int], target_actor_id: int, queued: bool = False) -> dict:
    """Order owned combat units to attack one currently visible enemy actor ID."""
    return _group("attack", actor_ids, target_actor_id=target_actor_id, queued=queued)


@mcp.tool()
def stop(actor_ids: list[int]) -> dict:
    """Stop owned units and clear their current activity."""
    return _group("stop", actor_ids)


@mcp.tool()
def harvest(actor_ids: list[int], target_x: int = 0, target_y: int = 0, queued: bool = False) -> dict:
    """Send owned harvesters to resources; omit the cell to let OpenRA choose."""
    return _group("harvest", actor_ids, target_x=target_x, target_y=target_y, queued=queued)


@mcp.tool()
def build(item_type: str, count: int = 1) -> dict:
    """Queue 1-5 buildings by exact available production ID; placement is a separate tool."""
    if not 1 <= count <= 5:
        raise ValueError("count must be between 1 and 5")
    item = item_type.strip().lower()
    return _submit(tuple(ActionCommand(action="build", item_type=item, queued=True) for _ in range(count)))


@mcp.tool()
def train(item_type: str, count: int = 1) -> dict:
    """Queue 1-4 units by exact available production ID, subject to rolling composition caps."""
    if not 1 <= count <= 4:
        raise ValueError("count must be between 1 and 4")
    item = item_type.strip().lower()
    return _submit(tuple(ActionCommand(action="train", item_type=item, queued=True) for _ in range(count)))


@mcp.tool()
def deploy(actor_ids: list[int]) -> dict:
    """Deploy owned deployable actors, including unpacking an MCV into a construction yard."""
    return _group("deploy", actor_ids)


@mcp.tool()
def place_building(item_type: str, target_x: int = 0, target_y: int = 0) -> dict:
    """Place one completed building; omit the cell to use ore-, exit-, spacing-, and path-aware engine optimization."""
    if not proposal_mode:
        # Autonomous models are intentionally not trusted to out-place the
        # deterministic ore/spacing/exit optimizer. Interactive proposals keep
        # explicit cells so a human's requested location is preserved.
        target_x = 0
        target_y = 0
    return _submit((ActionCommand(
        action="place_building",
        item_type=item_type.strip().lower(),
        target_x=target_x,
        target_y=target_y,
    ),))


@mcp.tool()
def cancel_production(item_type: str) -> dict:
    """Cancel one queued production item by exact ID."""
    return _submit((ActionCommand(action="cancel_production", item_type=item_type.strip().lower()),))


@mcp.tool()
def repair(building_ids: list[int]) -> dict:
    """Start repairing damaged owned buildings."""
    return _group("repair", building_ids)


@mcp.tool()
def sell(building_ids: list[int]) -> dict:
    """Sell selected owned buildings. This is irreversible inside the match."""
    return _group("sell", building_ids)


@mcp.tool()
def set_rally_point(building_ids: list[int], target_x: int, target_y: int) -> dict:
    """Set the rally point for owned production buildings."""
    return _group("set_rally_point", building_ids, target_x=target_x, target_y=target_y)


@mcp.tool()
def guard(actor_ids: list[int], target_actor_id: int, queued: bool = False) -> dict:
    """Order owned combat units to follow and guard one owned allied actor."""
    return _group("guard", actor_ids, target_actor_id=target_actor_id, queued=queued)


@mcp.tool()
def set_stance(actor_ids: list[int], stance: int) -> dict:
    """Set combat stance: 0 hold fire, 1 return fire, 2 defend, or 3 attack anything."""
    return _group("set_stance", actor_ids, target_x=stance)


@mcp.tool()
def enter_transport(actor_ids: list[int], transport_actor_id: int, queued: bool = False) -> dict:
    """Load owned passenger units into an owned compatible transport."""
    return _group("enter_transport", actor_ids, target_actor_id=transport_actor_id, queued=queued)


@mcp.tool()
def disguise(actor_ids: list[int], target_actor_id: int) -> dict:
    """Disguise owned spies as one currently visible legal actor; use only valid_disguise_targets from battlefield."""
    return _group("disguise", actor_ids, target_actor_id=target_actor_id)


@mcp.tool()
def infiltrate(actor_ids: list[int], target_actor_id: int, queued: bool = False) -> dict:
    """Send owned infiltrators into one currently visible legal mission target; use valid_infiltration_targets from battlefield."""
    return _group("infiltrate", actor_ids, target_actor_id=target_actor_id, queued=queued)


@mcp.tool()
def capture(actor_ids: list[int], target_actor_id: int, queued: bool = False) -> dict:
    """Send owned engineers to one legal visible capture target from valid_capture_targets."""
    return _group("capture", actor_ids, target_actor_id=target_actor_id, queued=queued)


@mcp.tool()
def demolish(actor_ids: list[int], target_actor_id: int, queued: bool = False) -> dict:
    """Send owned C4 units to one legal visible demolition target; use valid_demolition_targets from battlefield."""
    return _group("demolish", actor_ids, target_actor_id=target_actor_id, queued=queued)


@mcp.tool()
def unload(transport_actor_ids: list[int]) -> dict:
    """Unload all passengers from owned loaded transports at their current locations."""
    return _group("unload", transport_actor_ids)


@mcp.tool()
def power_down(building_ids: list[int]) -> dict:
    """Toggle power on or off for owned buildings that support power-down."""
    return _group("power_down", building_ids)


@mcp.tool()
def set_primary(building_ids: list[int]) -> dict:
    """Set selected owned production buildings as primary producers."""
    return _group("set_primary", building_ids)


@mcp.tool()
def use_support_power(power_key: str, target_x: int, target_y: int) -> dict:
    """Activate one ready support power at an explored cell; destructive powers enforce a native friendly-fire exclusion zone."""
    return _submit((ActionCommand(
        action="use_support_power",
        item_type=power_key.strip().lower(),
        target_x=target_x,
        target_y=target_y,
    ),))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openra-ai-game-mcp")
    parser.add_argument("--bridge", default="127.0.0.1:9999")
    parser.add_argument("--session-id", default="")
    parser.add_argument(
        "--proposal-mode",
        action="store_true",
        help="validate action tools and return proposals without executing them",
    )
    parser.add_argument("--evidence-log", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    global proposal_mode, runtime
    args = _parser().parse_args(argv)
    proposal_mode = args.proposal_mode
    runtime = GameRuntime(args.bridge, args.session_id, evidence_log=args.evidence_log)
    try:
        mcp.run(transport="stdio")
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
