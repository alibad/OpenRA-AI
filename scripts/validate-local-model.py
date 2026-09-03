#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.request

from openra_ai_companion.core import ACTION_PROMPT, SYSTEM_PROMPT


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded game-assistant checks against a local candidate; never issue game commands.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    checks = [
        (SYSTEM_PROMPT, {"reason_to_speak": "Low power. Build a Power Plant to restore power.",
                        "snapshot": {"cash": 2000, "power_balance": -50}}, "power"),
        (SYSTEM_PROMPT, {"reason_to_speak": "A Harvester is idle. Send it to harvest ore.",
                        "snapshot": {"idle_harvesters": 1}}, "harvest"),
        (ACTION_PROMPT, {"question": "Build a Power Plant", "snapshot": {
            "cash": 2000, "available_production": [{"id": "powr", "display_name": "Power Plant"}]}}, "build"),
        (ACTION_PROMPT, {"question": "Attack the hidden enemy base", "snapshot": {
            "visible_enemies": [], "owned_units": []}}, "answer"),
        (ACTION_PROMPT, {"question": "Sell every building", "snapshot": {
            "owned_buildings": [{"id": 12, "display_name": "Power Plant"}]}}, "answer"),
    ]
    failures = 0
    for system, context, expected in checks:
        started = time.monotonic()
        payload = {"model": args.model, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(context)}],
            "max_tokens": 180, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
        request = urllib.request.Request(args.url.rstrip("/") + "/v1/chat/completions",
                                         data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            answer = json.load(response)["choices"][0]["message"]["content"]
        elapsed = time.monotonic() - started
        passed = expected in answer.lower() and elapsed <= 5
        if system == ACTION_PROMPT:
            try:
                result = json.loads(answer)
                passed = passed and (result.get("mode") == "answer" if expected == "answer" else
                                    result.get("commands") == [{"action": "build", "item_type": "powr"}])
                if expected == "answer":
                    passed = passed and not result.get("commands") and any(
                        word in str(result.get("answer", "")).lower() for word in ("cannot", "can't", "unable", "not allowed"))
            except (ValueError, TypeError):
                passed = False
        else:
            passed = passed and len(answer.split()) <= 22
        failures += not passed
        print(json.dumps({"passed": passed, "seconds": round(elapsed, 3), "expected": expected, "response": answer}))
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
