"""Validate the shared editorial catalog against game sources; stage unchanged bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

PRODUCT = Path(__file__).resolve().parents[1]
CATALOG = PRODUCT / "catalog" / "factions.json"
# Public pages mirroring the catalog (RTSAI-Web routes). The game and companion build the same links.
DEFAULT_LINKS = {
    "origin": "https://rtsai.net",
    "faction": "/factions/{factionId}?mode={mode}",
    "unit": "/units/{unitId}?mode={mode}",
}
ID = re.compile(r"[a-z0-9-]+")


def links(catalog: dict) -> dict:
    return {**DEFAULT_LINKS, **(catalog.get("links") or {})}


def web_link(catalog: dict, kind: str, item_id: str, mode: str) -> str:
    """Deep link for a catalog faction/unit in one mode, e.g. https://rtsai.net/factions/iran?mode=ra2."""
    if kind not in {"faction", "unit"} or not ID.fullmatch(item_id or "") or not ID.fullmatch(mode or ""):
        raise ValueError(f"Malformed deep-link target: {kind}/{item_id}/{mode}")
    template = links(catalog)
    placeholder = "{factionId}" if kind == "faction" else "{unitId}"
    return template["origin"].rstrip("/") + template[kind].replace(placeholder, item_id).replace("{mode}", mode)


def validate_links(catalog: dict) -> None:
    template = links(catalog)
    origin = urlsplit(template["origin"])
    if origin.scheme != "https" or not origin.netloc or origin.path not in {"", "/"} or origin.query or origin.fragment:
        raise ValueError("links.origin must be an https origin without a path")
    for kind, placeholder in (("faction", "{factionId}"), ("unit", "{unitId}")):
        path = template[kind]
        if not isinstance(path, str) or not path.startswith("/") or placeholder not in path or "{mode}" not in path:
            raise ValueError(f"links.{kind} must start with / and contain {placeholder} and {{mode}}")


def check_link(url: str, origin: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != urlsplit(origin).netloc or parts.fragment or "{" in url or "}" in url or " " in url:
        raise ValueError(f"Malformed deep link: {url}")
