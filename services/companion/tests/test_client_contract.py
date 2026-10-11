from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from openra_ai_companion.core import Companion
from openra_ai_companion.hosted_gateway import HostedClient
from openra_ai_companion.hosted_policy import HostedLimits, HostedPolicy, PolicyDenied
from openra_ai_companion.models import ActionReceipt
from openra_ai_companion.router import RouterError
from openra_ai_companion.server import create_server
from test_companion import FakePlayer, FakeRouter, snapshot


@pytest.fixture
def api():
    executions = []
    companion = Companion(router=FakeRouter(), action_executor=lambda request_id, tick, commands:
                          (executions.append(request_id) or ActionReceipt(request_id, True, tick, "Queued")))
    companion.update_snapshot(snapshot(map_info={"width": 64, "height": 64},
                                      units=[{"actor_id": 1, "type": "mcv", "speed": 1}]))
    server = create_server(port=0, companion=companion, player=FakePlayer())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(path, payload=None, headers=None):
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{path}", data=body,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)
    request.base_url = f"http://127.0.0.1:{server.server_port}"
    yield request, companion, executions
    server.shutdown()
    server.server_close()
    thread.join()


def test_http_contract_propose_confirm_and_duplicate(api):
    request, _, executions = api
    code, contract = request("/v1/contract")
    assert code == 200 and contract["contract_version"] == 1
    code, offer = request("/v1/proposals", {"contract_version": 1, "instruction": "deploy the mcv"})
    assert code == 200 and not executions
    assert offer["metadata"]["action"]["state"] == "pending"
    proposal_id = offer["metadata"]["action"]["proposal_id"]
    payload = {"contract_version": 1, "proposal_id": proposal_id}
    assert request("/v1/proposals/confirm", payload)[1]["metadata"]["action"]["state"] == "executed"
    assert request("/v1/proposals/confirm", payload)[1]["metadata"]["action"]["state"] == "missing"
    assert executions == [proposal_id]


@pytest.mark.parametrize("payload", [{}, {"contract_version": True, "instruction": "yes"},
                                       {"contract_version": 2, "instruction": "yes"},
                                       {"contract_version": 1, "instruction": "yes"},
                                       {"contract_version": 1, "instruction": "switch to rush"}])
def test_propose_cannot_confirm_or_change_doctrine(api, payload):
    request, _, executions = api
    assert request("/v1/proposals", payload)[0] == 400
    assert executions == []


def test_confirm_requires_id_cancel_preserves_manual_control(api):
    request, _, executions = api
    assert request("/v1/proposals/confirm", {"contract_version": 1})[0] == 400
    offer = request("/v1/proposals", {"contract_version": 1, "instruction": "deploy the mcv"})[1]
    payload = {"contract_version": 1, "proposal_id": offer["metadata"]["action"]["proposal_id"]}
    assert request("/v1/proposals/cancel", payload)[1]["metadata"]["action"]["state"] == "cancelled"
    assert request("/v1/proposals/confirm", payload)[1]["metadata"]["action"]["state"] == "missing"
    assert not executions


def test_advice_is_grounded_when_model_times_out(api):
    request, companion, executions = api
    with patch.object(companion.router, "chat", side_effect=RouterError("timed out", state="offline")):
        code, response = request("/v1/advice", {"contract_version": 1, "question": "What should I do?"})
    assert code == 200 and response["text"] and not executions


def test_parallel_confirmations_dispatch_only_once(api):
    request, companion, executions = api
    offer = request("/v1/proposals", {"contract_version": 1, "instruction": "deploy the mcv"})[1]
    proposal_id = offer["metadata"]["action"]["proposal_id"]
    barrier = threading.Barrier(2)
    withdraw = companion._withdraw
    def simultaneous(proposal):
        barrier.wait(timeout=3)
        return withdraw(proposal)
    with patch.object(companion, "_withdraw", side_effect=simultaneous):
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: companion.confirm_action(proposal_id), range(2)))
    assert executions == [proposal_id]
    assert sorted(r.metadata["action"]["state"] for r in results) == ["executed", "missing"]


def test_hosted_disabled_never_opens_network(monkeypatch):
    monkeypatch.delenv("OPENRA_AI_HOSTED_ENABLED", raising=False)
    client = HostedClient("https://rtsai.net/api/ai/v1", lambda: "", lambda _: None)
    with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
        reply = client.chat(b"{}")
        state = client.refresh_status()
    assert reply.status == 503 and reply.state == state["state"] == "paused"


def policy(**changes):
    values = dict(enabled=True, per_user_daily_micro_usd=100, global_daily_micro_usd=150,
                  requests_per_minute=20, concurrent_per_user=20, concurrent_global=20)
    return HostedPolicy(HostedLimits(**(values | changes)), clock=lambda: 86401)


def test_policy_disabled_and_auth_denied_before_provider():
    calls = []
    for store in [HostedPolicy(), policy()]:
        with pytest.raises(PolicyDenied):
            store.dispatch("bad", "id", 10, lambda _: "", lambda: calls.append(1))
    assert not calls


def test_policy_concurrent_cannot_overspend_and_users_are_isolated():
    store = policy()
    def reserve(index):
        try:
            store.reserve("user-one", f"id-{index}", 30)
            return True
        except PolicyDenied:
            return False
    with ThreadPoolExecutor(10) as pool:
        assert sum(pool.map(reserve, range(10))) == 3
    assert store.usage("user-one")["used_or_reserved_micro_usd"] == 90
    store.reserve("user-two", "other", 30)
    assert store.usage("user-two")["used_or_reserved_micro_usd"] == 30
    with pytest.raises(PolicyDenied, match="global_budget"):
        store.reserve("user-three", "over-global", 40)


