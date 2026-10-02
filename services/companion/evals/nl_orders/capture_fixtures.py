"""Capture natural-language order fixtures from live headless OpenRA matches.

Each scenario starts a private multi-session engine, locks the requested
factions in a private copy of a lobby map, and drives the match with ordinary
allowlisted engine orders until a milestone is reached.  The exact
fog-respecting observation is then written to ``fixtures/<name>.json``.

The large spatial tensor is omitted to keep fixtures reviewable; the order
interpreter does not use it.  Everything else is the unmodified
``GameObservation`` that the companion bridge serializes for the player.

    python services/companion/evals/nl_orders/capture_fixtures.py --mod ra --faction england
    python services/companion/evals/nl_orders/capture_fixtures.py --all
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from live import DEFAULT_ENGINE, REPOSITORY, LiveMatch  # noqa: E402

from openra_ai_companion.models import ActionCommand, GameSnapshot  # noqa: E402

FIXTURES = HERE / "fixtures"

# (mod, map, player faction, enemy faction, depth).  "full" drives the match
# to visible contact; "roster" stops after the production buildings exist.
SCENARIOS: tuple[tuple[str, str, str, str, str], ...] = (
    ("ra", "desert-rats", "england", "russia", "full"),
    ("ra", "desert-rats", "russia", "england", "full"),
    ("ra", "desert-rats", "china", "russia", "full"),
    ("ra", "ore-lord.oramap", "iran", "england", "roster"),
    ("ra", "ore-lord.oramap", "turkey", "russia", "roster"),
    ("ra", "ore-lord.oramap", "saudi", "russia", "roster"),
    ("ra", "ore-lord.oramap", "yemen", "england", "roster"),
    ("ra", "singles.oramap", "germany", "ukraine", "radar"),
    # RA2 has no multi-session RL agent, so its fixtures come from real-time
    # companion matches driven through the confirmed-action engine boundary.
    ("ra2", "little-big-lake", "america", "russia", "full"),
    ("ra2", "little-big-lake", "iraq", "america", "full"),
    ("ra2", "little-big-lake", "china", "america", "roster"),
    ("ra2", "little-big-lake", "iran", "america", "roster"),
    ("ra2", "little-big-lake", "turkey", "russia", "roster"),
)


def base_type(value: str) -> str:
    return value.lower().split("@", 1)[0].split(".", 1)[0]


def name_of(snapshot: GameSnapshot, item: str) -> str:
    return snapshot.actor_name(item).lower()


def pick(snapshot: GameSnapshot, include: tuple[str, ...], exclude: tuple[str, ...] = ()) -> str | None:
    for item in snapshot.available_production:
        name = name_of(snapshot, item)
        if any(word in name for word in include) and not any(word in name for word in exclude):
            return item
    return None


def queued(snapshot: GameSnapshot, item: str) -> dict | None:
    return next((entry for entry in snapshot.production if str(entry.get("item", "")).lower() == item), None)


def complete(entry: dict | None) -> bool:
    return entry is not None and (
        float(entry.get("progress", 0)) >= 0.999 or int(entry.get("remaining_ticks", 1)) <= 0
    )


class Driver:
    def __init__(self, match: LiveMatch, mod: str, faction: str, enemy: str, map_name: str) -> None:
        self.match = match
        self.mod = mod
        self.faction = faction
        self.enemy = enemy
        self.map_name = map_name
        self.snapshot = match.advance(1) if match.mode == "session" else match.observe()
        self.saved: list[str] = []

    def step(self, ticks: int = 25, *commands: ActionCommand) -> GameSnapshot:
        if self.match.mode == "session":
            self.snapshot = self.match.advance(ticks, tuple(commands))
            return self.snapshot
        # Real-time companion match: submit through the confirmed-action
        # boundary, then wait for the simulation to reach the requested tick.
        start = self.match.observe()
        if commands:
            receipt = self.match.execute(f"capture-{uuid.uuid4().hex}", start.tick, tuple(commands))
            if not receipt.accepted:
                print(f"  engine rejected capture step: {receipt.detail}", flush=True)
        target = start.tick + ticks
        current = start
        while current.tick < target:
            time.sleep(0.1)
            current = self.match.observe()
        self.snapshot = current
        return current

    def until(self, predicate, limit: int = 4000, step: int = 25) -> GameSnapshot:
        spent = 0
        while spent < limit:
            if predicate(self.snapshot):
                return self.snapshot
            self.step(step)
            spent += step
        raise TimeoutError(f"condition not reached after {limit} ticks at {self.snapshot.tick}")

    def save(self, scenario: str, note: str) -> None:
        raw = self.match.raw_observation()
        raw.pop("spatial_map", None)
        raw["spatial_channels"] = 0
        name = f"{self.mod}-{self.faction}-{scenario}"
        commit = subprocess.run(
            ["git", "-C", str(self.match.engine), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        product = subprocess.run(
            ["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        payload = {
            "fixture": name,
            "captured": {
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": (
                    "live headless OpenRA multi-session match (Game.Platform=Null)"
                    if self.match.mode == "session" else
                    "live headless real-time companion match (Game.Platform=Null, OPENRA_AI_COMPANION=1)"
                ),
                "mod": self.mod,
                "map": self.map_name,
                "player_faction": self.faction,
                "enemy_faction": self.enemy,
                "scenario": scenario,
                "note": note,
                "engine_commit": commit,
                "product_commit": product,
                "spatial_map": "omitted to keep fixtures reviewable; not used by order interpretation",
            },
            "state": self.match.state(),
            "observation": raw,
        }
        FIXTURES.mkdir(parents=True, exist_ok=True)
        (FIXTURES / f"{name}.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        self.saved.append(name)
        print(f"  saved {name} tick={raw.get('tick')}", flush=True)

    # -- build helpers -----------------------------------------------------
    def build(self, include: tuple[str, ...], exclude: tuple[str, ...] = (), *, place: bool = True) -> str | None:
        item = pick(self.snapshot, include, exclude)
        if item is None:
            return None
        self.step(10, ActionCommand("build", item_type=item, queued=True))
        self.until(lambda s: complete(queued(s, item)), limit=6000)
        if place:
            before = sum(base_type(b.kind) == base_type(item) for b in self.snapshot.buildings)
            for _ in range(6):
                self.step(25, ActionCommand("place_building", item_type=item))
                try:
                    self.until(lambda s: sum(base_type(b.kind) == base_type(item) for b in s.buildings) > before, limit=150)
                    break
                except TimeoutError:
                    continue
        return item

    def train(self, include: tuple[str, ...], count: int, exclude: tuple[str, ...] = ()) -> str | None:
        item = pick(self.snapshot, include, exclude)
        if item is None:
            return None
        self.step(10, *(ActionCommand("train", item_type=item, queued=True) for _ in range(count)))
        return item

    def deploy_mcv(self) -> None:
        mcv = next(unit for unit in self.snapshot.units if base_type(unit.kind) in {"mcv", "amcv", "smcv"})
        self.step(20, ActionCommand("deploy", actor_id=mcv.actor_id))
        self.until(lambda s: bool(s.buildings), limit=600)
        self.until(lambda s: bool(s.available_production), limit=300)


POWER = ("power plant", "reactor", "power")
POWER_EXCLUDE = ("advanced", "nuclear")
BARRACKS = ("barracks",)
REFINERY = ("refinery",)
FACTORY = ("war factory", "factory")
FACTORY_EXCLUDE = ("naval", "ship", "cloning")
INFANTRY = ("rifle", "gi", "conscript", "infantry", "soldier", "guard", "militia")
INFANTRY_EXCLUDE = ("engineer", "spy", "dog", "medic", "sniper", "tanya", "thief")
TANK = ("tank",)
TANK_EXCLUDE = ("destroyer", "mammoth", "apocalypse", "tesla", "mirage", "prism", "chrono", "flak")


def run_scenario(mod: str, map_name: str, faction: str, enemy: str, depth: str, work_root: Path) -> list[str]:
    started = time.monotonic()
    work = work_root / f"{mod}-{faction}"
    print(f"[{mod}/{faction}] starting on {map_name}", flush=True)
    mode = "companion" if mod == "ra2" else "session"
    with LiveMatch(mode, mod, map_name, work, player_faction=faction, enemy_faction=enemy,
                   opponent="normal", shared_root=work_root / "shared-content") as match:
        driver = Driver(match, mod, faction, enemy, map_name)
        driver.save("opening", "Start of match: the Mobile Construction Vehicle is not deployed yet.")
        driver.deploy_mcv()
        driver.step(30)
        driver.save("base-empty", "Construction Yard deployed; nothing queued yet.")
        power = pick(driver.snapshot, POWER, POWER_EXCLUDE)
        if power:
            driver.step(10, ActionCommand("build", item_type=power, queued=True))
            driver.until(lambda s: 0.2 <= float((queued(s, power) or {}).get("progress", 0)) <= 0.8, limit=2000, step=10)
            driver.save("power-queued", "A power plant is part-way through construction and not ready to place.")
            driver.until(lambda s: complete(queued(s, power)), limit=4000)
            driver.save("power-ready", "The power plant finished construction and is waiting for placement.")
            driver.step(25, ActionCommand("place_building", item_type=power))
            driver.until(lambda s: any(base_type(b.kind) == base_type(power) for b in s.buildings), limit=400)
        if depth == "radar":
            # A placed Radar Dome is a real power-down-capable structure.
            driver.build(REFINERY)
            driver.build(POWER, POWER_EXCLUDE)
            driver.build(("radar", "dome"))
            driver.step(60)
            driver.save("radar", "Base with a placed Radar Dome, two power plants and a refinery.")
            print(f"[{mod}/{faction}] done in {time.monotonic() - started:.0f}s", flush=True)
            return driver.saved
        driver.build(BARRACKS)
        driver.build(REFINERY)
        driver.build(POWER, POWER_EXCLUDE)
        driver.build(FACTORY, FACTORY_EXCLUDE)
        infantry = driver.train(INFANTRY, 5, INFANTRY_EXCLUDE)
        driver.step(50)
        tank = driver.train(TANK, 3, TANK_EXCLUDE)
        engineer = driver.train(("engineer",), 1)
        transport = driver.train(("apc", "transport", "ifv", "personnel"), 1, ("helicopter", "chinook", "plane"))
        driver.until(
            lambda s: sum(unit.can_attack for unit in s.units) >= 5,
            limit=6000,
        )
        driver.step(600)
        # Leave a mixed queue in progress, as a player usually has.
        if infantry:
            driver.step(5, ActionCommand("train", item_type=infantry, queued=True))
        radar = pick(driver.snapshot, ("radar", "dome", "air force command"), ())
        if radar:
            driver.step(5, ActionCommand("build", item_type=radar, queued=True))
        driver.step(60)
        driver.save("army", "Production base with idle infantry and vehicles, harvesters, and a mixed production queue.")
        # Empty transports report no passenger count, so identify them by role.
        carrier = next((unit for unit in driver.snapshot.units if unit.passenger_count >= 0 or any(
            word in name_of(driver.snapshot, unit.kind)
            for word in ("personnel carrier", "transport", "ifv", "infantry fighting", "flak track")
        )), None)
        riders = [unit for unit in driver.snapshot.units
                  if unit.can_attack and unit.idle and unit.kind.lower() in {infantry, "e1", "e2", "e3"}][:2]
        if carrier is not None and riders:
            driver.step(10, *(ActionCommand("enter_transport", actor_id=unit.actor_id,
                                            target_actor_id=carrier.actor_id) for unit in riders))
            try:
                driver.until(lambda s: any(unit.actor_id == carrier.actor_id and unit.passenger_count > 0
                                           for unit in s.units), limit=1500)
                driver.step(20)
                driver.save("transport-loaded", "Infantry have boarded an owned transport.")
            except TimeoutError:
                print(f"[{mod}/{faction}] transport did not load", flush=True)
        if depth != "full":
            print(f"[{mod}/{faction}] done in {time.monotonic() - started:.0f}s", flush=True)
            return driver.saved
        # Advance on the mirrored spawn until enemy structures are seen.
        base = driver.snapshot.buildings[0]
        width = driver.snapshot.map_width
        height = driver.snapshot.map_height
        target = (width - 1 - base.cell_x, height - 1 - base.cell_y)
        target = (min(max(2, target[0]), width - 3), min(max(2, target[1]), height - 3))
        army = [unit for unit in driver.snapshot.units if unit.can_attack]
        engineers = [unit for unit in driver.snapshot.units if unit.can_capture]
        driver.step(10, *(ActionCommand("attack_move", actor_id=unit.actor_id, target_x=target[0], target_y=target[1])
                          for unit in army[:10]),
                    *(ActionCommand("move", actor_id=unit.actor_id, target_x=target[0], target_y=target[1])
                      for unit in engineers[:1]))
        try:
            driver.until(lambda s: bool(s.visible_enemies or s.visible_enemy_buildings), limit=5000)
            driver.step(20)
            driver.save("contact", "Visible enemy forces or structures are in view.")
        except TimeoutError:
            print(f"[{mod}/{faction}] no contact before timeout", flush=True)
        try:
            driver.until(lambda s: bool(s.visible_enemy_buildings or s.remembered_enemy_buildings), limit=6000)
            driver.step(20)
            driver.save("enemy-base", "Enemy structures have been seen by the advancing force.")
        except TimeoutError:
            print(f"[{mod}/{faction}] enemy base not found before timeout", flush=True)
        try:
            driver.until(lambda s: any(b.hp_percent < 0.9 for b in s.buildings) or (
                bool(s.remembered_enemy_buildings) and not s.visible_enemy_buildings), limit=8000, step=50)
            driver.step(20)
            driver.save("late", "Later match state with remembered enemy structures under fog and/or base damage.")
        except TimeoutError:
            print(f"[{mod}/{faction}] no late-game milestone before timeout", flush=True)
        print(f"[{mod}/{faction}] done in {time.monotonic() - started:.0f}s", flush=True)
        return driver.saved


# Campaign missions provide rare, real special-unit states (valid demolition,
# infiltration and disguise targets, loaded transports) at mission start.
MISSIONS: tuple[tuple[str, str, str, int], ...] = (
    ("allies-03a", "tanya-demolition", "Tanya with visible demolition targets and an engineer.", 50),
    ("allies-05a", "spy-infiltration", "A spy with visible infiltration and disguise targets.", 50),
    ("soviet-06a", "engineers-apc", "Engineers who have just left their APC, plus heavy armor.", 50),
    ("soviet-06b", "loaded-apc", "APCs still carrying infantry at mission start.", 5),
)


def run_mission(map_name: str, label: str, note: str, ticks: int, work_root: Path) -> list[str]:
    from openra_ai_companion.mission_eval import inventory_missions

    spec = next(spec for spec in inventory_missions(REPOSITORY) if spec.map_name == map_name)
    work = work_root / f"mission-{map_name}"
    match = LiveMatch("session", "ra", map_name, work, shared_root=work_root / "shared-content")
    match.start_mission(spec.request_name, spec.player_slot)
    try:
        driver = Driver(match, "ra", "mission", "campaign", map_name)
        driver.step(ticks)
        driver.save(f"{map_name}-{label}", note)
        return driver.saved
    finally:
        match.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod", choices=("ra", "ra2"))
    parser.add_argument("--faction")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--missions", action="store_true", help="capture the campaign special-unit fixtures")
    parser.add_argument("--parallel", type=int, default=3)
    parser.add_argument("--work", type=Path, default=REPOSITORY / ".artifacts" / "nl-orders" / "capture")
    parser.add_argument("--engine", type=Path, default=DEFAULT_ENGINE)
    args = parser.parse_args()
    selected = [
        scenario for scenario in SCENARIOS
        if args.all or ((not args.mod or scenario[0] == args.mod) and (not args.faction or scenario[2] == args.faction))
    ]
    if args.missions and not (args.all or args.mod or args.faction):
        selected = []
    elif not selected:
        parser.error("no scenario selected")
    # Private content folders are created once, before parallel matches share them.
    from live import prepare_content
    for mod in sorted({scenario[0] for scenario in selected} | ({"ra"} if args.missions or args.all else set())):
        prepare_content(mod, args.work / "shared-content")
    results: dict[str, object] = {}

    def run(scenario):
        mod, map_name, faction, enemy, depth = scenario
        try:
            return f"{mod}-{faction}", run_scenario(mod, map_name, faction, enemy, depth, args.work)
        except Exception as error:  # keep the rest of the corpus
            return f"{mod}-{faction}", f"failed: {type(error).__name__}: {error}"

    with ThreadPoolExecutor(max_workers=max(1, min(4, args.parallel))) as pool:
        for key, value in pool.map(run, selected):
            results[key] = value
    if args.all or args.missions:
        for map_name, label, note, ticks in MISSIONS:
            try:
                results[f"mission-{map_name}"] = run_mission(map_name, label, note, ticks, args.work)
            except Exception as error:
                results[f"mission-{map_name}"] = f"failed: {type(error).__name__}: {error}"
    print(json.dumps(results, indent=2))
    return 0 if all(isinstance(value, list) for value in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
