from __future__ import annotations

import argparse
import json
from pathlib import Path


def grade(evidence_dir: Path) -> dict:
    outcome_path = evidence_dir / "outcome.json"
    events_path = evidence_dir / "tool-events.jsonl"
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    commands = [
        command
        for event in events
        if event.get("event") == "commands"
        for command in event.get("queued", [])
    ]
    actions = [str(command.get("action", "")) for command in commands]
    built = {str(command.get("item_type", "")) for command in commands if command.get("action") == "build"}
    checks = {
        "engine_reported_win": bool(outcome.get("won") and str(outcome.get("result", "")).lower() == "win"),
        "deployed_starting_base": "deploy" in actions,
        "built_power": bool({"powr", "apwr"} & built),
        "built_refinery": "proc" in built,
        "trained_units": "train" in actions,
        "issued_combat_orders": bool({"attack", "attack_move"} & set(actions)),
        "advanced_simulation": any(event.get("event") == "advance" for event in events),
        "never_surrendered": "surrender" not in actions,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "commands": len(commands),
        "events": len(events),
        "tick": outcome.get("tick", 0),
        "session_id": outcome.get("session_id", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade a real OpenRA autonomous-match evidence directory")
    parser.add_argument("evidence_dir", type=Path)
    args = parser.parse_args()
    result = grade(args.evidence_dir.resolve())
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
