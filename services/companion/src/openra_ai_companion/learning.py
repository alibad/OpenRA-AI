from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .labels import production_name


_STORE_LOCK = threading.Lock()


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_learning_dir() -> Path:
    configured = os.environ.get("OPENRA_AI_LEARNING_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else workspace_root() / ".artifacts" / "autoplay" / "learning"


def _json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _timeline(events: list[dict[str, Any]], rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for event in events:
        kind = str(event.get("event", ""))
        tick = int(event.get("tick", 0))
        if kind == "decision":
            timeline.append({
                "tick": tick,
                "type": "decision",
                "decision": str(event.get("decision", "")),
                "evidence": str(event.get("evidence", "")),
                "expected_result": str(event.get("expected_result", "")),
            })
        elif kind == "commands":
            commands = event.get("queued", [])
            if not isinstance(commands, list):
                continue
            descriptions = []
            for command in commands:
                if not isinstance(command, dict):
                    continue
                action = str(command.get("action", "unknown"))
                item = str(command.get("item_type", "")).strip()
                target = int(command.get("target_actor_id", 0))
                cell = [int(command.get("target_x", 0)), int(command.get("target_y", 0))]
                descriptions.append({
                    "action": action,
                    **({"item": item} if item else {}),
                    **({"target_actor": target} if target else {}),
                    **({"target_cell": cell} if cell != [0, 0] else {}),
                    **({"actors": 1} if int(command.get("actor_id", 0)) else {}),
                })
            timeline.append({
                "tick": tick,
                "type": "orders",
                "orders": descriptions,
                "economy": event.get("economy", {}),
            })
        elif kind == "advance" and (event.get("interrupt_reason") or event.get("done")):
            timeline.append({
                "tick": tick,
                "type": "event",
                "event": str(event.get("interrupt_reason") or event.get("result") or "match complete"),
                "economy": event.get("economy", {}),
                "military": event.get("military", {}),
            })

    for round_record in rounds:
        if round_record.get("error") or round_record.get("turn_budget_exhausted") or round_record.get("done"):
            timeline.append({
                "tick": int(round_record.get("tick", 0)),
                "type": "round_review",
                "round": int(round_record.get("round", 0)),
                "budget_exhausted": bool(round_record.get("turn_budget_exhausted")),
                "error": str(round_record.get("error", "")),
                "note": str(round_record.get("note", ""))[:500],
            })
    return sorted(timeline, key=lambda item: (item["tick"], item["type"]))


def review_match(evidence_dir: Path, outcome: dict[str, Any]) -> dict[str, Any]:
    events = _json_lines(evidence_dir / "tool-events.jsonl")
    rounds = _json_lines(evidence_dir / "agent-rounds.jsonl")
    frames = _json_lines(evidence_dir / "frames.jsonl")
    commands = [
        command
        for event in events
        if event.get("event") == "commands"
        for command in event.get("queued", [])
        if isinstance(command, dict)
    ]
    actions = Counter(str(command.get("action", "unknown")) for command in commands)
    built = Counter(
        str(command.get("item_type", "unknown"))
        for command in commands
        if command.get("action") == "build"
    )
    trained = Counter(
        str(command.get("item_type", "unknown"))
        for command in commands
        if command.get("action") == "train"
    )
    silo_build_ticks = [
        int(event.get("tick", 0))
        for event in events
        if event.get("event") == "commands"
        and any(
            isinstance(command, dict)
            and command.get("action") == "build"
            and command.get("item_type") == "silo"
            for command in event.get("queued", [])
        )
    ]
    samples = [event for event in events if event.get("event") in {"battlefield", "commands", "advance"}]
    economies = [event.get("economy", {}) for event in samples if isinstance(event.get("economy"), dict)]
    militaries = [event.get("military", {}) for event in samples if isinstance(event.get("military"), dict)]
    peak_live_siege = max(
        (
            int(event.get("counts", {}).get("own_units", {}).get("Artillery", 0))
            + int(event.get("counts", {}).get("own_units", {}).get("V2 Rocket Launcher", 0))
            for event in events
            if isinstance(event.get("counts"), dict)
            and isinstance(event.get("counts", {}).get("own_units"), dict)
        ),
        default=0,
    )
    storage_peak = max((float(sample.get("storage_percent", 0)) for sample in economies), default=0)
    cash_values = [int(sample.get("cash", 0)) for sample in economies]
    harvester_values = [int(sample.get("harvesters", 0)) for sample in economies]
    final = outcome.get("snapshot", {}) if isinstance(outcome.get("snapshot"), dict) else {}
    final_military = final.get("military", {}) if isinstance(final.get("military"), dict) else {}
    final_economy = final.get("economy", {}) if isinstance(final.get("economy"), dict) else {}
    kills_cost = int(final_military.get("kills_cost", 0))
    deaths_cost = int(final_military.get("deaths_cost", 0))
    budget_exhaustions = sum(bool(record.get("turn_budget_exhausted")) for record in rounds)
    won = bool(outcome.get("won") and str(outcome.get("result", "")).lower() == "win")
    result = str(outcome.get("result", "incomplete")) or "incomplete"
    infrastructure_failure = result in {"launcher_timeout", "engine_failure", "controller_failure"}
    strategy_reset = result == "strategy_reset"
    state = outcome.get("state", {}) if isinstance(outcome.get("state"), dict) else {}

    strengths: list[str] = []
    improvements: list[str] = []
    if {"powr", "apwr"} & set(built) and "proc" in built and "weap" in built:
        strengths.append("Established power, refinery, and vehicle production.")
    if max(harvester_values, default=int(final_economy.get("harvesters", 0))) >= 3:
        strengths.append("Reached a three-harvester economy.")
    if int(final_military.get("buildings_killed", 0)) >= 3:
        strengths.append("Converted the army into meaningful enemy-structure damage.")
    if kills_cost > deaths_cost and deaths_cost >= 0:
        strengths.append("Finished with a positive combat-value exchange.")
    if won:
        strengths.append("Verified the win from the engine's terminal match result.")
    if trained.get("v2rl") and int(final_military.get("buildings_killed", 0)) >= 3:
        strengths.append("Protected siege units long enough to dismantle multiple enemy structures.")

    if storage_peak > 80 and not built.get("silo"):
        improvements.append("Build a silo as soon as stored ore exceeds 80% capacity so harvesters do not stall.")
    if any(right - left < 500 for left, right in zip(silo_build_ticks, silo_build_ticks[1:])):
        improvements.append("Build exactly one silo per storage episode, then re-read the increased capacity before considering another.")
    if max(harvester_values, default=0) < 2:
        improvements.append("Reach at least two harvesters before sustained combat production.")
    if int(final_military.get("buildings_killed", 0)) == 0:
        improvements.append("Scout until an enemy base is located, then attack production and economy structures with a concentrated force.")
    if not won and int(final_military.get("buildings_killed", 0)) <= 2 and int(final_military.get("units_lost", 0)) >= 8:
        improvements.append("Keep infantry outside Tesla/Flame/Pillbox range and let protected siege weapons destroy static defenses first.")
    if not won and int(final_military.get("buildings_killed", 0)) >= 1 and int(final_military.get("units_lost", 0)) > int(final_military.get("units_killed", 0)):
        improvements.append("After destroying the Construction Yard, drive surviving armor onto War Factories/Barracks instead of grinding through replaceable APC and infantry screens.")
    if not won and outcome.get("opponent") == "normal" and int(final_military.get("units_lost", 0)) >= 20:
        improvements.append("On Normal, delay the main assault until at least four durable tanks, ten screening infantry, and protected siege are assembled.")
    if (
        not won
        and int(final_military.get("buildings_killed", 0)) >= 3
        and int(final_military.get("units_lost", 0)) >= 15
        and peak_live_siege < 2
    ):
        improvements.append("Against a defended base, assemble two protected siege units and queue a replacement before probing the Tesla/Flame/Pillbox line.")
    if deaths_cost > kills_cost:
        improvements.append("Improve force concentration and target selection; lost unit value exceeded destroyed enemy value.")
    if not won and not infrastructure_failure and not strategy_reset and int(final_military.get("army_value", 0)) >= 5000:
        improvements.append("Commit the assembled army earlier and keep it together instead of ending with unused combat value.")
    if int(final_military.get("units_lost", 0)) >= 20:
        improvements.append("Preserve opening scouts and screen siege units; early piecemeal attacks caused excessive attrition.")
    if (
        int(final_military.get("units_lost", 0)) > int(final_military.get("units_killed", 0))
        and trained.get("e3", 0) > 0
        and trained.get("e2", 0) == 0
        and state.get("player_faction") in {"russia", "ukraine"}
    ):
        improvements.append("Against infantry-heavy contact, screen Soviet siege with Grenadiers instead of overproducing anti-armor Rocket Soldiers.")
    combat_trained = Counter({kind: count for kind, count in trained.items() if kind not in {"harv", "mcv", "tran"}})
    total_combat_trained = sum(combat_trained.values())
    if total_combat_trained >= 8:
        dominant_kind, dominant_count = combat_trained.most_common(1)[0]
        if dominant_count / total_combat_trained > 0.6:
            improvements.append(
                f"Correct the {production_name(dominant_kind)} production monoculture with OpenRA's weighted mixed-force plan and visible-enemy counters."
            )
    if not won and int(final_military.get("units_lost", 0)) >= 20 and int(final_military.get("buildings_killed", 0)) <= 2:
        improvements.append("After aborting an assault, retreat behind the base-side War Factory/Service Depot before rebuilding; a midpoint staging line is still exposed to reinforcements.")
    if any(item.startswith("afld") for item in built) and not built.get("fix") and not trained.get("3tnk") and state.get("player_faction") in {"russia", "ukraine"}:
        improvements.append("Use the Service Depot (`fix`) to unlock Soviet Heavy Tanks; an Airfield unlocks aircraft, not armor.")
    if infrastructure_failure:
        improvements.append("Run the next match without an external launcher watchdog so OpenRA can emit a terminal result.")
    if rounds and budget_exhaustions / len(rounds) >= 0.5:
        improvements.append("Batch related orders and use longer safe advances; too many decision rounds exhausted their tool budget.")
    if not won and not improvements:
        improvements.append("Increase scouting coverage, preserve the economy, and focus the main force on enemy production before attrition sets in.")

    return {
        "attempt_id": evidence_dir.name,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "won": won,
        "result": result,
        "map": str(outcome.get("map_name", final.get("map", "unknown"))),
        "opponent": str(outcome.get("opponent", "unknown")),
        "model": str(outcome.get("model", "unknown")),
        "policy_id": str(outcome.get("policy_id", "baseline")),
        "safety_violations": int(outcome.get("safety_violations", 0)),
        "seed": int(outcome.get("seed", 0)),
        "tick": int(outcome.get("tick", 0)),
        "rounds": int(outcome.get("rounds", len(rounds))),
        "factions": {
            "player": str(state.get("player_faction", "unknown")),
            "enemy": str(state.get("enemy_faction", "unknown")),
        },
        "decisions": {
            "logged_rationales": sum(event.get("event") == "decision" for event in events),
            "orders": len(commands),
            "action_counts": dict(sorted(actions.items())),
            "builds": dict(sorted(built.items())),
            "units_trained": dict(sorted(trained.items())),
            "turn_budget_exhaustions": budget_exhaustions,
        },
        "resources": {
            "peak_cash": max(cash_values, default=int(final_economy.get("cash", 0))),
            "average_harvesters": round(sum(harvester_values) / len(harvester_values), 2) if harvester_values else 0,
            "peak_harvesters": max(harvester_values, default=int(final_economy.get("harvesters", 0))),
            "peak_storage_percent": round(storage_peak, 1),
            "final_economy": final_economy,
            "final_military": final_military,
            "combat_value_ratio": round(kills_cost / max(1, deaths_cost), 2),
            "peak_army_value": max((int(sample.get("army_value", 0)) for sample in militaries), default=0),
        },
        "assessment": {
            "strengths": strengths,
            "improvements": improvements,
        },
        "visual_evidence": {
            "frame_count": len(frames),
            "periodic_interval_ticks": 125,
            "periodic_interval_seconds": 5,
            "reasons": dict(sorted(Counter(str(frame.get("reason", "unknown")) for frame in frames).items())),
            "recent_frames": frames[-20:],
        },
        "timeline": _timeline(events, rounds),
        "evidence_dir": str(evidence_dir.resolve()),
    }


class LearningStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_learning_dir()).resolve()
        self.matches_dir = self.root / "matches"
        self.history_path = self.root / "history.jsonl"
        self.summary_path = self.root / "summary.json"
        self.policies_path = self.root / "policies.json"

    def policies(self) -> dict[str, Any]:
        value = _read_json(self.policies_path)
        return value if value else {"active_policy": "baseline", "candidates": {}}

    def propose_policy(
        self,
        candidate_id: str,
        parameters: dict[str, Any],
        *,
        baseline_id: str = "baseline",
        rationale: str = "",
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", candidate_id):
            raise ValueError("invalid policy candidate id")
        state = self.policies()
        candidate = {
            "candidate_id": candidate_id,
            "baseline_id": baseline_id,
            "parameters": dict(parameters),
            "rationale": rationale[:500],
            "status": "candidate",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "evaluation": {},
        }
        state.setdefault("candidates", {})[candidate_id] = candidate
        with _STORE_LOCK:
            self.root.mkdir(parents=True, exist_ok=True)
            self.policies_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return candidate

    def evaluate_policy(self, candidate_id: str, *, minimum_games: int = 3) -> dict[str, Any]:
        state = self.policies()
        candidate = state.get("candidates", {}).get(candidate_id)
        if not isinstance(candidate, dict):
            raise ValueError("unknown policy candidate")
        records = self.records()
        candidate_records = [record for record in records if record.get("policy_id") == candidate_id]
        baseline_id = str(candidate.get("baseline_id", "baseline"))
        baseline_records = [record for record in records if record.get("policy_id", "baseline") == baseline_id]

        def rate(values: list[dict[str, Any]]) -> float:
            return sum(bool(value.get("won")) for value in values) / max(1, len(values))

        candidate_rate = rate(candidate_records)
        baseline_rate = rate(baseline_records)
        safety_violations = sum(int(record.get("safety_violations", 0)) for record in candidate_records)
        enough_games = len(candidate_records) >= max(3, minimum_games)
        materially_better = candidate_rate >= max(2 / 3, baseline_rate + 0.05)
        passed = enough_games and materially_better and safety_violations == 0
        evaluation = {
            "games": len(candidate_records),
            "wins": sum(bool(record.get("won")) for record in candidate_records),
            "win_rate": round(candidate_rate * 100, 1),
            "baseline_games": len(baseline_records),
            "baseline_win_rate": round(baseline_rate * 100, 1),
            "safety_violations": safety_violations,
            "gates": {
                "minimum_games": enough_games,
                "material_win_rate_gain": materially_better,
                "zero_safety_violations": safety_violations == 0,
            },
            "passed": passed,
            "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        candidate["evaluation"] = evaluation
        candidate["status"] = "promoted" if passed else "candidate"
        if passed:
            state["active_policy"] = candidate_id
        with _STORE_LOCK:
            self.root.mkdir(parents=True, exist_ok=True)
            self.policies_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return evaluation

    def records(self) -> list[dict[str, Any]]:
        return _json_lines(self.history_path)

    def import_existing(self) -> int:
        """One-time migration of earlier autoplay evidence into the persistent learning feed."""
        if self.history_path.is_file():
            return 0
        candidates = sorted(self.root.parent.glob("*/outcome.json"))
        imported: list[dict[str, Any]] = []
        for outcome_path in candidates:
            evidence_dir = outcome_path.parent
            if evidence_dir == self.root or not (evidence_dir / "tool-events.jsonl").is_file():
                continue
            outcome = _read_json(outcome_path)
            if outcome:
                imported.append(review_match(evidence_dir, outcome))
        if not imported:
            return 0
        with _STORE_LOCK:
            self.matches_dir.mkdir(parents=True, exist_ok=True)
            with self.history_path.open("w", encoding="utf-8") as history:
                for record in imported:
                    (self.matches_dir / f"{record['attempt_id']}.json").write_text(
                        json.dumps(record, indent=2) + "\n", encoding="utf-8"
                    )
                    history.write(json.dumps(record, separators=(",", ":")) + "\n")
            self.summary_path.write_text(
                json.dumps(self._summarize(imported), indent=2) + "\n", encoding="utf-8"
            )
        return len(imported)

    def dashboard(self) -> dict[str, Any]:
        self.import_existing()
        return {**self._summarize(self.records()), "policies": self.policies()}

    def match(self, attempt_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", attempt_id):
            raise ValueError("invalid learning attempt id")
        return _read_json(self.matches_dir / f"{attempt_id}.json")

    def latest(self) -> dict[str, Any]:
        dashboard = self.dashboard()
        attempt = dashboard.get("latest_attempt", {})
        return self.match(str(attempt.get("attempt_id", ""))) if attempt else {}

    def context(self, map_name: str, opponent: str, limit: int = 3) -> str:
        self.import_existing()
        records = self.records()
        usable = [
            record for record in records
            if record.get("result") != "strategy_reset" or int(record.get("rounds", 0)) >= 5
        ]
        exact = [
            record for record in usable
            if record.get("map") == map_name and record.get("opponent") == opponent
        ]
        relevant = exact[-limit:]
        if len(relevant) < limit:
            selected_ids = {record.get("attempt_id") for record in relevant}
            transferable = [
                record for record in usable
                if record.get("map") == map_name and record.get("attempt_id") not in selected_ids
            ]
            relevant = (transferable[-(limit - len(relevant)):] + relevant)[-limit:]
        if not relevant:
            return "No prior learning records exist for this map and difficulty."
        lessons = []
        for record in relevant:
            result = "win" if record.get("won") else "loss/incomplete"
            improvements = record.get("assessment", {}).get("improvements", [])
            lessons.append({
                "attempt": record.get("attempt_id"),
                "result": result,
                "difficulty": record.get("opponent"),
                "tick": record.get("tick", 0),
                "lessons": improvements[:4],
            })
        return json.dumps(lessons, separators=(",", ":"))

    def record(self, evidence_dir: Path, outcome: dict[str, Any]) -> dict[str, Any]:
        record = review_match(evidence_dir.resolve(), outcome)
        with _STORE_LOCK:
            self.matches_dir.mkdir(parents=True, exist_ok=True)
            (self.matches_dir / f"{record['attempt_id']}.json").write_text(
                json.dumps(record, indent=2) + "\n", encoding="utf-8"
            )
            self.root.mkdir(parents=True, exist_ok=True)
            records = self.records()
            replaced = False
            for index, existing in enumerate(records):
                if existing.get("attempt_id") == record["attempt_id"]:
                    records[index] = record
                    replaced = True
                    break
            if not replaced:
                records.append(record)
            self.history_path.write_text(
                "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in records),
                encoding="utf-8",
            )
            summary = self._summarize(records)
            self.summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return record

    @staticmethod
    def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
        wins = sum(bool(record.get("won")) for record in records)
        by_difficulty: dict[str, dict[str, Any]] = {}
        for record in records:
            difficulty = str(record.get("opponent", "unknown"))
            bucket = by_difficulty.setdefault(difficulty, {"attempts": 0, "wins": 0})
            bucket["attempts"] += 1
            bucket["wins"] += int(bool(record.get("won")))
        for bucket in by_difficulty.values():
            bucket["win_rate"] = round(bucket["wins"] / max(1, bucket["attempts"]) * 100, 1)
        latest = records[-1] if records else None
        latest_summary = ({key: value for key, value in latest.items() if key not in {"timeline", "evidence_dir"}}
                          if latest else None)
        return {
            "attempts": len(records),
            "wins": wins,
            "losses_or_incomplete": len(records) - wins,
            "win_rate": round(wins / max(1, len(records)) * 100, 1),
            "by_difficulty": by_difficulty,
            "latest_lessons": latest.get("assessment", {}) if latest else {},
            "latest_attempt": latest_summary,
            "recent_attempts": [
                {
                    "attempt_id": record.get("attempt_id"),
                    "recorded_at": record.get("recorded_at"),
                    "won": record.get("won"),
                    "result": record.get("result"),
                    "opponent": record.get("opponent"),
                    "map": record.get("map"),
                    "tick": record.get("tick"),
                    "rounds": record.get("rounds"),
                }
                for record in records[-10:][::-1]
            ],
        }


def learning_dashboard(root: Path | None = None) -> dict[str, Any]:
    return LearningStore(root).dashboard()
