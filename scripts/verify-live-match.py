from __future__ import annotations

import argparse
import json
import time

from openra_ai_companion.bridge import OpenRABridge
from openra_ai_companion.core import Companion


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a live OpenRA AI bridge and optional model response.")
    parser.add_argument("--bridge", default="127.0.0.1:9998")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--require-ai", action="store_true")
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
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

    result: dict[str, object] = {
        "map": snapshot.map_name,
        "tick": snapshot.tick,
        "cash": snapshot.cash,
        "units": len(snapshot.units),
        "buildings": len(snapshot.buildings),
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
