from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from agents import ModelSettings, OpenAIChatCompletionsModel, RunConfig, set_tracing_disabled
from agents.model_settings import Reasoning
from openai import AsyncOpenAI


LOCAL_PROVIDER = "local"
LOCAL_MODEL = "local-coder"
LOCAL_ROUTER_URL = "http://127.0.0.1:4000"
HOSTED_MODEL = "gpt-5.5"
LOCAL_PROMPT_TRUNCATION_TOKENS = 31_500


@dataclass(frozen=True)
class AgentModelRuntime:
    provider: str
    name: str
    model: Any
    client: AsyncOpenAI | None
    run_config: RunConfig

    @property
    def local(self) -> bool:
        return self.provider == LOCAL_PROVIDER

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()


def default_agent_provider() -> str:
    return os.environ.get("OPENRA_AI_AGENT_PROVIDER", os.environ.get("OPENRA_AI_MODEL_PROVIDER", LOCAL_PROVIDER))


def default_agent_model(provider: str | None = None) -> str:
    provider = (provider or default_agent_provider()).strip().lower()
    return os.environ.get("OPENRA_AI_AGENT_MODEL", LOCAL_MODEL if provider == LOCAL_PROVIDER else HOSTED_MODEL)


def default_agent_router_url() -> str:
    return os.environ.get("OPENRA_AI_AGENT_ROUTER_URL", os.environ.get("OPENRA_AI_ROUTER_URL", LOCAL_ROUTER_URL)).rstrip("/")


def create_agent_model(
    *,
    provider: str,
    model: str,
    router_url: str,
) -> AgentModelRuntime:
    provider = provider.strip().lower()
    model = model.strip()
    if not model:
        raise ValueError("model must not be empty")
    if provider != LOCAL_PROVIDER:
        return AgentModelRuntime(provider, model, model, None, RunConfig())

    # A local run must never fall back to the OpenAI default provider or export
    # traces there. The BeTenshi router owns the local-coder -> vLLM mapping.
    set_tracing_disabled(True)
    os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1"
    client = AsyncOpenAI(
        api_key="local-router",
        base_url=f"{router_url.rstrip('/')}/v1",
        timeout=120.0,
        max_retries=0,
    )
    local_model = OpenAIChatCompletionsModel(
        model=model,
        openai_client=client,
        buffer_streamed_tool_calls=True,
    )
    return AgentModelRuntime(
        provider,
        model,
        local_model,
        client,
        RunConfig(tracing_disabled=True, trace_include_sensitive_data=False),
    )


def agent_model_settings(*, local: bool, max_tokens: int, reasoning_effort: str) -> ModelSettings:
    if local:
        # vLLM accepts the standard chat/tool surface but not OpenAI-only
        # reasoning or verbosity fields.
        return ModelSettings(
            temperature=0.1,
            parallel_tool_calls=False,
            max_tokens=max_tokens,
            # The local router otherwise auto-truncates to one token beyond
            # the model's 32K input allowance. Give MCP tool schemas and the
            # requested output a deterministic safety margin.
            extra_body={"truncate_prompt_tokens": LOCAL_PROMPT_TRUNCATION_TOKENS},
        )
    return ModelSettings(
        reasoning=Reasoning(effort=reasoning_effort, summary="concise"),
        verbosity="low",
        parallel_tool_calls=False,
        max_tokens=max_tokens,
    )
