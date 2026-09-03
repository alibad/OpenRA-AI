from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from collections import deque
from typing import Any

from agents import Agent, Runner
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.mcp import MCPServerStdio
from pydantic import BaseModel, Field

from .agent_models import (
    agent_model_settings,
    create_agent_model,
    default_agent_model,
    default_agent_provider,
    default_agent_router_url,
)
from .autonomous import _game_child_environment, _reuse_project_key, _workspace_root
from .process_entrypoints import game_mcp_command


INTERACTIVE_INSTRUCTIONS = """You are the live tactical copilot for a human playing OpenRA.
You can inspect the fog-respecting match and use every openra-game MCP tool. Action tools are proposal-only: they validate orders but never execute them.

Rules:
- Call battlefield before answering any match-specific question.
- A direct player request outranks autonomous routine policy. Fulfill it with proposal tools even when it overlaps work normally owned by the native brain, unless the requested order is illegal or unsafe.
- Never answer with process filler such as "I am assessing", "analyzing", or "I need more information" when battlefield data is available. State the important facts and one useful next move.
- When `mission_plan.active` is true, treat its briefing and live objectives as authoritative. Follow `recommended_commands`, preserve required heroes, and never substitute skirmish build-order logic.
- In scripted missions, disguise, infiltrate, and plant C4 only on their reported valid targets; route spies outside dog-detector hazard zones and preserve required heroes.
- If the player asks for a suggestion, plan, recommendation, or action, call one or more appropriate action tools and return their exact proposed commands.
- Make concrete progress toward winning: economy first, then production, scouting, concentrated defense, and attacks on visible targets.
- Follow the `strategy_profile` returned by battlefield: adapt scout count, harvester target, opening, and tech priorities to faction and map scale.
- Treat `assistant_strategy` as the persistent player-approved doctrine. Explain its objective sequence and tradeoffs when asked; recommend a different doctrine only from current fog-respecting evidence.
- When `assistant_strategy.native_brain_active` is true, OpenRA's native ModularBot already owns routine economy, construction, production, squads, repairs, power, expansion, and support powers. Avoid unsolicited duplicate orders, but obey a direct player request and coordinate it with work already queued.
- Follow `force_plan.next_production`: it ports OpenRA's weighted UnitBuilder queue rotation and specialist caps, then biases the mix toward counters for visible contacts. Do not repeatedly choose the first available type.
- Respect `force_plan.squad`: keep its defense reserve, gather a mixed squad to its attack threshold, and avoid feeding newly produced units into combat one by one.
- If battlefield reports storage above 80%, build one silo only while below `storage_policy.maximum_silos`; at the limit, spend reserves on combat production and map control instead.
- In the opening, train the recommended 2-4 Rifle Infantry scouts and send each toward a different exploration direction.
- Treat "scout" or "recon" as a concrete destination: choose distinct reachable unexplored approaches from battlefield data instead of asking the player for coordinates.
- If a requested building is already queued, completed, or placed, say so and continue with the next legal part of the request instead of proposing a duplicate or returning a generic refusal.
- Omit coordinates from place_building unless the player explicitly demands a cell; the engine optimizer scores explored ore proximity, structure spacing, and clear production exits.
- Set rally points on barracks and war factories toward open staging space beyond their doors; never rally onto ore or into base congestion.
- Use only actor IDs, item IDs, coordinates, enemies, and facts returned by tools. Never infer hidden state.
- Do not call advance in a live player match. Never surrender.
- Avoid sell, cancel_production, or power_down unless the player explicitly requests it.
- Keep message and summary terse. Do not claim an order executed. The game will require the player to say confirm before execution.
- Never expose internal type IDs such as e1, proc, 2tnk, or numeric actor IDs in message or summary. Use `display_name` values and natural player-facing names; IDs belong only in commands.
- For a capability question, explain that you can inspect state and propose build, train, move, attack, guard, repair, harvest, deploy, disguise, infiltrate, demolish, transport, rally, stance, and production actions.
- If no safe concrete action is possible, return no commands and ask one concise clarifying question.

When an action tool returns `proposed`, copy those command objects exactly into the structured `commands` output."""


