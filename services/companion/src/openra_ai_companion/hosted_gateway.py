"""Client side of the RTS AI hosted proxy (rtsai.net/api/ai/v1).

The loopback gateway owns the install token: it is requested once on first
launch, stored encrypted with Windows DPAPI in provider.json, and never given to
the game or the companion. Text and vision requests are forwarded with that
token; speech stays on this machine. Failures are classified into a small set of
states the HUD can show, and a short backoff stops a dead or exhausted proxy
from adding latency to every alert.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

DEFAULT_HOSTED_ENDPOINT = "https://rtsai.net/api/ai/v1"
HOSTED_MODEL = "claude-haiku-4-5"

# States reported by the proxy's x-rtsai-ai-state header plus the gateway's own
# "offline". Every state except "ok" and "invalid" moves the brain to the local
# fallback (when installed) or to deterministic alert lines.
FALLBACK_STATES = frozenset({"offline", "unauthorized", "allowance", "rate_limited", "paused", "budget", "unavailable", "upstream"})
_BACKOFF_SECONDS = {
    "offline": 30.0,
    "unauthorized": 300.0,
    "allowance": 900.0,
    "rate_limited": 30.0,
    "paused": 300.0,
    "budget": 900.0,
    "unavailable": 60.0,
    "upstream": 20.0,
}
_STATUS_FOR_STATE = {
    "offline": 503,
    "unauthorized": 401,
    "allowance": 429,
    "rate_limited": 429,
    "paused": 503,
    "budget": 503,
    "unavailable": 503,
    "upstream": 503,
}
_MESSAGES = {
    "offline": "RTS AI hosted service is unreachable.",
    "unauthorized": "RTS AI could not register this install.",
    "allowance": "Today's hosted AI allowance is used up. It resets at 00:00 UTC.",
    "rate_limited": "Too many AI requests this minute.",
    "paused": "Hosted AI is paused by the operator.",
    "budget": "Hosted AI has reached today's capacity.",
    "unavailable": "Hosted AI is temporarily unavailable.",
    "upstream": "Hosted AI is temporarily unavailable.",
}


def hosted_endpoint(configured: str = "") -> str:
    value = os.environ.get("OPENRA_AI_HOSTED_ENDPOINT", "").strip() or configured.strip() or DEFAULT_HOSTED_ENDPOINT
    return value.rstrip("/")


@dataclass
class HostedReply:
    status: int
    payload: bytes
    content_type: str = "application/json"
    state: str = "ok"
    headers: dict[str, str] = field(default_factory=dict)


def _classify(status: int, payload: bytes, header_state: str) -> str:
    if status == 0:
        return "offline"
    if 200 <= status < 300:
        return "ok"
    state = header_state.strip().lower()
    if not state:
        try:
            state = str(json.loads(payload).get("error", {}).get("rtsai_state", "")).lower()
        except (ValueError, AttributeError):
            state = ""
    if state in FALLBACK_STATES or state == "invalid":
        return state
    if status == 401:
        return "unauthorized"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "upstream"
    return "invalid"


class HostedClient:
    """Token lifecycle, forwarding and backoff for the hosted proxy."""

    def __init__(
        self,
        endpoint: str,
        load_token: Callable[[], str],
        save_token: Callable[[str], None],
        *,
        timeout: float = 18.0,
        version: str = "",
    ):
        self.endpoint = endpoint.rstrip("/")
        self._load_token = load_token
        self._save_token = save_token
        self.timeout = timeout
        self.version = version or os.environ.get("OPENRA_AI_VERSION", "development")
        self._lock = threading.Lock()
        self._token: str | None = None
        self._state = {
            "state": "ok",
            "route": "hosted",
            "detail": "",
            "retry_at": 0.0,
            "remaining_usd": None,
            "updated_at": time.time(),
        }

    # -- token -----------------------------------------------------------------
    def _http(self, method: str, path: str, body: bytes | None, headers: dict[str, str]) -> tuple[int, bytes, dict[str, str]]:
        request = urllib.request.Request(f"{self.endpoint}{path}", data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read(), {key.lower(): value for key, value in response.headers.items()}
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), {key.lower(): value for key, value in (exc.headers or {}).items()}
        except (OSError, TimeoutError, urllib.error.URLError):
            return 0, b"", {}

    def acquire_token(self) -> str:
        """Zero-click registration: POST /install once, then keep the token under DPAPI."""
        status, payload, headers = self._http(
            "POST",
            "/install",
            json.dumps({"client": "rtsai-companion", "version": self.version}).encode("utf-8"),
            {"Content-Type": "application/json", "Accept": "application/json"},
        )
        if status != 201:
            state = _classify(status, payload, headers.get("x-rtsai-ai-state", ""))
            raise HostedUnavailable(state if state in FALLBACK_STATES else "unauthorized", status, payload, headers)
        token = str(json.loads(payload).get("token", ""))
        if not token:
            raise HostedUnavailable("unauthorized", 502, b"", {})
        self._save_token(token)
        self._token = token
        return token

    def token(self, *, refresh: bool = False) -> str:
        with self._lock:
            if refresh:
                self._token = None
                self._save_token("")
            if self._token:
                return self._token
            try:
                stored = self._load_token()
            except Exception:
                stored = ""
            if stored:
                self._token = stored
                return stored
            return self.acquire_token()

    # -- state -----------------------------------------------------------------
    def state(self) -> dict:
        with self._lock:
            value = dict(self._state)
        value["backoff_seconds"] = max(0.0, round(value["retry_at"] - time.time(), 1))
        return value

    def _record(self, state: str, *, retry_after: float | None = None, detail: str = "", remaining: str | None = None) -> None:
        with self._lock:
            self._state["state"] = state
            self._state["detail"] = detail[:200]
            self._state["updated_at"] = time.time()
            if remaining is not None:
                try:
                    self._state["remaining_usd"] = float(remaining)
                except ValueError:
                    pass
            if state in FALLBACK_STATES:
                cap = _BACKOFF_SECONDS[state]
                wait = min(cap, retry_after) if retry_after and retry_after > 0 else cap
                self._state["retry_at"] = time.time() + wait
            else:
                self._state["retry_at"] = 0.0

    def set_route(self, route: str) -> None:
        with self._lock:
            self._state["route"] = route

    def backing_off(self) -> bool:
        with self._lock:
            return self._state["state"] in FALLBACK_STATES and time.time() < self._state["retry_at"]

    def synthetic_error(self) -> HostedReply:
        with self._lock:
            state = self._state["state"]
            detail = self._state["detail"] or _MESSAGES.get(state, "Hosted AI is unavailable.")
            retry = max(1, int(self._state["retry_at"] - time.time()))
        body = json.dumps({"error": {"code": f"hosted_{state}", "message": detail, "rtsai_state": state}}).encode("utf-8")
        return HostedReply(_STATUS_FOR_STATE.get(state, 503), body, state=state, headers={"Retry-After": str(retry)})

    # -- forwarding --------------------------------------------------------------
    def chat(self, body: bytes) -> HostedReply:
        """Forward one chat completion; re-register once if the token was rejected."""
        if self.backing_off():
            return self.synthetic_error()
        for attempt in range(2):
            try:
                token = self.token(refresh=attempt == 1)
            except HostedUnavailable as exc:
                self._record(exc.state, retry_after=exc.retry_after, detail=exc.detail)
                return self.synthetic_error()
            status, payload, headers = self._http(
                "POST",
                "/chat/completions",
                body,
                {"Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {token}"},
            )
            state = _classify(status, payload, headers.get("x-rtsai-ai-state", ""))
            if state == "unauthorized" and attempt == 0:
                continue
            retry_after = _retry_after(headers)
            detail = _error_message(payload) if state != "ok" else ""
            if state != "invalid":
                self._record(state, retry_after=retry_after, detail=detail, remaining=headers.get("x-rtsai-remaining-usd"))
            forwarded = {name: headers[name] for name in ("x-rtsai-remaining-usd", "x-rtsai-cost-usd", "retry-after") if name in headers}
            if status == 0:
                return self.synthetic_error()
            return HostedReply(status, payload, headers.get("content-type", "application/json"), state, forwarded)
        return self.synthetic_error()

    def refresh_status(self) -> dict:
        """Ask the proxy for allowance and service state without spending tokens."""
        try:
            token = self.token()
        except HostedUnavailable as exc:
            self._record(exc.state, retry_after=exc.retry_after, detail=exc.detail)
            return self.state()
        status, payload, headers = self._http("GET", "/status", None, {"Accept": "application/json", "Authorization": f"Bearer {token}"})
        if status == 200:
            try:
                report = json.loads(payload)
            except ValueError:
                report = {}
            state = str(report.get("state", "ok"))
            self._record(state if state in FALLBACK_STATES else "ok", remaining=str(report.get("remaining_usd", "")) or None,
                         detail=_MESSAGES.get(state, ""))
            merged = self.state()
            merged["allowance"] = report
            return merged
        state = _classify(status, payload, headers.get("x-rtsai-ai-state", ""))
        if state in FALLBACK_STATES:
            self._record(state, retry_after=_retry_after(headers), detail=_error_message(payload))
        return self.state()


class HostedUnavailable(RuntimeError):
    def __init__(self, state: str, status: int, payload: bytes, headers: dict[str, str]):
        self.state = state
        self.status = status
        self.retry_after = _retry_after(headers)
        self.detail = _error_message(payload) or _MESSAGES.get(state, "")
        super().__init__(self.detail)


def _retry_after(headers: dict[str, str]) -> float | None:
    try:
        return float(headers.get("retry-after", ""))
    except ValueError:
        return None


def _error_message(payload: bytes) -> str:
    try:
        error = json.loads(payload).get("error", {})
        return str(error.get("message", "") if isinstance(error, dict) else error)[:200]
    except (ValueError, AttributeError):
        return ""


def prepare_hosted_body(body: bytes, model: str = HOSTED_MODEL) -> bytes:
    """Point any companion route name at the hosted model and drop local-only knobs."""
    request = json.loads(body)
    request["model"] = model
    request.pop("truncate_prompt_tokens", None)
    request.pop("chat_template_kwargs", None)
    return json.dumps(request).encode("utf-8")


def prepare_local_body(body: bytes, *, vision: bool) -> bytes:
    """Re-target a hosted request at the installed local model."""
    request = json.loads(body)
    request["model"] = "local-coder"
    if not vision:
        for message in request.get("messages", []):
            content = message.get("content")
            if isinstance(content, list):
                kept = [part for part in content if not (isinstance(part, dict) and part.get("type") == "image_url")]
                if len(kept) != len(content):
                    kept.append({"type": "text", "text": "(Map images omitted: the local fallback model reads structured state only.)"})
                message["content"] = kept
    return json.dumps(request).encode("utf-8")
