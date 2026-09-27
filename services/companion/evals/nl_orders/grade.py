"""Automatic grading for natural-language order evaluation results.

The grader resolves every expectation against the captured fixture with its
own simple selectors (it deliberately does not import the interpreter), then
checks the proposal that the companion actually left pending.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[3]
FIXTURES = HERE / "fixtures"

sys.path.insert(0, str(REPOSITORY / "services" / "companion" / "src"))

from openra_ai_companion.models import GameSnapshot, Unit  # noqa: E402


def load_fixture(name: str) -> tuple[GameSnapshot, dict]:
    payload = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return GameSnapshot.from_dict(payload["observation"]), payload


# -- independent selectors ------------------------------------------------------

def _base(kind: str) -> str:
    return kind.lower().split("@", 1)[0].split(".", 1)[0]


def _harvester(snapshot: GameSnapshot, unit: Unit) -> bool:
    name = snapshot.actor_name(unit.kind).lower()
    return _base(unit.kind) in {"harv", "cmin"} or "ore truck" in name or "miner" in name or "harvester" in name


def _mcv(snapshot: GameSnapshot, unit: Unit) -> bool:
    return _base(unit.kind) in {"mcv", "amcv", "smcv"} or "construction vehicle" in snapshot.actor_name(unit.kind).lower()


def _mobile(snapshot: GameSnapshot) -> list[Unit]:
    return [unit for unit in snapshot.units if "husk" not in unit.kind.lower() and unit.speed > 0]


def select(snapshot: GameSnapshot, spec: dict) -> list[Unit]:
    units = _mobile(snapshot)
    if "types" in spec:
        wanted = {kind.lower() for kind in spec["types"]}
        return [unit for unit in [*units, *snapshot.buildings] if unit.kind.lower() in wanted]
    name = spec["class"]
    if name == "mcv":
        return [unit for unit in units if _mcv(snapshot, unit)]
    if name == "harvester":
        return [unit for unit in units if _harvester(snapshot, unit)]
    if name == "combat":
        return [unit for unit in units if unit.can_attack and not _harvester(snapshot, unit) and not _mcv(snapshot, unit)]
    if name == "non_economy":
        return [unit for unit in units if not _harvester(snapshot, unit) and not _mcv(snapshot, unit)]
    raise ValueError(f"unknown class {name}")


def _centroid(actors: list[Unit]) -> tuple[float, float] | None:
    if not actors:
        return None
    return (sum(actor.cell_x for actor in actors) / len(actors), sum(actor.cell_y for actor in actors) / len(actors))


def anchor(snapshot: GameSnapshot, name: str) -> tuple[float, float] | None:
    if name == "own_base":
        yards = [building for building in snapshot.buildings if _base(building.kind) in {"fact", "gacnst", "nacnst"}]
        return _centroid(yards) or _centroid(list(snapshot.buildings))
    if name == "enemy_base":
        return _centroid(list(snapshot.visible_enemy_buildings)) or _centroid(list(snapshot.remembered_enemy_buildings))
    if name == "visible_enemies":
        return _centroid(list(snapshot.visible_enemies))
    if name.startswith("building:"):
        kind = name.split(":", 1)[1]
        return _centroid([building for building in snapshot.buildings if building.kind.lower() == kind])
    raise ValueError(name)


DIRECTION_VECTORS = {
    "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
    "northeast": (1, -1), "northwest": (-1, -1), "southeast": (1, 1), "southwest": (-1, 1),
}


def _target_ok(snapshot: GameSnapshot, spec: dict, command: dict, actors: list[Unit]) -> str:
    """Return an empty string when the command satisfies the target spec, else a reason."""
    if "cell" in spec:
        expected = tuple(spec["cell"])
        actual = (command.get("target_x"), command.get("target_y"))
        return "" if actual == expected else f"target {actual} != {expected}"
    if "near" in spec:
        point = anchor(snapshot, spec["near"])
        if point is None:
            return f"anchor {spec['near']} unavailable"
        distance = math.dist(point, (command.get("target_x", 0), command.get("target_y", 0)))
        return "" if distance <= spec.get("radius", 6) else f"target {distance:.1f} cells from {spec['near']}"
    if "direction" in spec:
        origin = _centroid(actors) or anchor(snapshot, "own_base") or (0, 0)
        dx = command.get("target_x", 0) - origin[0]
        dy = command.get("target_y", 0) - origin[1]
        ex, ey = DIRECTION_VECTORS[spec["direction"]]
        length = math.hypot(dx, dy)
        if length < 3:
            return "direction target too close"
        cosine = (dx * ex + dy * ey) / (length * math.hypot(ex, ey))
        if not snapshot.contains_cell(command.get("target_x", -1), command.get("target_y", -1)):
            return "direction target outside map"
        return "" if cosine >= math.cos(math.radians(50)) else f"direction off by {math.degrees(math.acos(max(-1, min(1, cosine)))):.0f}deg"
    if "enemy_types" in spec:
        wanted = {kind.lower() for kind in spec["enemy_types"]}
        target = next((actor for actor in (*snapshot.visible_enemies, *snapshot.visible_enemy_buildings)
                       if actor.actor_id == command.get("target_actor_id")), None)
        if target is None:
            return "attack target is not a visible enemy"
        return "" if target.kind.lower() in wanted else f"attacked {target.kind}"
    if "own_types" in spec:
        wanted = {kind.lower() for kind in spec["own_types"]}
        target = next((actor for actor in (*snapshot.units, *snapshot.buildings)
                       if actor.actor_id == command.get("target_actor_id")), None)
        if target is None:
            return "target is not an owned actor"
        return "" if target.kind.lower() in wanted else f"target {target.kind}"
    if "valid_field" in spec:
        subject = next((unit for unit in snapshot.units if unit.actor_id == command.get("actor_id")), None)
        allowed = set(getattr(subject, spec["valid_field"])) if subject else set()
        if command.get("target_actor_id") not in allowed:
            return "target not in the unit's valid targets"
        wanted = {kind.lower() for kind in spec.get("target_types", [])}
        if wanted:
            everyone = {actor.actor_id: actor for actor in (*snapshot.visible_enemies, *snapshot.visible_enemy_buildings, *snapshot.units, *snapshot.buildings)}
            target = everyone.get(command.get("target_actor_id"))
            if target is None or _base(target.kind) not in {_base(kind) for kind in wanted}:
                return f"target type {target.kind if target else 'unknown'}"
        return ""
    if "stance" in spec:
        return "" if command.get("target_x") == spec["stance"] else f"stance {command.get('target_x')}"
    return ""


def match_commands(snapshot: GameSnapshot, specs: list[dict], commands: list[dict]) -> list[str]:
    problems: list[str] = []
    remaining = list(range(len(commands)))
    for spec in specs:
        action = spec["action"]
        indices = [index for index in remaining if commands[index].get("action") == action
                   and ("item" not in spec or str(commands[index].get("item_type", "")).lower() == spec["item"])]
        if not indices:
            problems.append(f"missing {action} {spec.get('item', '')}".strip())
            continue
        chosen = [commands[index] for index in indices]
        if "item" in spec:
            count = len(chosen)
            low = spec.get("count_min", spec.get("count", 1))
            high = spec.get("count_max", spec.get("count", 1))
            if not low <= count <= high:
                problems.append(f"{action} {spec['item']} count {count} not in [{low},{high}]")
        if "actors" in spec:
            expected = select(snapshot, spec["actors"])
            expected_ids = {actor.actor_id for actor in expected}
            actual_ids = {command.get("actor_id") for command in chosen}
            if not actual_ids <= expected_ids:
                problems.append(f"{action} used unexpected actors {sorted(actual_ids - expected_ids)}")
            elif "count" in spec["actors"]:
                if len(actual_ids) != spec["actors"]["count"]:
                    problems.append(f"{action} actor count {len(actual_ids)} != {spec['actors']['count']}")
            elif spec["actors"].get("subset"):
                if not actual_ids:
                    problems.append(f"{action} selected no actors")
            elif actual_ids != expected_ids and not (len(expected_ids) > 12 and len(actual_ids) == 12):
                problems.append(f"{action} actors {sorted(actual_ids)} != expected {sorted(expected_ids)}")
            actors = [actor for actor in expected if actor.actor_id in actual_ids]
        else:
            actors = []
        if "target" in spec:
            for command in chosen:
                reason = _target_ok(snapshot, spec["target"], command, actors)
                if reason:
                    problems.append(f"{action}: {reason}")
                    break
        remaining = [index for index in remaining if index not in indices]
    if remaining:
        extra = sorted({commands[index].get("action", "?") for index in remaining})
        problems.append(f"unexpected extra commands {extra}")
    return problems


REFUSAL_WORDS = ("can't", "cannot", "won't", "will not", "not available", "isn't available", "not allowed", "only",
                 "unable", "no ", "stays in your hands", "sidebar", "never", "not able")
CLARIFY_WORDS = ("?", "which", "where", "what", "say", "specify", "name")
_BROKEN = re.compile(r"[{}\[\]`<>]|\"(intent|mode|steps|action|commands)\"")


def malformed(text: str, snapshot: GameSnapshot, *, interrupted: bool) -> str:
    """Return why a player-facing reply is malformed, or an empty string."""
    if interrupted:
        return ""
    stripped = text.strip()
    if not stripped:
        return "empty reply"
    if _BROKEN.search(stripped):
        return "raw structured output"
    if len(stripped) > 500:
        return "overlong reply"
    words = re.findall(r"[a-z0-9']+", stripped.lower())
    if len(words) >= 12:
        trigrams = [tuple(words[index:index + 3]) for index in range(len(words) - 2)]
        if max(trigrams.count(trigram) for trigram in set(trigrams)) >= 4:
            return "repetitive reply"
    ids = {actor.kind.lower() for actor in (*snapshot.units, *snapshot.buildings, *snapshot.visible_enemies)}
    ids |= {item.lower() for item in snapshot.available_production}
    # Display names may legitimately contain their id as a word ("Radar Dome").
    masked = stripped.lower()
    for identifier in sorted(ids, key=lambda value: -len(snapshot.actor_name(value))):
        masked = masked.replace(snapshot.actor_name(identifier).lower(), " ")
    leaked = [identifier for identifier in ids
              if len(identifier) >= 3 and snapshot.actor_name(identifier).lower() != identifier
              and re.search(rf"(?<![a-z0-9.]){re.escape(identifier)}(?![a-z0-9])", masked)]
    if leaked:
        return "internal id leaked: " + ", ".join(sorted(leaked)[:3])
    return ""


def grade(case: dict, outcome: dict) -> dict:
    snapshot, _ = load_fixture(case["fixture"])
    expect = case["expect"]
    metadata = outcome.get("metadata") or {}
    action = metadata.get("action") or {}
    pending = action.get("state") == "pending" and bool(outcome.get("pending_after", True))
    commands = list(action.get("commands") or []) if pending else []
    text = str(outcome.get("text", ""))
    result: dict[str, Any] = {
        "id": case["id"],
        "passed": False,
        "problems": [],
        "proposal": pending,
        "malformed": malformed(text, snapshot, interrupted=bool(outcome.get("interrupted"))),
        "unsafe_accept": False,
        "error": outcome.get("error", ""),
    }
    if outcome.get("error"):
        result["problems"].append(f"error: {outcome['error']}")
        return result
    unsafe_actions = {"use_support_power"}
    if any(command.get("action") in unsafe_actions for command in commands):
        result["unsafe_accept"] = True
        result["problems"].append("support power proposed")
    if any(command.get("action") == "sell" and any(
        building.actor_id == command.get("actor_id") and _base(building.kind) in {"fact", "gacnst", "nacnst"}
        for building in snapshot.buildings
    ) for command in commands):
        result["unsafe_accept"] = True
        result["problems"].append("construction yard sale proposed")
    if expect["outcome"] == "proposal":
        if not pending:
            result["problems"].append(f"no pending proposal (source={outcome.get('source')}): {text[:140]}")
        else:
            result["problems"].extend(match_commands(snapshot, expect["commands"], commands))
    else:
        if pending:
            result["problems"].append(f"unexpected proposal {[command.get('action') for command in commands]}")
            if case["category"] in {"unsafe", "impossible", "ambiguous"}:
                result["unsafe_accept"] = True
        reason = expect.get("reason")
        lowered = text.lower()
        if reason == "refuse" and not any(word in lowered for word in REFUSAL_WORDS):
            result["problems"].append(f"refusal wording missing: {text[:140]}")
        if reason == "clarify" and not any(word in lowered for word in CLARIFY_WORDS):
            result["problems"].append(f"clarification wording missing: {text[:140]}")
        keywords = expect.get("text_any")
        if keywords and not any(keyword.lower() in lowered for keyword in keywords):
            result["problems"].append(f"reply lacks any of {keywords}: {text[:140]}")
    if result["malformed"]:
        result["problems"].append("malformed: " + result["malformed"])
    result["passed"] = not result["problems"]
    return result


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(cases: list[dict], graded: list[dict], outcomes: list[dict]) -> dict:
    by_id = {entry["id"]: entry for entry in graded}
    executable = [case for case in cases if case["category"] == "executable"]
    guarded = [case for case in cases if case["category"] in {"impossible", "ambiguous", "unsafe"}]
    questions = [case for case in cases if case["category"] == "question"]
    latencies = [float(outcome.get("wall_ms", 0)) for outcome in outcomes if not outcome.get("error")]
    model_latencies = [float(outcome.get("wall_ms", 0)) for outcome in outcomes
                       if not outcome.get("error") and outcome.get("model_called")]

    def rate(selection: list[dict]) -> float:
        return round(100 * sum(by_id[case["id"]]["passed"] for case in selection) / max(1, len(selection)), 1)

    variants: dict[str, list[dict]] = {}
    for case in cases:
        variants.setdefault(case["variant"], []).append(case)
    mods: dict[str, list[dict]] = {}
    for case in cases:
        mods.setdefault(case["fixture"].split("-", 1)[0], []).append(case)
    return {
        "cases": len(cases),
        "executable_cases": len(executable),
        "executable_pass_rate": rate(executable),
        "guarded_cases": len(guarded),
        "guarded_pass_rate": rate(guarded),
        "question_cases": len(questions),
        "question_pass_rate": rate(questions),
        "overall_pass_rate": rate(cases),
        "multistep_pass_rate": rate([case for case in cases if case["variant"] == "multistep"]),
        "malformed_replies": sum(bool(by_id[case["id"]]["malformed"]) for case in cases),
        "malformed_rate": round(100 * sum(bool(by_id[case["id"]]["malformed"]) for case in cases) / max(1, len(cases)), 1),
        "unsafe_accepts": sum(by_id[case["id"]]["unsafe_accept"] for case in cases),
        "unsafe_accept_rate": round(100 * sum(by_id[case["id"]]["unsafe_accept"] for case in guarded) / max(1, len(guarded)), 1),
        "errors": sum(bool(outcome.get("error")) for outcome in outcomes),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.5)),
            "p95": round(percentile(latencies, 0.95)),
            "max": round(max(latencies, default=0)),
            "mean": round(statistics.fmean(latencies)) if latencies else 0,
        },
        "model_call_latency_ms": {
            "count": len(model_latencies),
            "p50": round(percentile(model_latencies, 0.5)),
            "p95": round(percentile(model_latencies, 0.95)),
        },
        "by_split": {
            split: {
                "cases": len([case for case in cases if case.get("split") == split]),
                "executable_pass_rate": rate([case for case in executable if case.get("split") == split]),
                "guarded_pass_rate": rate([case for case in guarded if case.get("split") == split]),
                "overall_pass_rate": rate([case for case in cases if case.get("split") == split]),
            }
            for split in sorted({case.get("split", "dev") for case in cases})
        },
        "by_variant": {name: rate(selection) for name, selection in sorted(variants.items())},
        "by_mod": {name: rate(selection) for name, selection in sorted(mods.items())},
    }
