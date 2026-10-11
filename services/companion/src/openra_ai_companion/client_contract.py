from __future__ import annotations

CONTRACT_VERSION = 1


def contract(timeout_seconds: float = 20.0) -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "loopback-local-companion",
        "hosted_enabled_by_default": False,
        "endpoints": {
            "contract": "GET /v1/contract",
            "state": "GET /v1/state",
            "advice": "POST /v1/advice",
            "propose": "POST /v1/proposals",
            "confirm": "POST /v1/proposals/confirm",
            "cancel": "POST /v1/proposals/cancel",
            "interrupt": "POST /v1/interrupt",
        },
        "request": {"contract_version": CONTRACT_VERSION},
        "model_timeout_seconds": timeout_seconds,
        "client_timeout_seconds": timeout_seconds + 5,
        "proposal_expiry_seconds": 300,
        "application": {
            "requires_explicit_proposal_id": True,
            "requires_player_confirmation": True,
            "live_validation": True,
            "authority": "native engine order bridge; accepted does not imply completed",
            "retry": "poll state after a lost confirmation response; never choose the latest proposal implicitly",
        },
        "fallback": {
            "offline_or_timeout": "leave authoritative gameplay running; interrupt request, discard late advice, keep manual controls",
            "no_model": "deterministic alerts and grounded strategy answers remain available",
            "expired_or_rejected": "nothing applied; request a fresh proposal",
        },
    }


def validate_request(payload: object, field: str) -> str:
    if not isinstance(payload, dict) or type(payload.get("contract_version")) is not int or payload["contract_version"] != CONTRACT_VERSION:
        raise ValueError("contract_version must be 1")
    value = payload.get(field)
    limit = 4096 if field in {"question", "instruction"} else 160
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return value.strip()
