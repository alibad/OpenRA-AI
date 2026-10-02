"""A mock OpenAI-compatible provider for the explicit external-provider path.

It never contacts the internet and needs no real key.  It records what the
companion/gateway sent (model, response_format, Authorization) and answers
with a typed order intent chosen by simple keyword rules, so the whole
external route -- companion -> loopback gateway in external mode -> provider
-> schema validation -> grounding -- can be exercised deterministically.

``--reject-json-schema`` imitates providers that only support ``json_object``.

    python services/companion/evals/nl_orders/mock_provider.py --port 4700
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def intent_for(text: str) -> dict:
    lowered = text.lower()
    player = re.search(r'Player: "(.*)"\s*$', text, re.S)
    said = (player.group(1) if player else lowered).lower()

    def step(action: str, **values) -> dict:
        return {"action": action, "units": "", "count": 0, "item": "", "target": "", "stance": "", **values}

    for direction in ("north", "south", "east", "west"):
        if direction in said and any(word in said for word in ("move", "go", "send", "head")):
            units = "all tanks" if "tank" in said else "everyone"
            action = "attack_move" if "attack" in said else "move"
            return {"intent": "command", "reply": "", "steps": [step(action, units=units, target=direction)]}
    if said.startswith(("how", "what", "where", "why", "is ", "are ")):
        return {"intent": "question", "reply": "", "steps": []}
    if any(word in said for word in ("nuke", "surrender", "chronosphere")):
        return {"intent": "refuse", "reply": "That can't be ordered by voice.", "steps": []}
    match = re.search(r"(?:train|build)\s+(\w+)\s+(.+)", said)
    if match:
        count = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}.get(match.group(1), 1)
        return {"intent": "command", "reply": "", "steps": [step("train", count=count, item=match.group(2))]}
    return {"intent": "clarify", "reply": "Which units should do what, and where?", "steps": []}


class MockProvider(BaseHTTPRequestHandler):
    reject_json_schema = False
    requests: list[dict] = []
    lock = threading.Lock()

    def log_message(self, *_):  # noqa: ANN002
        pass

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self._send(200, {"data": [{"id": "mock-gpt", "object": "model"}]})

    def do_POST(self) -> None:  # noqa: N802
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        response_format = request.get("response_format") or {}
        with self.lock:
            type(self).requests.append({
                "path": self.path,
                "model": request.get("model"),
                "response_format": response_format.get("type"),
                "authorization": self.headers.get("Authorization", ""),
            })
        if self.reject_json_schema and response_format.get("type") == "json_schema":
            self._send(400, {"error": {"message": "response_format json_schema is not supported by this model"}})
            return
        text = " ".join(
            str(message.get("content")) for message in request.get("messages", [])
            if isinstance(message.get("content"), str)
        )
        content = json.dumps(intent_for(text)) if "Vocabulary:" in text else "Holding steady; no threats visible."
        self._send(200, {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": len(text) // 4, "completion_tokens": len(content) // 4},
        })


def start(port: int = 0, *, reject_json_schema: bool = False) -> ThreadingHTTPServer:
    handler = type("ConfiguredMockProvider", (MockProvider,), {"reject_json_schema": reject_json_schema, "requests": []})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=4700)
    parser.add_argument("--reject-json-schema", action="store_true")
    args = parser.parse_args()
    server = start(args.port, reject_json_schema=args.reject_json_schema)
    print(f"mock provider on http://127.0.0.1:{server.server_port}/v1", flush=True)
    threading.Event().wait()
