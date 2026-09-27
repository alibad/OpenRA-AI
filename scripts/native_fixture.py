"""Shared helpers for private, headless native OpenRA fixtures.

Two sources of nondeterminism used to leak into the RA2 production tests:

* Their deadline was wall-clock time measured from process launch. Native
  fixtures run at normal game speed (40 ms per tick), so JIT/content start-up
  and host load were charged to the gameplay under test. The same match that
  passed at tick ~2600 in 119 s on an idle host needed 140-156 s when four
  fixtures started together. Budgets are therefore expressed in game ticks;
  wall-clock time is only a generous guard against a hung process.
* Exact-destination movement was sampled by polling while several ships
  crossed one another's routes. A moving friendly legitimately nudges an idle
  unit off its cell (``Mobile`` implements ``INotifyBlockingMove`` by queueing
  ``Nudge``) and the nudged unit does not return; a mover whose final cell is
  momentarily occupied by passing traffic also ends its ``Move`` one cell short
  ("avoid fighting over the destination cell"). Either way the old check waited
  for an arrival that could no longer be observed. :class:`ExactMoveCheck`
  records the first observed exact arrival, and repeats the *same* move for an
  actor that is idle away from a destination it has not yet been seen to reach.
  The actor must still path natively to the exact cell; nothing is teleported.

A launch that exits before its first observation (engine start-up failure)
carries no information about the gameplay under test; :func:`run_with_startup_retry`
relaunches it once in a fresh profile and keeps the failed attempt's evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import time
from typing import Mapping

TICKS_PER_SECOND = 25  # The "default" game speed: Timestep 40 ms.


def link_directory(link: Path, target: Path) -> None:
    """Expose ``target`` at ``link`` without copying it.

    Prefer a symbolic link. Windows only grants that privilege to elevated or
    developer-mode sessions, so fall back to an NTFS junction there. Neither
    form copies owned game content into a disposable profile.
    """
    target = Path(target).resolve()
    try:
        Path(link).symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        import _winapi  # CPython's documented-internal junction helper.

        _winapi.CreateJunction(str(target), str(link))


def unlink_directory(link: Path) -> None:
    """Remove a link created by :func:`link_directory`, never its target."""
    link = Path(link)
    if link.is_symlink() or (os.name == "nt" and link.is_junction()):
        os.unlink(link) if link.is_symlink() else os.rmdir(link)


class BudgetExceeded(TimeoutError):
    """The fixture did not reach its goal within its game-time budget."""


@dataclass
class TickBudget:
    """A game-time deadline with a wall-clock guard for hung processes."""

    ticks: int
    hang_guard_seconds: float = 900.0
    started: float = field(default_factory=time.monotonic)

    @classmethod
    def from_seconds(cls, game_seconds: float, hang_guard_seconds: float = 900.0) -> "TickBudget":
        return cls(int(round(game_seconds * TICKS_PER_SECOND)), hang_guard_seconds)

    def wall_ok(self) -> bool:
        return time.monotonic() - self.started < self.hang_guard_seconds

    def elapsed(self) -> float:
        return round(time.monotonic() - self.started, 2)

    def check(self, tick: int, phase: str) -> None:
        if tick > self.ticks:
            raise BudgetExceeded(f"Game-time budget of {self.ticks} ticks exceeded in {phase} (tick {tick})")

    def failure(self, phase: str, process_running: bool) -> str:
        if process_running and not self.wall_ok():
            return f"Hang guard ({self.hang_guard_seconds:.0f} s wall clock) expired in {phase}"
        if not process_running:
            return f"Game process exited in {phase}"
        return f"Stopped in {phase}"

    def as_dict(self) -> dict:
        return {"ticks": self.ticks, "game_seconds": self.ticks / TICKS_PER_SECOND,
                "hang_guard_seconds": self.hang_guard_seconds, "wall_seconds": self.elapsed()}


class ExactMoveCheck:
    """Order actors to exact cells and prove native arrival despite nudging.

    ``destinations`` maps an actor type to its exact map (MPos) cell. Actor
    lookups use the fixture's ``{kind: unit}`` observation mapping.
    """

    def __init__(self, label: str, destinations: Mapping[str, tuple[int, int]], *,
                 settle_ticks: int = 50, max_reissues: int = 3):
        if len(set(destinations.values())) != len(destinations):
            raise ValueError("Exact destinations must be distinct cells")
        self.label = label
        self.destinations = {kind: tuple(cell) for kind, cell in destinations.items()}
        self.settle_ticks = settle_ticks
        self.max_reissues = max_reissues
        self.dispatched_tick: int | None = None
        self.ordered: dict[str, int] = {}
        self.reissues: dict[str, list[int]] = {kind: [] for kind in destinations}
        self.origin: dict[str, tuple[int, int]] = {}
        self.arrived: dict[str, int] = {}
        self.displaced: dict[str, tuple[int, int]] = {}

    def _order(self, bridge, tick: int, unit) -> None:
        from openra_ai_companion.models import ActionCommand

        x, y = self.destinations[unit.kind]
        attempt = len(self.reissues[unit.kind])
        receipt = bridge.execute_actions(f"{self.label}-{unit.kind}-{attempt}", tick, (
            ActionCommand("move", actor_id=unit.actor_id, target_x=x, target_y=y),))
        if not receipt.accepted:
            raise ValueError(f"Move for {unit.kind} rejected: {receipt.as_dict()}")
        self.ordered[unit.kind] = tick

    def dispatch(self, bridge, tick: int, units: Mapping[str, object]) -> None:
        self.dispatched_tick = tick
        for kind in self.destinations:
            unit = units.get(kind)
            if unit is None:
                raise ValueError(f"{kind} is missing before movement")
            self.origin[kind] = (unit.cell_x, unit.cell_y)
            self._order(bridge, tick, unit)

    def update(self, bridge, tick: int, units: Mapping[str, object]) -> bool:
        """Record arrivals, repeat stalled orders; return True when all arrived."""
        for kind, destination in self.destinations.items():
            unit = units.get(kind)
            if unit is None:
                raise ValueError(f"{kind} disappeared during movement")
            cell = (unit.cell_x, unit.cell_y)
            if cell == destination:
                self.arrived.setdefault(kind, tick)
                self.displaced.pop(kind, None)
            elif kind in self.arrived:
                # Native nudging after arrival; the arrival itself was observed.
                self.displaced[kind] = cell
            elif unit.idle and tick >= self.ordered[kind] + self.settle_ticks:
                if len(self.reissues[kind]) >= self.max_reissues:
                    raise ValueError(f"{kind} stopped at {cell}, not {destination}, after "
                                     f"{self.max_reissues} repeated orders")
                self.reissues[kind].append((tick, cell))
                self._order(bridge, tick, unit)
        return len(self.arrived) == len(self.destinations)

    def as_dict(self) -> dict:
        start = self.dispatched_tick or 0
        return {
            "dispatched_tick": self.dispatched_tick,
            "destinations": {k: list(v) for k, v in self.destinations.items()},
            "origin": {k: list(v) for k, v in self.origin.items()},
            "arrival_ticks": {k: v - start for k, v in sorted(self.arrived.items())},
            # Tick and the idle cell each repeated order was issued from.
            "repeated_orders": {k: [[t - start, list(c)] for t, c in v] for k, v in self.reissues.items() if v},
            "displaced_after_arrival": {k: list(v) for k, v in sorted(self.displaced.items())},
        }


def startup_failure(report: dict, profile: Path) -> None:
    """Mark a report whose game process exited before it was ever observed."""
    report["startup_failure"] = True
    log = Path(profile) / "game.log"
    if log.is_file():
        report["startup_log_tail"] = log.read_text(errors="replace")[-1500:]


def run_with_startup_retry(run, *args, attempts: int = 3, pause_seconds: float = 5.0, **kwargs) -> bool:
    """Call a fixture ``run(resources, binaries, content, output, ...)``.

    Only a launch marked :func:`startup_failure` is repeated, after a short
    pause. Observed on Windows when several fixtures start together: the
    engine occasionally skips the private user-map folder during
    ``MapCache.LoadMaps`` (an optional folder whose open failure is silently
    ignored) and exits with "Could not find map" before the first tick; it
    was not reproduced in 40 instrumented launches. Each failed attempt's
    result is preserved beside the final one, which records how many
    launches it took.
    """
    output = Path(args[3])
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            time.sleep(pause_seconds)
        passed = run(*args, **kwargs)
        result_path = output / "result.json"
        result = json.loads(result_path.read_text())
        if passed or not result.get("startup_failure") or attempt == attempts:
            if attempt > 1:
                result["startup_attempts"] = attempt
                result_path.write_text(json.dumps(result, indent=2) + "\n")
            return passed
        result_path.rename(output / f"result-startup-failure-{attempt}.json")
    return False