_ACTION_WORDS = frozenset({
    "attack", "build", "cancel", "capture", "create", "defend", "demolish", "deploy",
    "disguise", "do", "escort", "focus", "guard", "handle", "harvest", "infiltrate", "make",
    "move", "order", "patrol", "place", "power", "produce", "protect", "queue", "rally", "repair",
    "retreat", "scout", "sell", "send", "stance", "stop", "train", "transport", "unload", "use",
})
_ACTION_REQUEST_MARKERS = (
    "can you", "could you", "i want you to", "i need you to", "let s", "please",
    "what do we do", "what should we do", "what should i do", "what s our next move",
    "whats our next move", "recommend a move", "suggest a move",
)
_ACTION_TOOL_NAMES = frozenset({
    "move", "attack_move", "attack", "stop", "harvest", "build", "train", "deploy",
    "place_building", "cancel_production", "repair", "sell", "set_rally_point", "guard",
    "set_stance", "enter_transport", "disguise", "infiltrate", "capture", "demolish", "unload",
    "power_down", "set_primary", "use_support_power",
})
_BACKGROUND_PREFIX = "autonomous commander mode is enabled"


def _requests_action(instruction: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", instruction.lower()).strip()
    words = normalized.split()
    if not words or not any(word in _ACTION_WORDS for word in words):
        return False
    return words[0] in _ACTION_WORDS or any(marker in normalized for marker in _ACTION_REQUEST_MARKERS)


def _tool_call_names(result: object) -> list[str]:
    names: list[str] = []
    for item in getattr(result, "new_items", []):
        if not isinstance(item, ToolCallItem):
            continue
        raw = item.raw_item
        name = raw.get("name", "") if isinstance(raw, dict) else getattr(raw, "name", "")
        if name and str(name) not in names:
            names.append(str(name))
    return names


def _structured_tool_output(output: object) -> dict[str, Any] | None:
    structured = getattr(output, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    if isinstance(output, dict):
        nested = output.get("structuredContent")
        if isinstance(nested, dict):
            return nested
        # The Agents SDK normalizes MCP text content to a small content block
        # instead of passing the JSON text through directly.
        text = output.get("text")
        if isinstance(text, str):
            parsed = _structured_tool_output(text)
            if parsed is not None:
                return parsed
        return output
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _proposed_tool_commands(result: object) -> list[dict[str, Any]]:
    names_by_call: dict[str, str] = {}
    pending_names: deque[str] = deque()
    commands: list[dict[str, Any]] = []
    for item in getattr(result, "new_items", []):
        if isinstance(item, ToolCallItem):
            if item.call_id and item.tool_name:
                names_by_call[item.call_id] = item.tool_name
            if item.tool_name:
                pending_names.append(item.tool_name)
            continue
        if not isinstance(item, ToolCallOutputItem):
            continue
        name = names_by_call.get(str(item.call_id or ""), "")
        if not name and pending_names:
            name = pending_names.popleft()
        elif name in pending_names:
            pending_names.remove(name)
        if name not in _ACTION_TOOL_NAMES:
            continue
        payload = _structured_tool_output(item.output)
        proposed = payload.get("proposed", []) if payload else []
        if isinstance(proposed, list):
            commands.extend(command for command in proposed if isinstance(command, dict))
    return commands[:12]


class ProposedCommand(BaseModel):
    action: str
    actor_id: int = 0
    target_actor_id: int = 0
    target_x: int = 0
    target_y: int = 0
    item_type: str = ""
    queued: bool = False
    ticks: int = 0


class InteractiveDecision(BaseModel):
    message: str = Field(description="One concise answer or clarification for the player.")
    summary: str = Field(default="", description="Short action summary when commands are proposed.")
    commands: list[ProposedCommand] = Field(default_factory=list)


class InteractiveMCPPlanner:
    """Runs the full MCP tool loop in non-executing proposal mode."""

    TOOL_COUNT = 28

    def __init__(
        self,
        bridge: str,
        model: str | None = None,
        provider: str | None = None,
        router_url: str | None = None,
    ) -> None:
        self.bridge = bridge
        self.provider = (provider or default_agent_provider()).strip().lower()
        self.model = model or default_agent_model(self.provider)
        self.router_url = (router_url or default_agent_router_url()).rstrip("/")
        self._dialogue: deque[tuple[str, str]] = deque(maxlen=6)
        self._dialogue_lock = threading.Lock()

    async def _plan(
        self,
        instruction: str,
        dialogue: tuple[tuple[str, str], ...] = (),
    ) -> dict[str, Any]:
        if self.provider != "local":
            _reuse_project_key()
            os.environ.setdefault("OPENAI_AGENTS_DONT_LOG_MODEL_DATA", "1")
            os.environ.setdefault("OPENAI_AGENTS_DONT_LOG_TOOL_DATA", "1")
        model_runtime = create_agent_model(
            provider=self.provider,
            model=self.model,
            router_url=self.router_url,
        )
        command = game_mcp_command("--bridge", self.bridge, "--proposal-mode")
        mcp_params = {
            "command": command[0],
            "args": command[1:],
            "cwd": str(_workspace_root()),
            "env": _game_child_environment(),
        }
        started = time.perf_counter()
        try:
            async with MCPServerStdio(
                mcp_params,
                cache_tools_list=True,
                name="openra-game-interactive",
                client_session_timeout_seconds=30,
                use_structured_content=True,
            ) as game_server:
                agent = Agent(
                    name="OpenRA live tactical copilot",
                    model=model_runtime.model,
                    instructions=INTERACTIVE_INSTRUCTIONS,
                    mcp_servers=[game_server],
                    output_type=InteractiveDecision,
                    model_settings=agent_model_settings(
                        local=model_runtime.local,
                        max_tokens=900 if model_runtime.local else 1200,
                        reasoning_effort="low",
                        # The player should never receive an ungrounded answer merely
                        # because a model chose not to use its available tools.
                        tool_choice="battlefield",
                    ),
                )
                history = "\n".join(
                    f"Player: {player}\nAssistant: {assistant}"
                    for player, assistant in dialogue
                )
                prompt = (
                    ("Recent player dialogue (oldest first):\n" + history + "\n\n")
                    if history else ""
                ) + f"Current player transmission: {instruction}"
                result = await Runner.run(
                    agent,
                    prompt,
                    max_turns=10,
                    run_config=model_runtime.run_config,
                )
                tool_calls = _tool_call_names(result)
                verified_commands = _proposed_tool_commands(result)
                decision = result.final_output
                proposed_action = (
                    decision.commands[0].action
                    if isinstance(decision, InteractiveDecision) and decision.commands
                    else ""
                )
                if (
                    isinstance(decision, InteractiveDecision)
                    and (
                        (_requests_action(instruction) and not decision.commands)
                        or (decision.commands and not verified_commands)
                    )
                ):
                    retry_input = result.to_input_list()
                    retry_input.append({
                        "role": "user",
                        "content": (
                            "Your prior response did not back its commands with a proposal action-tool result. "
                            "Use the proposal action tools for the first legal step and any other immediately legal "
                            "parts, then copy their exact proposed commands. Return no commands only if a live tool "
                            "identifies a concrete blocker; name that blocker."
                        ),
                    })
                    retry_agent = agent.clone(model_settings=agent_model_settings(
                        local=model_runtime.local,
                        max_tokens=900 if model_runtime.local else 1200,
                        reasoning_effort="low",
                        tool_choice=proposed_action if proposed_action in _ACTION_TOOL_NAMES else "required",
                    ))
                    result = await Runner.run(
                        retry_agent,
                        retry_input,
                        max_turns=10,
                        run_config=model_runtime.run_config,
                    )
                    tool_calls.extend(name for name in _tool_call_names(result) if name not in tool_calls)
                    verified_commands.extend(_proposed_tool_commands(result))
        finally:
            await model_runtime.close()

        decision = result.final_output
        if not isinstance(decision, InteractiveDecision):
            raise RuntimeError("The MCP planner did not return a structured decision")
        action_tool_calls = [name for name in tool_calls if name in _ACTION_TOOL_NAMES]
        if verified_commands:
            decision = decision.model_copy(update={
                "commands": [ProposedCommand.model_validate(command) for command in verified_commands[:12]],
            })
        commands_verified = not decision.commands or bool(verified_commands)
        if not commands_verified:
            decision = InteractiveDecision(
                message=(
                    decision.message.strip()
                    or "I read the battlefield but could not validate a concrete order, so nothing was proposed."
                ),
            )
        return {
            "message": decision.message.strip(),
            "summary": decision.summary.strip(),
            "commands": [command.model_dump() for command in decision.commands],
            "provider": self.provider,
            "model": self.model,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "mcp": {
                "connected": True,
                "server": "openra-game",
                "tools": self.TOOL_COUNT,
                "proposal_only": True,
                "tool_calls": tool_calls,
                "battlefield_read": "battlefield" in tool_calls,
                "action_tool_calls": action_tool_calls,
                "commands_verified_by_tools": commands_verified,
            },
        }

    def plan(self, instruction: str) -> dict[str, Any]:
        background = instruction.strip().lower().startswith(_BACKGROUND_PREFIX)
        with self._dialogue_lock:
            dialogue = () if background else tuple(self._dialogue)
        planned = asyncio.run(self._plan(instruction, dialogue))
        if not background:
            with self._dialogue_lock:
                self._dialogue.append((instruction.strip(), str(planned.get("message", "")).strip()))
        return planned
