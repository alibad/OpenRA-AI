from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPANION_SOURCE = REPOSITORY_ROOT / "services" / "companion" / "src"
if str(COMPANION_SOURCE) not in sys.path:
    sys.path.insert(0, str(COMPANION_SOURCE))

from openra_ai_companion.bridge import OpenRABridge
from openra_ai_companion.core import Companion


def wait_for_json(url: str, deadline: float) -> dict[str, object]:
    last_error = f"{url} did not become ready"
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                return json.loads(response.read())
        except (OSError, TimeoutError, URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"Local service at {url} was unavailable: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a live OpenRA AI bridge and optional model response.")
    parser.add_argument("--bridge", default="127.0.0.1:9998")
    parser.add_argument("--ai-console")
    parser.add_argument("--world-studio")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--require-ai", action="store_true")
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    services: dict[str, object] = {}
    if args.ai_console:
        services["ai_console"] = wait_for_json(args.ai_console.rstrip("/") + "/health", deadline)
    if args.world_studio:
        services["world_studio"] = wait_for_json(args.world_studio.rstrip("/") + "/health", deadline)

    snapshot = None
    last_error = "bridge did not become ready"
    with OpenRABridge(args.bridge) as bridge:
        while time.monotonic() < deadline:
            try:
                candidate = bridge.observe()
                if candidate.tick > 0 and candidate.map_name != "Unknown battlefield":
                    snapshot = candidate
                    break
            except RuntimeError as exc:
                last_error = str(exc)
            time.sleep(0.5)

    if snapshot is None:
        raise RuntimeError(last_error)
    if snapshot.explored_percent <= 0:
        raise RuntimeError("Live observation reported no explored terrain after the match started.")

    result: dict[str, object] = {
        "map": snapshot.map_name,
        "tick": snapshot.tick,
        "cash": snapshot.cash,
        "units": len(snapshot.units),
        "buildings": len(snapshot.buildings),
        "explored_percent": round(snapshot.explored_percent, 1),
        "power_balance": snapshot.power_provided - snapshot.power_drained,
        "remembered_enemy_buildings": len(snapshot.remembered_enemy_buildings),
        "services": services,
    }
    if args.require_ai:
        companion = Companion()
        companion.latest_snapshot = snapshot
        response = companion.ask("Give me one immediate tactical priority in one sentence.")
        if response.source != "ai-layer" or not response.text.strip():
            raise RuntimeError(f"AI-layer response was not available: {response.as_dict()}")
        result["ai"] = {
            "source": response.source,
            "model": response.metadata.get("model", ""),
            "answer": response.text,
        }

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
