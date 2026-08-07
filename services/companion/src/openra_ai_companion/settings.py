from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_project_env() -> dict[str, str]:
    values: dict[str, str] = {}
    candidates = [Path.cwd(), *Path.cwd().parents]
    for directory in candidates:
        path = directory / ".env"
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        break
    return values


@dataclass(frozen=True)
class Settings:
    router_url: str = "http://127.0.0.1:4000"
    text_model: str = "gpt-5.5"
    transcribe_model: str = "openai-transcribe"
    speech_model: str = "openai-tts"
    speech_voice: str = "alloy"
    timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls) -> "Settings":
        file_values = _load_project_env()

        def get(name: str, default: str) -> str:
            return os.environ.get(name, file_values.get(name, default))

        return cls(
            router_url=get("OPENRA_AI_ROUTER_URL", cls.router_url).rstrip("/"),
            text_model=get("OPENRA_AI_TEXT_MODEL", cls.text_model),
            transcribe_model=get("OPENRA_AI_TRANSCRIBE_MODEL", cls.transcribe_model),
            speech_model=get("OPENRA_AI_TTS_MODEL", cls.speech_model),
            speech_voice=get("OPENRA_AI_TTS_VOICE", cls.speech_voice),
            timeout_seconds=float(get("OPENRA_AI_ROUTER_TIMEOUT_SECONDS", str(cls.timeout_seconds))),
        )
