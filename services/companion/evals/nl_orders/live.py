"""Disposable live OpenRA matches for natural-language order evaluation.

Two launch modes are supported:

* ``session`` starts the headless multi-session engine used by the autonomous
  evaluators.  It advances at CPU speed and is used to *capture* realistic
  snapshot fixtures.  It shares OpenRA's ``ObservationSerializer`` with the
  live companion bridge, so fixtures have the exact wire shape the player path
  receives.
* ``companion`` starts a normal single-player skirmish with
  ``OPENRA_AI_COMPANION=1``.  Confirmed actions travel through the real
  ``ExecuteCompanionActions`` engine boundary and receipts.  End-to-end proofs
  use this mode.

Every match uses a private support directory under the caller's work folder.
The player's OpenRA profile, settings, saves and installed apps are never
read or written.  Commercial Red Alert 2 data is imported through the
product's own ``import_owned_ra2`` path into that private directory.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPOSITORY = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY / "services" / "companion" / "src"))

from openra_ai_companion.bridge import OpenRABridge  # noqa: E402
from openra_ai_companion.models import ActionCommand, ActionReceipt, GameSnapshot  # noqa: E402

DEFAULT_ENGINE = REPOSITORY / "engine" / "openra"
CANONICAL_RA_CONTENT = REPOSITORY.parent / "OpenRA" / "Support" / "Content" / "ra"


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def ra2_mod_root(engine: Path) -> Path:
    """Return the prepared integrated RA2 mods folder for this engine checkout."""
    cache = engine / "Support" / "IntegratedGames"
    candidates = sorted(
        (path for path in cache.glob("*/mods") if (path / "ra2" / "mod.yaml").is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(
            "RA2 mod data is not prepared; run scripts/prepare-local-ra2.py --engine engine/openra"
        )
    return candidates[0]


def _junction(link: Path, target: Path) -> None:
    if link.exists():
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def prepare_content(mod: str, shared_root: Path) -> Path:
    """Return a private content folder for ``mod`` (created once, then reused)."""
    destination = shared_root / "Content" / mod
    if mod == "ra":
        if not (destination / "v2").is_dir():
            if not CANONICAL_RA_CONTENT.is_dir():
                raise RuntimeError(f"Freeware Red Alert content is missing at {CANONICAL_RA_CONTENT}")
            shutil.copytree(CANONICAL_RA_CONTENT, destination, dirs_exist_ok=True)
        return destination
    if mod == "ra2":
        previous = os.environ.get("OPENRA_AI_SUPPORT_DIR")
        os.environ["OPENRA_AI_SUPPORT_DIR"] = str(shared_root)
        try:
            from openra_ai_companion.game_content import import_owned_ra2

            import_owned_ra2()
        finally:
            if previous is None:
                os.environ.pop("OPENRA_AI_SUPPORT_DIR", None)
            else:
                os.environ["OPENRA_AI_SUPPORT_DIR"] = previous
        return destination
    raise ValueError(f"unsupported mod {mod}")


def _map_source(engine: Path, mod: str, map_name: str) -> Path:
    if mod == "ra":
        return engine / "mods" / "ra" / "maps" / map_name
    return ra2_mod_root(engine) / "ra2" / "maps" / map_name


def locked_map_copy(
    engine: Path,
    mod: str,
    map_name: str,
    support: Path,
    player_faction: str | None,
    enemy_faction: str | None,
) -> str:
    """Copy a lobby map into the private support dir with locked factions."""
    source = _map_source(engine, mod, map_name)
    stem = map_name.removesuffix(".oramap")
    label = "-".join(part for part in (stem, player_faction or "any", enemy_faction or "any") if part)
    destination = support / "maps" / mod / "{DEV_VERSION}" / f"nl-{label}"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        with zipfile.ZipFile(source) as archive:
            archive.extractall(destination)
    map_yaml = destination / "map.yaml"
    text = map_yaml.read_text(encoding="utf-8-sig")

    def lock(text: str, slot: str, faction: str | None) -> str:
        if not faction:
            return text
        pattern = rf"(\tPlayerReference@{slot}:\n(?:(?!\tPlayerReference)[^\n]*\n)*?\t\tFaction:) [^\n]+"
        text, count = re.subn(pattern, rf"\g<1> {faction}\n\t\tLockFaction: True", text)
        if count != 1:
            raise RuntimeError(f"could not lock {slot} faction in {map_name}")
        return text

    text = lock(text, "Multi0", player_faction)
    text = lock(text, "Multi1", enemy_faction)
    map_yaml.write_text(text, encoding="utf-8", newline="\n")
    return destination.name


@dataclass
class LiveMatch:
    """One private OpenRA process plus its gRPC bridge."""

    mode: str  # "session" or "companion"
    mod: str
    map_name: str
    work_dir: Path
    player_faction: str | None = None
    enemy_faction: str | None = None
    opponent: str = "normal"
    engine: Path = DEFAULT_ENGINE
    shared_root: Path | None = None
    seed: int = 7
    port: int = 0
    process: subprocess.Popen | None = field(default=None, init=False)
    bridge: OpenRABridge | None = field(default=None, init=False)
    launch_map: str = field(default="", init=False)
    log_path: Path | None = field(default=None, init=False)

    def __enter__(self) -> "LiveMatch":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def start(self) -> None:
        self._launch(lock_map=True)
        if self.mode == "session":
            assert self.bridge is not None
            self.bridge.create_session(self.launch_map, f"Multi0:rl-agent,Multi1:{self.opponent}", self.seed)
        self.wait_until(lambda snapshot: bool(snapshot.units or snapshot.buildings), timeout=120)

    def start_mission(self, request_name: str, player_slot: str) -> None:
        """Start a campaign mission session (capture mode) with the agent in its player slot."""
        self.mode = "session"
        self._launch(lock_map=False)
        assert self.bridge is not None
        self.bridge.create_session(request_name, f"{player_slot}:rl-agent", self.seed)
        self.wait_until(lambda snapshot: bool(snapshot.units or snapshot.buildings), timeout=120)

    def _launch(self, *, lock_map: bool) -> None:
        self.work_dir = self.work_dir.resolve()
        self.engine = self.engine.resolve()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        support = self.work_dir / "support"
        support.mkdir(parents=True, exist_ok=True)
        shared = self.shared_root or (self.work_dir.parent / "shared-content")
        content = prepare_content(self.mod, shared)
        _junction(support / "Content" / self.mod, content)
        if lock_map:
            self.launch_map = locked_map_copy(
                self.engine, self.mod, self.map_name, support, self.player_faction, self.enemy_faction
            )
        self.port = self.port or free_port()
        binaries = self.engine / "bin"
        arguments = [
            "dotnet", str(binaries / "OpenRA.dll"),
            f"Engine.EngineDir={self.engine}",
            f"Engine.SupportDir={support}",
            f"Game.Mod={self.mod}",
            "Game.Platform=Null",
            "Game.FetchNews=false",
        ]
        if self.mod == "ra2":
            arguments.append(f"Engine.ModSearchPaths={self.engine / 'mods'},{ra2_mod_root(self.engine)}")
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith("OPENRA_AI_") and key not in {"OPENAI_API_KEY"}
        }
        environment["DOTNET_ROLL_FORWARD"] = "LatestMajor"
        # The Windows launcher otherwise re-enters launch-game.ps1 and starts a
        # full product companion; evaluation owns its own companion instance.
        environment["OPENRA_AI_DISABLE_AUTOSTART"] = "1"
        if self.mode == "session":
            arguments.append(f"Launch.MultiSession={self.port}")
        elif self.mode == "companion":
            arguments += [f"Launch.Map={self.launch_map}", f"Launch.Bots=Multi1:{self.opponent}"]
            environment.update({
                "OPENRA_AI_COMPANION": "1",
                "OPENRA_AI_COMPANION_READY": "1",
                "OPENRA_AI_STARTUP_ENABLED": "1",
                "OPENRA_AI_STARTUP_MUTED": "1",
                "OPENRA_AI_STARTUP_AUTO_ACT": "0",
                "OPENRA_AI_GRPC_PORT": str(self.port),
            })
        else:
            raise ValueError(self.mode)
        self.log_path = self.work_dir / "engine.log"
        log = self.log_path.open("wb")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            arguments, cwd=binaries, env=environment, stdout=log, stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        self.bridge = OpenRABridge(f"127.0.0.1:{self.port}", timeout=5.0)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"OpenRA exited with {self.process.returncode}; see {self.log_path}")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.25):
                    break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("OpenRA did not open its bridge port")

    def stop(self) -> None:
        if self.bridge is not None:
            if self.mode == "session":
                try:
                    self.bridge.destroy_session()
                except RuntimeError:
                    pass
            self.bridge.close()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    # -- observation -------------------------------------------------------
    def observe(self) -> GameSnapshot:
        assert self.bridge is not None
        return self.bridge.observe()

    def raw_observation(self) -> dict:
        """Return the exact proto-to-dict observation used by GameSnapshot.from_dict."""
        from google.protobuf.json_format import MessageToDict

        from openra_ai_companion.generated import rl_bridge_pb2

        assert self.bridge is not None
        message = self.bridge.stub.Observe(
            rl_bridge_pb2.StateRequest(session_id=self.bridge.session_id), timeout=self.bridge.timeout
        )
        return MessageToDict(message, preserving_proto_field_name=True)

    def state(self) -> dict:
        assert self.bridge is not None
        return self.bridge.state()

    def wait_until(
        self,
        predicate: Callable[[GameSnapshot], bool],
        *,
        timeout: float,
        step_ticks: int = 25,
    ) -> GameSnapshot:
        deadline = time.monotonic() + timeout
        last_error = ""
        while time.monotonic() < deadline:
            try:
                snapshot = self.advance(step_ticks) if self.mode == "session" else self.observe()
                if predicate(snapshot):
                    return snapshot
            except RuntimeError as error:
                last_error = str(error)
            if self.process is not None and self.process.poll() is not None:
                raise RuntimeError(f"OpenRA exited with {self.process.returncode}; see {self.log_path}")
            if self.mode == "companion":
                time.sleep(0.2)
        raise TimeoutError(f"live condition not reached ({last_error})")

    # -- control -----------------------------------------------------------
    def advance(self, ticks: int, commands: tuple[ActionCommand, ...] = ()) -> GameSnapshot:
        """Advance a headless session (capture mode only)."""
        assert self.bridge is not None and self.mode == "session"
        return self.bridge.fast_advance(ticks, commands, check_events_every=0, enabled_interrupts=())

    def execute(self, request_id: str, expected_tick: int, commands: tuple[ActionCommand, ...]) -> ActionReceipt:
        """Submit a confirmed proposal through the real companion engine boundary."""
        assert self.bridge is not None and self.mode == "companion"
        return self.bridge.execute_actions(request_id, expected_tick, commands)

    def keep_companion_ready(self) -> bool:
        assert self.bridge is not None
        return self.bridge.update_companion_status("ready", "NL order validation", enabled=True, muted=True)
