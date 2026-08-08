from __future__ import annotations

import os
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from urllib.parse import urlparse


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


def user_settings_path() -> Path:
    app_data = os.environ.get("APPDATA")
    root = Path(app_data) if app_data else Path.home()
    return root / "OpenRA-AI" / "settings.json"


def _load_user_settings() -> dict[str, str | float | bool]:
    path = user_settings_path()
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class Settings:
    router_url: str = "http://127.0.0.1:4000"
    model_provider: str = "openai"
    text_model: str = "gpt-5.5"
    vision_model: str = "gpt-5.5"
    transcribe_model: str = "openai-transcribe"
    speech_model: str = "openai-tts"
    speech_voice: str = "alloy"
    timeout_seconds: float = 20.0
    companion_enabled: bool = True
    voice_enabled: bool = True
    notification_pace: str = "calm"
    voice_priority: str = "critical"

    @classmethod
    def from_env(cls) -> "Settings":
        file_values = _load_project_env()
        user_values = _load_user_settings()

        def get(name: str, default: str) -> str:
            field_name = {
                "OPENRA_AI_ROUTER_URL": "router_url",
                "OPENRA_AI_MODEL_PROVIDER": "model_provider",
                "OPENRA_AI_TEXT_MODEL": "text_model",
                "OPENRA_AI_VISION_MODEL": "vision_model",
                "OPENRA_AI_TRANSCRIBE_MODEL": "transcribe_model",
                "OPENRA_AI_TTS_MODEL": "speech_model",
                "OPENRA_AI_TTS_VOICE": "speech_voice",
                "OPENRA_AI_ROUTER_TIMEOUT_SECONDS": "timeout_seconds",
                "OPENRA_AI_NOTIFICATION_PACE": "notification_pace",
                "OPENRA_AI_VOICE_PRIORITY": "voice_priority",
            }[name]
            return str(os.environ.get(name, user_values.get(field_name, file_values.get(name, default))))

        def get_bool(name: str, field_name: str, default: bool) -> bool:
            value = os.environ.get(name, user_values.get(field_name, file_values.get(name, default)))
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() not in {"0", "false", "no", "off"}

        return cls(
            router_url=get("OPENRA_AI_ROUTER_URL", cls.router_url).rstrip("/"),
            model_provider=get("OPENRA_AI_MODEL_PROVIDER", cls.model_provider),
            text_model=get("OPENRA_AI_TEXT_MODEL", cls.text_model),
            vision_model=get("OPENRA_AI_VISION_MODEL", cls.vision_model),
            transcribe_model=get("OPENRA_AI_TRANSCRIBE_MODEL", cls.transcribe_model),
            speech_model=get("OPENRA_AI_TTS_MODEL", cls.speech_model),
            speech_voice=get("OPENRA_AI_TTS_VOICE", cls.speech_voice),
            timeout_seconds=float(get("OPENRA_AI_ROUTER_TIMEOUT_SECONDS", str(cls.timeout_seconds))),
            companion_enabled=get_bool("OPENRA_AI_COMPANION_ENABLED", "companion_enabled", cls.companion_enabled),
            voice_enabled=get_bool("OPENRA_AI_VOICE_ENABLED", "voice_enabled", cls.voice_enabled),
            notification_pace=get("OPENRA_AI_NOTIFICATION_PACE", cls.notification_pace),
            voice_priority=get("OPENRA_AI_VOICE_PRIORITY", cls.voice_priority),
        ).validated()

    def validated(self) -> "Settings":
        parsed = urlparse(self.router_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("AI Layer URL must be an absolute http or https URL")
        if self.model_provider not in {"openai", "anthropic", "gemini", "local", "custom"}:
            raise ValueError("model_provider must be openai, anthropic, gemini, local, or custom")
        for name in ("text_model", "vision_model", "transcribe_model", "speech_model", "speech_voice"):
            value = str(getattr(self, name)).strip()
            if not value or len(value) > 160:
                raise ValueError(f"{name} must contain 1 to 160 characters")
        if not 1 <= self.timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be between 1 and 120")
        if self.notification_pace not in {"calm", "balanced", "frequent"}:
            raise ValueError("notification_pace must be calm, balanced, or frequent")
        if self.voice_priority not in {"off", "critical", "important"}:
            raise ValueError("voice_priority must be off, critical, or important")
        return self

    def with_updates(self, values: dict) -> "Settings":
        allowed = {
            "router_url",
            "model_provider",
            "text_model",
            "vision_model",
            "transcribe_model",
            "speech_model",
            "speech_voice",
            "timeout_seconds",
            "companion_enabled",
            "voice_enabled",
            "notification_pace",
            "voice_priority",
        }
        updates = {key: values[key] for key in allowed if key in values}
        if "timeout_seconds" in updates:
            updates["timeout_seconds"] = float(updates["timeout_seconds"])
        for key in ("companion_enabled", "voice_enabled"):
            if key in updates:
                value = updates[key]
                updates[key] = value if isinstance(value, bool) else str(value).strip().lower() not in {"0", "false", "no", "off"}
        for key in allowed - {"timeout_seconds", "companion_enabled", "voice_enabled"}:
            if key in updates:
                updates[key] = str(updates[key]).strip()
        if "router_url" in updates:
            updates["router_url"] = updates["router_url"].rstrip("/")
        return replace(self, **updates).validated()

    def as_dict(self) -> dict[str, str | float | bool]:
        return asdict(self)

    def save(self) -> Path:
        path = user_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2) + "\n", encoding="utf-8")
        return path
