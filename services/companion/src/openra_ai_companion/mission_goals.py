from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import GameSnapshot, MissionObjective, Unit


@dataclass(frozen=True)
class MissionGoalNode:
    goal_id: str
    primitive: str
    description: str
    status: str
    required: bool
    dependencies: tuple[str, ...] = ()
    preserve_actor_ids: tuple[int, ...] = ()
    legal_target_ids: tuple[int, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "primitive": self.primitive,
            "description": self.description,
            "status": self.status,
            "required": self.required,
            "dependencies": list(self.dependencies),
            "preserve_actor_ids": list(self.preserve_actor_ids),
            "legal_target_ids": list(self.legal_target_ids),
        }


def _kind(actor: Unit) -> str:
    return actor.kind.lower().split("@", 1)[0].split(".", 1)[0]


def _primitive(objective: MissionObjective) -> str:
    text = " ".join(re.sub(r"[^a-z0-9]+", " ", objective.description.lower()).split())
    patterns = (
        ("infiltrate", ("infiltrat", "spy into", "spy inside")),
        ("capture", ("captur",)),
        ("extract", ("extract", "evacuat", "escape", "get to the", "reach the")),
        ("escort", ("escort", "rescue", "protect", "keep alive", "survive")),
        ("defend", ("defend", "hold", "protect the base")),
        ("establish-base", ("establish", "build a base", "construct", "deploy")),
        ("destroy", ("destroy", "eliminate", "kill", "neutralize", "wipe out")),
        ("explore", ("find", "locate", "discover", "recon", "scout")),
    )
    for primitive, needles in patterns:
        if any(needle in text for needle in needles):
            return primitive
    return "scripted-trigger"


def _preserve_ids(snapshot: GameSnapshot, text: str) -> tuple[int, ...]:
    named_types = {
        "tanya": {"e7", "tanya"},
        "spy": {"spy"},
        "engineer": {"engi"},
        "scientist": {"scientist"},
        "einstein": {"einstein"},
        "general": {"general"},
    }
    kinds: set[str] = set()
    lowered = text.lower()
    for name, values in named_types.items():
        if name in lowered:
            kinds.update(values)
    return tuple(sorted(actor.actor_id for actor in snapshot.units if _kind(actor) in kinds))


def _legal_targets(snapshot: GameSnapshot, primitive: str) -> tuple[int, ...]:
    if primitive == "capture":
        values = (target for actor in snapshot.units for target in actor.valid_capture_targets)
    elif primitive == "infiltrate":
        values = (target for actor in snapshot.units for target in actor.valid_infiltration_targets)
    elif primitive == "destroy":
        values = (
            actor.actor_id
            for actor in (*snapshot.visible_enemy_buildings, *snapshot.visible_enemies)
        )
    else:
        values = iter(())
    return tuple(sorted(set(values)))


def compile_mission_goal_graph(snapshot: GameSnapshot) -> dict[str, Any]:
    """Compile localized mission objectives into reusable execution primitives.

    The graph is deliberately grounded in live objective state and legal target
    telemetry. It does not inspect mission scripts or hidden actors.
    """
    if not snapshot.mission_mode:
        return {"active": False, "nodes": [], "ready": []}

    nodes: list[MissionGoalNode] = []
    previous_required = ""
    for objective in snapshot.objectives:
        primitive = _primitive(objective)
        goal_id = f"objective-{objective.objective_id}"
        dependencies = (previous_required,) if previous_required and objective.state == "incomplete" else ()
        node = MissionGoalNode(
            goal_id=goal_id,
            primitive=primitive,
            description=objective.description,
            status=objective.state,
            required=objective.required,
            dependencies=dependencies,
            preserve_actor_ids=_preserve_ids(snapshot, objective.description),
            legal_target_ids=_legal_targets(snapshot, primitive),
        )
        nodes.append(node)
        if objective.required and objective.state != "complete":
            previous_required = goal_id

    by_id = {node.goal_id: node for node in nodes}
    ready = [
        node for node in nodes
        if node.status == "incomplete"
        and all(by_id.get(dependency) is None or by_id[dependency].status == "complete" for dependency in node.dependencies)
    ]
    # Mission UIs do not guarantee objective ordering as a dependency graph.
    # If that conservative chain yields nothing, keep the first live objective actionable.
    if not ready:
        ready = [node for node in nodes if node.status == "incomplete"][:1]

    briefing_directives = []
    for index, sentence in enumerate(re.split(r"[\n.!?]+", snapshot.mission_briefing)):
        text = sentence.strip()
        if not text:
            continue
        objective = MissionObjective(-(index + 1), text, kind="Briefing", required=False)
        primitive = _primitive(objective)
        if primitive == "scripted-trigger" and not re.search(r"\b(avoid|beware|must|do not|keep)\b", text.lower()):
            continue
        briefing_directives.append({
            "directive_id": f"briefing-{index + 1}",
            "primitive": primitive,
            "description": text,
            "preserve_actor_ids": list(_preserve_ids(snapshot, text)),
            "legal_target_ids": list(_legal_targets(snapshot, primitive)),
        })

    return {
        "active": True,
        "briefing": snapshot.mission_briefing,
        "nodes": [node.as_dict() for node in nodes],
        "ready": [node.goal_id for node in ready],
        "ready_primitives": [node.primitive for node in ready],
        "briefing_directives": briefing_directives,
        "compiler": "fog-respecting objective primitive compiler v1",
    }
