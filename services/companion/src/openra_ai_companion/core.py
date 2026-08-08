from __future__ import annotations

import json
import threading
import time

from .insights import InsightEngine
from .models import CompanionResponse, GameSnapshot, Insight
from .router import AIRouter, RouterError

SYSTEM_PROMPT = """You are a calm battlefield companion inside OpenRA, a classic RTS.
Speak in one short sentence, under 22 words. Mention only facts in the supplied fog-respecting snapshot.
Visible enemies are current contacts. Remembered enemy buildings are last-known structures under fog; never claim they are unknown or currently visible.
Explored percent is cumulative map knowledge. Power balance is the same net value shown beside the lightning icon; never invent or quote supply/usage totals.
Treat production countdowns as transient: never quote raw tick counts or imply that an old countdown is still current.
Prioritize an actionable observation. Never claim to control units. Never use markdown, greetings, or filler."""


class Companion:
    def __init__(self, router: AIRouter | None = None, insights: InsightEngine | None = None):
        self.router = router or AIRouter()
        self.insights = insights or InsightEngine()
        self.latest_snapshot: GameSnapshot | None = None
        self.enabled = True
        self.muted = False
        self._generation = 0
        self._lock = threading.Lock()

    def _begin(self) -> int:
        with self._lock:
            self._generation += 1
            return self._generation

    def interrupt(self) -> int:
        """Invalidate in-flight speech/text immediately; provider work may finish but is discarded."""
        with self._lock:
            self._generation += 1
            return self._generation

    def _interrupted(self, generation: int) -> bool:
        with self._lock:
            return generation != self._generation

    def configure(self, *, enabled: bool | None = None, muted: bool | None = None) -> dict[str, bool]:
        if enabled is not None:
            self.enabled = enabled
            if not enabled:
                self.interrupt()
        if muted is not None:
            self.muted = muted
            if muted:
                self.interrupt()
        return {"enabled": self.enabled, "muted": self.muted}

    def _render_insight(self, snapshot: GameSnapshot, insight: Insight, generation: int) -> CompanionResponse:
        started = time.perf_counter()
        if not self.enabled or self.muted:
            return CompanionResponse("", "disabled", utterance_id=generation, insight=insight)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps({"reason_to_speak": insight.fact, "snapshot": snapshot.compact()}, separators=(",", ":")),
            },
        ]
        try:
            result = self.router.chat(messages)
            response = CompanionResponse(result.text, "ai-layer", utterance_id=generation, insight=insight, latency_ms=result.latency_ms, metadata={"model": result.model})
        except RouterError as exc:
            response = CompanionResponse(insight.fallback_text, "deterministic-fallback", utterance_id=generation, insight=insight, latency_ms=round((time.perf_counter() - started) * 1000), metadata={"degraded": True, "reason": str(exc)})
        if self._interrupted(generation):
            response.text = ""
            response.interrupted = True
        return response

    def observe(self, snapshot: GameSnapshot) -> CompanionResponse | None:
        self.latest_snapshot = snapshot
        insight = self.insights.select(snapshot)
        if not insight:
            return None
        generation = self._begin()
        return self._render_insight(snapshot, insight, generation)

    def ask(self, question: str) -> CompanionResponse:
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        generation = self._begin()
        if not self.enabled or self.muted:
            return CompanionResponse("", "disabled", utterance_id=generation)
        snapshot = self.latest_snapshot
        if snapshot is None:
            return CompanionResponse("I don't have a live game snapshot yet.", "deterministic-fallback", utterance_id=generation, metadata={"degraded": True})
        started = time.perf_counter()
        try:
            result = self.router.chat([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({"player_question": question, "snapshot": snapshot.compact()}, separators=(",", ":"))},
            ])
            response = CompanionResponse(result.text, "ai-layer", utterance_id=generation, latency_ms=result.latency_ms, metadata={"model": result.model})
        except RouterError as exc:
            response = CompanionResponse("The AI router is unavailable; I can still watch for critical deterministic alerts.", "deterministic-fallback", utterance_id=generation, latency_ms=round((time.perf_counter() - started) * 1000), metadata={"degraded": True, "reason": str(exc)})
        if self._interrupted(generation):
            response.text = ""
            response.interrupted = True
        return response

    def transcribe(self, audio: bytes, filename: str = "question.wav") -> CompanionResponse:
        if not audio:
            raise ValueError("audio must not be empty")
        generation = self._begin()
        if not self.enabled:
            return CompanionResponse("", "disabled", utterance_id=generation)
        result = self.router.transcribe(audio, filename)
        response = CompanionResponse(result.text, "ai-layer", utterance_id=generation, latency_ms=result.latency_ms, metadata={"model": result.model})
        if self._interrupted(generation):
            response.text = ""
            response.interrupted = True
        return response

    def speech(self, text: str) -> tuple[bytes, dict]:
        text = text.strip()
        if not text:
            raise ValueError("text must not be empty")
        generation = self._begin()
        if not self.enabled or self.muted:
            return b"", {"interrupted": False, "disabled": True, "utterance_id": generation}
        audio, latency_ms, content_type = self.router.speech(text)
        interrupted = self._interrupted(generation)
        return (b"" if interrupted else audio), {
            "interrupted": interrupted,
            "utterance_id": generation,
            "latency_ms": latency_ms,
            "content_type": content_type,
        }

    def status(self) -> dict:
        return {
            "service": "companion",
            "version": "0.1.0",
            "enabled": self.enabled,
            "muted": self.muted,
            "has_snapshot": self.latest_snapshot is not None,
            "router": self.router.health(),
        }
