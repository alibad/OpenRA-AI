"""End-to-end natural-language order proof in live OpenRA matches.

Path under test (no shortcuts):

    player text or synthetic speech
      -> the real ``openra-ai-companion watch`` service (HTTP control API)
      -> natural-language interpretation -> pending proposal
      -> /v1/actions/confirm -> Python revalidation
      -> ExecuteCompanionActions -> OpenRA game-thread validation -> receipt
      -> observed game-state change (queue, building, position, stance, ...)

Voice commands are *synthetic speech*: text is rendered by the product's local
Kokoro voice, prepared with the same ``prepare_voice_audio`` step as push-to-
talk, transcribed by the product's local Whisper through the companion's
``/v1/transcribe`` endpoint, cleaned like the hotkey path, and only then sent
to the order pipeline.  No human voice is involved.

    python services/companion/evals/nl_orders/live_e2e.py --router-url http://127.0.0.1:4610 --mod ra
    python services/companion/evals/nl_orders/live_e2e.py --router-url http://127.0.0.1:4610 --mod ra2
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from live import REPOSITORY, LiveMatch, free_port  # noqa: E402

from openra_ai_companion.models import GameSnapshot, Unit  # noqa: E402


def http_json(url: str, payload: dict | None = None, *, timeout: float = 120) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                     method="GET" if payload is None else "POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def http_bytes(url: str, body: bytes, content_type: str, *, timeout: float = 120) -> bytes:
    request = urllib.request.Request(url, data=body, headers={"Content-Type": content_type}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def base(kind: str) -> str:
    return kind.lower().split("@", 1)[0].split(".", 1)[0]


@dataclass
class Step:
    utterance: str
    verify: Callable[[GameSnapshot, GameSnapshot, dict], str] | None
    expect_proposal: bool = True
    voice: bool = False
    wait_for: Callable[[GameSnapshot], bool] | None = None
    timeout: float = 60.0
    note: str = ""


@dataclass
class Session:
    match: LiveMatch
    control: str
    router_url: str
    evidence: list[dict] = field(default_factory=list)

    def observe(self) -> GameSnapshot:
        return self.match.observe()

    def wait(self, predicate: Callable[[GameSnapshot], bool], timeout: float) -> GameSnapshot | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snapshot = self.observe()
            if predicate(snapshot):
                return snapshot
            time.sleep(0.25)
        return None

    def speak_and_transcribe(self, text: str) -> tuple[str, dict]:
        """Synthetic speech: local Kokoro -> push-to-talk preparation -> local Whisper."""
        from openra_ai_companion.hotkeys import VoiceHotkeys
        from openra_ai_companion.voice import prepare_voice_audio

        started = time.perf_counter()
        wav = http_bytes(self.router_url + "/v1/audio/speech",
                         json.dumps({"model": "local-kokoro", "voice": "alloy", "input": text, "response_format": "wav"}).encode(),
                         "application/json")
        synthesized = time.perf_counter()
        prepared, signal = prepare_voice_audio(wav)
        transcription = json.loads(http_bytes(self.control + "/v1/transcribe?filename=question.wav", prepared, "audio/wav"))
        raw = str(transcription.get("text", "")).strip()
        transcript = VoiceHotkeys._clean_transcript(raw)
        return transcript, {
            "spoken_text": text,
            "raw_transcript": raw,
            "transcript": transcript,
            "tts_ms": round((synthesized - started) * 1000),
            "stt_ms": round((time.perf_counter() - synthesized) * 1000),
            "audio_seconds": signal.get("duration_seconds"),
            "synthetic_speech": True,
        }

    def run(self, step: Step) -> dict:
        record: dict = {"utterance": step.utterance, "voice": step.voice, "note": step.note}
        if step.wait_for is not None:
            ready = self.wait(step.wait_for, step.timeout)
            record["precondition_met"] = ready is not None
            if ready is None:
                record.update(passed=False, problem="precondition not reached")
                self.evidence.append(record)
                return record
        text = step.utterance
        if step.voice:
            text, voice = self.speak_and_transcribe(step.utterance)
            record["voice_path"] = voice
        before = self.observe()
        started = time.perf_counter()
        proposal = http_json(self.control + "/v1/actions/propose", {"instruction": text})
        record["propose_ms"] = round((time.perf_counter() - started) * 1000)
        action = (proposal.get("metadata") or {}).get("action") or {}
        record["reply"] = proposal.get("text", "")
        record["source"] = proposal.get("source", "")
        record["nl_path"] = ((proposal.get("metadata") or {}).get("nl") or {}).get("path", "")
        record["proposed_commands"] = action.get("commands", [])
        if not step.expect_proposal:
            passed = action.get("state") != "pending"
            record.update(passed=passed, problem="" if passed else "unexpected proposal", tick=before.tick,
                          order_count_before=before.order_count)
            self.evidence.append(record)
            return record
        if action.get("state") != "pending":
            record.update(passed=False, problem=f"no proposal: {proposal.get('text', '')[:200]}")
            self.evidence.append(record)
            return record
        confirmed = http_json(self.control + "/v1/actions/confirm", {"proposal_id": action["proposal_id"]})
        receipt = ((confirmed.get("metadata") or {}).get("action") or {}).get("receipt") or {}
        record["receipt"] = receipt
        record["confirm_state"] = ((confirmed.get("metadata") or {}).get("action") or {}).get("state")
        if not receipt.get("accepted"):
            record.update(passed=False, problem=f"engine rejected: {confirmed.get('text', '')[:200]}")
            self.evidence.append(record)
            return record
        record["receipt_tick"] = receipt.get("game_tick")
        problem = "verification missing"
        after = before
        deadline = time.monotonic() + step.timeout
        while time.monotonic() < deadline:
            after = self.observe()
            problem = step.verify(before, after, action) if step.verify else ""
            if not problem:
                break
            time.sleep(0.3)
        record.update(passed=not problem, problem=problem, verified_tick=after.tick, start_tick=before.tick)
        self.evidence.append(record)
        return record


# -- verification helpers ---------------------------------------------------------

def producing(item_hint: Callable[[str], bool]) -> Callable[[GameSnapshot, GameSnapshot, dict], str]:
    def check(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
        items = {command["item_type"] for command in action.get("commands", []) if command.get("item_type")}
        queued_before = sum(str(entry.get("item", "")).lower() in items for entry in before.production)
        queued_after = sum(str(entry.get("item", "")).lower() in items for entry in after.production)
        owned_before = sum(actor.kind.lower() in items for actor in (*before.units, *before.buildings))
        owned_after = sum(actor.kind.lower() in items for actor in (*after.units, *after.buildings))
        if queued_after > queued_before or owned_after > owned_before:
            return ""
        return f"{sorted(items)} not queued (queue {queued_before}->{queued_after}, owned {owned_before}->{owned_after})"
    return check


def building_placed(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
    items = {command["item_type"] for command in action.get("commands", []) if command.get("action") == "place_building"}
    count_before = sum(building.kind.lower() in items for building in before.buildings)
    count_after = sum(building.kind.lower() in items for building in after.buildings)
    return "" if count_after > count_before else f"{sorted(items)} not placed ({count_before}->{count_after})"


def base_deployed(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
    yards = [building for building in after.buildings if base(building.kind) in {"fact", "gacnst", "nacnst"}]
    return "" if yards else "no construction yard yet"


def units_moved_toward(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
    moved = 0
    for command in action.get("commands", []):
        if command.get("action") not in {"move", "attack_move"}:
            continue
        old = next((unit for unit in before.units if unit.actor_id == command["actor_id"]), None)
        new = next((unit for unit in after.units if unit.actor_id == command["actor_id"]), None)
        if old is None or new is None:
            continue
        target = (command["target_x"], command["target_y"])
        if math.dist((new.cell_x, new.cell_y), target) + 2 < math.dist((old.cell_x, old.cell_y), target) \
                or (new.move_target_x, new.move_target_y) == target:
            moved += 1
    return "" if moved else "no ordered unit progressed toward its target"


def rally_set(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
    for command in action.get("commands", []):
        building = next((item for item in after.buildings if item.actor_id == command["actor_id"]), None)
        if building is None or (building.rally_x, building.rally_y) != (command["target_x"], command["target_y"]):
            return f"rally is {(building.rally_x, building.rally_y) if building else None}"
    return ""


def stance_set(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
    for command in action.get("commands", []):
        unit = next((item for item in after.units if item.actor_id == command["actor_id"]), None)
        if unit is not None and unit.stance != command["target_x"]:
            return f"unit {unit.actor_id} stance {unit.stance} != {command['target_x']}"
    return ""


def stopped(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
    for command in action.get("commands", []):
        unit = next((item for item in after.units if item.actor_id == command["actor_id"]), None)
        if unit is not None and not unit.idle:
            return f"unit {unit.actor_id} still active ({unit.current_activity})"
    return ""


def harvesting(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
    for command in action.get("commands", []):
        unit = next((item for item in after.units if item.actor_id == command["actor_id"]), None)
        if unit is not None and unit.idle:
            return f"harvester {unit.actor_id} idle"
    return ""


def guarding(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
    for command in action.get("commands", []):
        unit = next((item for item in after.units if item.actor_id == command["actor_id"]), None)
        if unit is not None and "guard" not in unit.current_activity.lower() and unit.idle:
            return f"unit {unit.actor_id} not guarding ({unit.current_activity})"
    return ""


def cancelled(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
    items = {command["item_type"] for command in action.get("commands", [])}
    count_before = sum(str(entry.get("item", "")).lower() in items for entry in before.production)
    count_after = sum(str(entry.get("item", "")).lower() in items for entry in after.production)
    return "" if count_after < count_before else f"queue {count_before}->{count_after}"


def sold(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
    ids = {command["actor_id"] for command in action.get("commands", [])}
    remaining = [building for building in after.buildings if building.actor_id in ids]
    return "" if not remaining or after.cash > before.cash else "building still present"


def deployed_units(before: GameSnapshot, after: GameSnapshot, action: dict) -> str:
    for command in action.get("commands", []):
        old = next((item for item in before.units if item.actor_id == command["actor_id"]), None)
        new = next((item for item in after.units if item.actor_id == command["actor_id"]), None)
        if old is not None and new is not None and new.attack_range > old.attack_range:
            return ""
    return "no deployed weapon-range change observed"


def completed(kind_hint: tuple[str, ...]) -> Callable[[GameSnapshot], bool]:
    def ready(snapshot: GameSnapshot) -> bool:
        return any(
            any(hint in str(entry.get("item", "")).lower() for hint in kind_hint)
            and (float(entry.get("progress", 0)) >= 0.999 or int(entry.get("remaining_ticks", 1)) <= 0)
            for entry in snapshot.production
        )
    return ready


def has_units(kind_hint: tuple[str, ...], minimum: int = 1) -> Callable[[GameSnapshot], bool]:
    return lambda snapshot: sum(base(unit.kind) in kind_hint for unit in snapshot.units) >= minimum


def has_building(kind_hint: tuple[str, ...]) -> Callable[[GameSnapshot], bool]:
    return lambda snapshot: any(base(building.kind) in kind_hint for building in snapshot.buildings)


def steps_classic(session: Session) -> list[Step]:
    def base_cell(dx: int, dy: int) -> str:
        snapshot = session.observe()
        yard = next((building for building in snapshot.buildings if base(building.kind) == "fact"), None)
        x = (yard.cell_x if yard else snapshot.map_width // 2) + dx
        y = (yard.cell_y if yard else snapshot.map_height // 2) + dy
        return f"{x},{y}"

    return [
        Step("deploy the MCV", base_deployed, timeout=30),
        Step("build a power plant", producing(lambda item: True), wait_for=has_building(("fact",)), timeout=20),
        Step("place the power plant", building_placed, wait_for=completed(("powr",)), timeout=90),
        Step("build a barracks", producing(lambda item: True), timeout=20),
        Step("put it down", building_placed, wait_for=completed(("tent", "barr")), timeout=120, note="pronoun via the model path"),
        Step("build an ore refinery", producing(lambda item: True), timeout=20),
        Step("train three rifle infantry", producing(lambda item: True), timeout=20),
        Step("place the refinery", building_placed, wait_for=completed(("proc",)), timeout=180),
        Step("build a power plant", producing(lambda item: True), timeout=20),
        Step("place the power plant", building_placed, wait_for=completed(("powr",)), timeout=120),
        Step("build a war factory", producing(lambda item: True), timeout=20),
        Step("__rally__", None),
        Step("__move__", None),
        Step("send the harvester back to work", harvesting, wait_for=has_units(("harv",)), timeout=30),
        Step("place the war factory", building_placed, wait_for=completed(("weap",)), timeout=240),
        Step("train two light tanks", producing(lambda item: True), timeout=20),
        Step("stop the rifle infantry", stopped, wait_for=has_units(("e1",), 3), timeout=30),
        Step("set the rifle infantry to hold fire", stance_set, timeout=15),
        Step("__tanks_move__", None),
        Step("move the tanks north", units_moved_toward, timeout=45, note="relative direction via the model path"),
        Step("guard the ore truck with the light tanks", guarding, timeout=30),
        Step("train two rifle infantry", producing(lambda item: True), timeout=20, voice=True),
        Step("cancel the rifle infantry", cancelled, timeout=15),
        Step("__voice_move__", None),
        Step("stop the light tanks", stopped, timeout=30, voice=True),
        Step("sell the power plant", sold, timeout=30),
        Step("surrender", None, expect_proposal=False),
        Step("launch the nuke at their base", None, expect_proposal=False),
    ], base_cell


def steps_ra2(session: Session) -> list[Step]:
    def base_cell(dx: int, dy: int) -> str:
        snapshot = session.observe()
        yard = next((building for building in snapshot.buildings if base(building.kind) in {"gacnst", "nacnst"}), None)
        x = (yard.cell_x if yard else snapshot.map_width // 2) + dx
        y = (yard.cell_y if yard else snapshot.map_height // 2) + dy
        return f"{x},{y}"

    return [
        Step("deploy the MCV", base_deployed, timeout=40),
        Step("build a power plant", producing(lambda item: True), wait_for=has_building(("gacnst", "nacnst")), timeout=30),
        Step("place the power plant", building_placed, wait_for=completed(("powr",)), timeout=150),
        Step("build a barracks", producing(lambda item: True), timeout=20),
        Step("put it down", building_placed, wait_for=completed(("gapile", "nahand")), timeout=180, note="pronoun via the model path"),
        Step("train three G.I.s", producing(lambda item: True), timeout=20),
        Step("__rally__", None),
        Step("__move__", None),
        Step("deploy the GIs", deployed_units, wait_for=has_units(("e1",), 2), timeout=60),
        Step("stop the GIs", stopped, timeout=30),
        Step("train two GIs", producing(lambda item: True), timeout=20, voice=True),
        Step("__voice_move__", None),
        Step("build an ore refinery", producing(lambda item: True), timeout=20),
        Step("use the chronosphere on their base", None, expect_proposal=False),
    ], base_cell


def expand(steps: list[Step], base_cell, mod: str) -> list[Step]:
    """Materialize coordinate steps from the live base location."""
    infantry = "rifle infantry" if mod == "ra" else "GIs"
    result: list[Step] = []
    for step in steps:
        if step.utterance == "__rally__":
            producer = "barracks"
            result.append(Step(f"set the {producer} rally point to {base_cell(4, 6)}", rally_set, timeout=15))
        elif step.utterance == "__move__":
            result.append(Step(f"move the {infantry} to {base_cell(-5, 4)}", units_moved_toward, timeout=40))
        elif step.utterance == "__tanks_move__":
            result.append(Step(f"light tanks attack move to {base_cell(3, -5)}", units_moved_toward, timeout=45,
                               wait_for=has_units(("1tnk",), 1)))
        elif step.utterance == "__voice_move__":
            cell = base_cell(-3, -3).split(",")
            result.append(Step(f"move the {infantry} to {cell[0]} {cell[1]}", units_moved_toward, timeout=40, voice=True))
        else:
            result.append(step)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--router-url", required=True)
    parser.add_argument("--mod", choices=("ra", "ra2"), default="ra")
    parser.add_argument("--map", default="")
    parser.add_argument("--faction", default="")
    parser.add_argument("--enemy", default="")
    parser.add_argument("--opponent", default="beginner")
    parser.add_argument("--work", type=Path, default=REPOSITORY / ".artifacts" / "nl-orders" / "e2e")
    parser.add_argument("--evidence", type=Path, default=None)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = (args.work / f"{args.mod}-{stamp}").resolve()
    map_name = args.map or ("desert-rats" if args.mod == "ra" else "little-big-lake")
    faction = args.faction or ("england" if args.mod == "ra" else "america")
    enemy = args.enemy or ("russia" if args.mod == "ra" else "russia")
    opponent = args.opponent if args.mod == "ra" else (args.opponent if args.opponent != "beginner" else "turtle")
    match = LiveMatch("companion", args.mod, map_name, work / "match", player_faction=faction, enemy_faction=enemy,
                      opponent=opponent, shared_root=work.parent / "shared-content")
    control_port = free_port()
    watch = None
    session = None
    try:
        match.start()
        settings_dir = work / "appdata" / "OpenRA-AI"
        settings_dir.mkdir(parents=True, exist_ok=True)
        (settings_dir / "settings.json").write_text(json.dumps({
            "router_url": args.router_url, "model_provider": "local", "text_model": "local-coder",
            "vision_model": "local-no-vision", "transcribe_model": "local-whisper", "speech_model": "local-kokoro",
            "auto_act_enabled": False, "voice_enabled": False, "companion_enabled": True,
        }), encoding="utf-8")
        environment = {key: value for key, value in os.environ.items() if not key.startswith("OPENRA_AI_")}
        environment.pop("OPENAI_API_KEY", None)
        environment.update({
            "APPDATA": str(work / "appdata"),
            "PYTHONPATH": os.pathsep.join([str(REPOSITORY / "services" / "companion" / "src"),
                                           str(REPOSITORY / "services" / "worldgen" / "src")]),
            "OPENRA_AI_ROUTER_URL": args.router_url,
            "OPENRA_AI_AGENT_ROUTER_URL": args.router_url,
            "OPENRA_AI_AGENT_PROVIDER": "local",
            "OPENRA_AI_AGENT_MODEL": "local-coder",
            "OPENRA_AI_BRAIN_STATE": str(work / "brain-blackboard.jsonl"),
            "OPENRA_AI_ENGINE_DIR": str(match.engine),
            "PYTHONIOENCODING": "utf-8",
        })
        log = (work / "companion-watch.log").open("wb")
        watch = subprocess.Popen(
            [sys.executable, "-m", "openra_ai_companion.cli", "watch", "--bridge", f"127.0.0.1:{match.port}",
             "--no-speak", "--control-port", str(control_port), "--worldgen-port", str(free_port()),
             "--game-pid", str(match.process.pid), "--mission-output", str(work / "missions")],
            env=environment, cwd=str(REPOSITORY), stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        control = f"http://127.0.0.1:{control_port}"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                health = http_json(control + "/health", timeout=2)
                if health.get("control_ready") and health.get("has_snapshot"):
                    break
            except (OSError, urllib.error.URLError, json.JSONDecodeError):
                pass
            time.sleep(0.5)
        session = Session(match, control, args.router_url.rstrip("/"))
        raw_steps, base_cell = (steps_classic if args.mod == "ra" else steps_ra2)(session)
        for step in raw_steps:
            for concrete in expand([step], base_cell, args.mod):
                record = session.run(concrete)
                status = "PASS" if record.get("passed") else "FAIL"
                transcript = record.get("voice_path", {}).get("transcript", "")
                print(f"{status} {concrete.utterance!r}{' (voice: ' + repr(transcript) + ')' if transcript else ''} "
                      f"[{record.get('nl_path', '')} {record.get('propose_ms', 0)}ms] {record.get('problem', '')}", flush=True)
    finally:
        evidence = {
            "mod": args.mod, "map": map_name, "player_faction": faction, "enemy_faction": enemy, "opponent": opponent,
            "router_url": args.router_url, "started": stamp,
            "synthetic_speech": "voice steps use local Kokoro speech transcribed by local Whisper; no human voice",
            "steps": session.evidence if session else [],
        }
        if session:
            evidence["passed"] = sum(bool(record.get("passed")) for record in session.evidence)
            evidence["total"] = len(session.evidence)
        target = args.evidence or (work / "evidence.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(evidence, indent=1) + "\n", encoding="utf-8")
        print(f"evidence: {target}")
        if watch is not None and watch.poll() is None:
            watch.terminate()
            try:
                watch.wait(timeout=10)
            except subprocess.TimeoutExpired:
                watch.kill()
        match.stop()
    return 0 if session and all(record.get("passed") for record in session.evidence) else 1


if __name__ == "__main__":
    raise SystemExit(main())
