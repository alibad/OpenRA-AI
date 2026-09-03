from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse

from .model_selection import Hardware


def discover(endpoint: str = "http://127.0.0.1:1234", hardware: Hardware | None = None) -> dict:
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
        raise ValueError("LM Studio discovery only supports a local loopback server")
    request = urllib.request.Request(endpoint.rstrip("/") + "/api/v1/models", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=2) as response:
        raw = json.load(response)
    models = []
    budget = (hardware or Hardware.detect()).model_budget_bytes
    for model in raw.get("models", []):
        if model.get("type") != "llm":
            continue
        capabilities = model.get("capabilities") or {}
        size = max(0, int(model.get("size_bytes") or 0))
        models.append({
            "id": model["key"], "label": model.get("display_name") or model["key"],
            "provider": "custom", "mode": "chat", "local": True,
            "supports_vision": capabilities.get("vision") is True,
            "supports_tools": capabilities.get("trained_for_tool_use") is True,
            "loaded": bool(model.get("loaded_instances")),
            "size_bytes": size,
            "fits_budget": size > 0 and size * 1.5 + 512 * 1024 ** 2 <= budget,
        })
    suitable = [model for model in models if model["supports_tools"] and model["fits_budget"]]
    suitable.sort(key=lambda model: (not model["loaded"], model["size_bytes"], model["id"]))
    return {
        "endpoint": endpoint, "models": models,
        "suggested": suitable[0] if suitable else None,
        "detail": "Detected from LM Studio metadata; not certified by OpenRA AI. Apply explicitly to use it. Voice remains separately managed.",
    }