def test_policy_rate_concurrency_settlement_and_retries():
    store = policy(concurrent_per_user=1, requests_per_minute=2)
    store.reserve("uid", "first", 40)
    with pytest.raises(PolicyDenied, match="concurrency"):
        store.reserve("uid", "second", 10)
    store.settle("first", 5)
    assert store.usage("uid")["used_or_reserved_micro_usd"] == 5
    store.reserve("uid", "second", 10)
    store.settle("second", 0)
    with pytest.raises(PolicyDenied, match="duplicate"):
        store.reserve("uid", "first", 40)
    with pytest.raises(PolicyDenied, match="rate"):
        store.reserve("uid", "third", 10)


def test_policy_dispatch_unknown_upstream_cost_keeps_reserved_charge():
    store = policy()
    def fail():
        raise TimeoutError("response lost")
    with pytest.raises(TimeoutError):
        store.dispatch("verified-token", "first", 40, lambda _: "verified-uid", fail)
    assert store.usage("verified-uid") == {"used_or_reserved_micro_usd": 40,
                                           "global_used_or_reserved_micro_usd": 40, "in_flight": 0}
    assert store.dispatch("verified-token", "second", 40, lambda _: "verified-uid", lambda: ("mock answer", 5)) == "mock answer"
    assert store.usage("verified-uid")["used_or_reserved_micro_usd"] == 45


def test_legacy_propose_is_compatible_and_cannot_confirm(api):
    request, _, executions = api
    code, offer = request("/v1/actions/propose", {"instruction": "deploy the mcv"})
    assert code == 200 and offer["metadata"]["action"]["state"] == "pending"
    assert request("/v1/actions/propose", {"instruction": "yes"})[0] == 400
    assert not executions
    payload = {"proposal_id": offer["metadata"]["action"]["proposal_id"]}
    assert request("/v1/actions/confirm", payload)[1]["metadata"]["action"]["state"] == "executed"
    assert len(executions) == 1


def test_confirmation_revalidates_changed_battlefield(api):
    request, companion, executions = api
    offer = request("/v1/proposals", {"contract_version": 1, "instruction": "deploy the mcv"})[1]
    companion.latest_snapshot = snapshot(tick=1001, units=[])
    code, response = request("/v1/proposals/confirm", {"contract_version": 1, "proposal_id": offer["metadata"]["action"]["proposal_id"]})
    assert code == 200 and response["metadata"]["action"]["state"] == "rejected"
    assert not executions


def test_policy_authentication_failure_does_not_dispatch():
    store = policy()
    calls = []
    def invalid(_):
        raise ValueError("unverified token")
    with pytest.raises(PolicyDenied, match="authentication"):
        store.dispatch("invalid-token", "request", 10, invalid, lambda: calls.append(1))
    assert not calls and store.usage("someone")["global_used_or_reserved_micro_usd"] == 0


def test_advice_yes_cannot_confirm_pending_offer(api):
    request, _, executions = api
    offer = request("/v1/proposals", {"contract_version": 1, "instruction": "deploy the mcv"})[1]
    assert offer["metadata"]["action"]["state"] == "pending"
    assert request("/v1/advice", {"contract_version": 1, "question": "yes"})[0] == 200
    assert not executions
    assert request("/v1/state")[1]["pending_action"]["proposal_id"] == offer["metadata"]["action"]["proposal_id"]


@pytest.mark.parametrize("headers", [{"Origin": "https://unrelated.example"}, {"Origin": "null"},
                                     {"Host": "unrelated.example:8787"}, {"Host": "127.0.0.1:1"},
                                     {"Origin": "http://localhost:3000"}])
def test_untrusted_mutation_cannot_confirm_legacy_offer(api, headers):
    request, _, executions = api
    request("/v1/actions/propose", {"instruction": "deploy the mcv"})
    code, response = request("/v1/actions/confirm", {}, {"Content-Type": "text/plain", **headers})
    assert code == 403 and response["error"] == "untrusted_origin_or_host"
    assert not executions


@pytest.mark.parametrize("length", ["-1", "999999999999", "1.5", "20000001"])
def test_bad_content_length_cannot_dispatch(api, length):
    request, _, executions = api
    request("/v1/actions/propose", {"instruction": "deploy the mcv"})
    assert request("/v1/actions/confirm", {}, {"Content-Length": length})[0] == 400
    assert not executions


def test_same_origin_and_no_origin_native_requests_remain_valid(api):
    request, companion, executions = api
    request("/v1/actions/propose", {"instruction": "deploy the mcv"})
    assert request("/v1/actions/confirm", {}, {"Origin": request.base_url})[0] == 200
    assert len(executions) == 1


def test_binary_transcription_remains_compatible_with_native_clients(api):
    request, companion, _ = api
    body = b"RIFFtestaudio"
    with patch.object(companion, "transcribe", wraps=companion.transcribe) as transcribe:
        req = urllib.request.Request(request.base_url + "/v1/transcribe", data=body,
                                     headers={"Content-Type": "audio/wav"})
        with urllib.request.urlopen(req, timeout=3) as response:
            assert response.status == 200
    transcribe.assert_called_once_with(body, "question.wav")


@pytest.mark.parametrize("headers", [{"Host": "unrelated.example:8787"}, {"Origin": "https://unrelated.example"}])
def test_untrusted_get_cannot_read_private_state(api, headers):
    request, companion, _ = api
    with patch.object(companion.router, "health", side_effect=AssertionError("state must not be read")):
        code, value = request("/v1/state", headers=headers)
    assert code == 403 and value == {"error": "untrusted_origin_or_host"}
