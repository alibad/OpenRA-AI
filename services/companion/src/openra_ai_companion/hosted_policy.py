from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable


class PolicyDenied(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class HostedLimits:
    enabled: bool = False
    per_user_daily_micro_usd: int = 0
    global_daily_micro_usd: int = 0
    requests_per_minute: int = 0
    concurrent_per_user: int = 0
    concurrent_global: int = 0


class HostedPolicy:
    """Atomic reference accounting for a single local server process.

    A deployed proxy must adopt the same transaction contract in a durable store.
    No provider secrets, prompts or token bodies are held in this store.
    """

    def __init__(self, limits: HostedLimits = HostedLimits(), *, clock: Callable[[], float] = time.time):
        self.limits = limits
        self.clock = clock
        self._lock = threading.Lock()
        self._users: dict[tuple[str, int], int] = {}
        self._global: dict[int, int] = {}
        self._rate: dict[tuple[str, int], int] = {}
        self._active: dict[str, tuple[str, int, int]] = {}
        self._finished: set[str] = set()

    def reserve(self, uid: str, request_id: str, worst_case_micro_usd: int) -> None:
        with self._lock:
            if not self.limits.enabled:
                raise PolicyDenied("hosted_disabled")
            if not isinstance(uid, str) or not uid.strip():
                raise PolicyDenied("authentication_required")
            if not isinstance(request_id, str) or not request_id or len(request_id) > 160:
                raise PolicyDenied("invalid_request_id")
            if type(worst_case_micro_usd) is not int or worst_case_micro_usd <= 0:
                raise PolicyDenied("invalid_reservation")
            if request_id in self._active or request_id in self._finished:
                raise PolicyDenied("duplicate_request")
            day, minute = int(self.clock() // 86400), int(self.clock() // 60)
            user_key, rate_key = (uid, day), (uid, minute)
            active_user = sum(1 for user, _, _ in self._active.values() if user == uid)
            if active_user >= self.limits.concurrent_per_user or len(self._active) >= self.limits.concurrent_global:
                raise PolicyDenied("concurrency_limited")
            if self._rate.get(rate_key, 0) >= self.limits.requests_per_minute:
                raise PolicyDenied("rate_limited")
            if self._users.get(user_key, 0) + worst_case_micro_usd > self.limits.per_user_daily_micro_usd:
                raise PolicyDenied("daily_allowance_exhausted")
            if self._global.get(day, 0) + worst_case_micro_usd > self.limits.global_daily_micro_usd:
                raise PolicyDenied("global_budget_exhausted")
            self._users[user_key] = self._users.get(user_key, 0) + worst_case_micro_usd
            self._global[day] = self._global.get(day, 0) + worst_case_micro_usd
            self._rate[rate_key] = self._rate.get(rate_key, 0) + 1
            self._active[request_id] = (uid, day, worst_case_micro_usd)

    def settle(self, request_id: str, actual_micro_usd: int | None) -> None:
        with self._lock:
            if request_id not in self._active:
                raise PolicyDenied("unknown_reservation")
            uid, day, reserved = self._active[request_id]
            if actual_micro_usd is not None and (type(actual_micro_usd) is not int or not 0 <= actual_micro_usd <= reserved):
                raise PolicyDenied("cost_exceeds_reservation")
            actual = reserved if actual_micro_usd is None else actual_micro_usd
            self._users[uid, day] -= reserved - actual
            self._global[day] -= reserved - actual
            del self._active[request_id]
            self._finished.add(request_id)

    def dispatch(self, bearer: str, request_id: str, worst_case_micro_usd: int,
                 authenticate: Callable[[str], str], provider: Callable[[], tuple[object, int]]) -> object:
        if not self.limits.enabled:
            raise PolicyDenied("hosted_disabled")
        try:
            uid = authenticate(bearer)
        except Exception as exc:
            raise PolicyDenied("authentication_required") from exc
        self.reserve(uid, request_id, worst_case_micro_usd)
        try:
            response, cost = provider()
        except Exception:
            self.settle(request_id, None)
            raise
        try:
            self.settle(request_id, cost)
        except PolicyDenied:
            self.settle(request_id, None)
            raise
        return response

    def usage(self, uid: str) -> dict:
        with self._lock:
            day = int(self.clock() // 86400)
            return {"used_or_reserved_micro_usd": self._users.get((uid, day), 0),
                    "global_used_or_reserved_micro_usd": self._global.get(day, 0),
                    "in_flight": sum(1 for user, _, _ in self._active.values() if user == uid)}
