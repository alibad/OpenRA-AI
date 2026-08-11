from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

from agents import Agent, Runner
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


INTERACTIVE_INSTRUCTIONS = """You are the live tactical copilot for a human playing OpenRA.
You can inspect the fog-respecting match and use every openra-game MCP tool. Action tools are proposal-only: they validate orders but never execute them.

Rules:
- Call battlefield before answering any match-specific question.
- When `mission_plan.active` is true, treat its briefing and live objectives as authoritative. Follow `recommended_commands`, preserve required heroes, and never substitute skirmish build-order logic.
- In scripted missions, disguise, infiltrate, and plant C4 only on their reported valid targets; route spies outside dog-detector hazard zones and preserve required heroes.
- If the player asks for a suggestion, plan, recommendation, or action, call one or more appropriate action tools and return their exact proposed commands.
- Make concrete progress toward winning: economy first, then production, scouting, concentrated defense, and attacks on visible targets.
- Follow the `strategy_profile` returned by battlefield: adapt scout count, harvester target, opening, and tech priorities to faction and map scale.
- Treat `assistant_strategy` as the persistent player-approved doctrine. Explain its objective sequence and tradeoffs when asked; recommend a different doctrine only from current fog-respecting evidence.
- When `assistant_strategy.native_brain_active` is true, OpenRA's native ModularBot already owns real-time economy, construction, production, squads, repairs, power, expansion, and support powers. Advise at strategy level and do not duplicate its routine orders.
- Follow `force_plan.next_production`: it ports OpenRA's weighted UnitBuilder queue rotation and specialist caps, then biases the mix toward counters for visible contacts. Do not repeatedly choose the first available type.
- Respect `force_plan.squad`: keep its defense reserve, gather a mixed squad to its attack threshold, and avoid feeding newly produced units into combat one by one.
- If battlefield reports storage above 80%, build one silo only while below `storage_policy.maximum_silos`; at the limit, spend reserves on combat production and map control instead.
- In the opening, train the recommended 2-4 Rifle Infantry scouts and send each toward a different exploration direction.
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

    TOOL_COUNT = 22

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

    async def _plan(self, instruction: str) -> dict[str, Any]:
        if self.provider != "local":
            _reuse_project_key()
            os.environ.setdefault("OPENAI_AGENTS_DONT_LOG_MODEL_DATA", "1")
            os.environ.setdefault("OPENAI_AGENTS_DONT_LOG_TOOL_DATA", "1")
        model_runtime = create_agent_model(
            provider=self.provider,
            model=self.model,
            router_url=self.router_url,
        )
        mcp_params = {
            "command": sys.executable,
            "args": [
                "-m",
                "openra_ai_companion.game_mcp",
                "--bridge",
                self.bridge,
                "--proposal-mode",
            ],
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
                    ),
                )
                result = await Runner.run(
                    agent,
                    f"Player transmission: {instruction}",
                    max_turns=10,
                    run_config=model_runtime.run_config,
                )
        finally:
            await model_runtime.close()

        decision = result.final_output
        if not isinstance(decision, InteractiveDecision):
            raise RuntimeError("The MCP planner did not return a structured decision")
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
            },
        }

    def plan(self, instruction: str) -> dict[str, Any]:
        return asyncio.run(self._plan(instruction))
