# Local companion client contract, version 1

11 October 2026. This contract is for the loopback companion, alongside the
native order bridge. Static public browser builds do not launch or expose this
service. No hosted provider was activated or called during validation.

Reads and mutations require a loopback Host with the actual service port. If Origin is
present, it must be the same HTTP origin as Host; null, foreign origins and
DNS-rebinding hosts are refused before private reads or body/action dispatch. Native clients and
trusted server proxies may omit Origin. Body lengths must be a single bounded
nonnegative integer; chunked/ambiguous lengths are refused. Audio bodies keep
their original binary content type. CORS preflights use the same origin guard.

The browser local proxy must separately guard its incoming Host and Origin
before starting/stopping the companion or forwarding mutations. It currently
strips upstream Origin, so a no-Origin upstream request is not proof that the
browser request was trusted. S06 must enforce same-origin/loopback requests at
that outer boundary (or authenticated proxy traffic). Do not expose the proxy
as an arbitrary cross-origin forwarder.

Read `GET /v1/contract` before enabling client controls. Unsupported versions
must disable apply while manual gameplay continues. State remains at
`GET /v1/state`: `snapshot`, `pending_actions`, `ai_service`, and the existing
strategy/brain fields. These are advisory observations; engine rules and its
accepted order receipts own authoritative gameplay.

| Request | Body | Response |
|---|---|---|
| `POST /v1/advice` | `{"contract_version":1,"question":"What should I do?"}` | version plus the existing CompanionResponse |
| `POST /v1/proposals` | `{"contract_version":1,"instruction":"deploy the mcv"}` | answer, explanation, rejection or `metadata.action.state=pending` with a proposal ID |
| `POST /v1/proposals/confirm` | `{"contract_version":1,"proposal_id":"<displayed ID>"}` | `executed`, `rejected`, `expired`, `unavailable`, `failed` or `missing` action state |
| `POST /v1/proposals/cancel` | same explicit ID | cancellation or missing; no orders |
| `POST /v1/interrupt` | `{}` | interrupted generation; discard late response |

A proposal does not execute. Proposal text cannot confirm/cancel an earlier
proposal or change native doctrine. A browser apply button confirms only the ID
shown with the displayed offer. Confirmation revalidates current owned actors,
fog-respecting targets, production, costs, strategy reserves and bridge readiness.
Offers expire after five minutes. Parallel/repeated confirmations send at most
one dispatch for an ID. `executed` means the engine accepted the order, not that
the goal finished. Poll state/brain verification for completion.

A response keeps `text`, `source`, `interrupted`, `utterance_id`, `insight`,
`latency_ms`, `metadata`; new endpoints add `contract_version:1`. HTTP400 means
invalid request or version; handle HTTP502/router and HTTP503/setup failures as
unavailable. A model failure can also return HTTP200 with
`source=deterministic-fallback`, `metadata.degraded=true`; do not treat that as
successful model inference. Show local/mock/alerts route honestly.

The contract reports the configured model timeout (default20 seconds) and a
client deadline five seconds longer. On client timeout/offline, keep gameplay
and manual controls running, interrupt outstanding advice, and ignore stale
response generations. After a lost confirmation response, poll state: do not
retry an implicit latest offer or infer failure means nothing was dispatched.
Request a new offer only after the old one's state is known. No model preserves
grounded strategy answers and critical deterministic alerts.

## Existing clients

Legacy `/v1/actions/propose` retains its response shape but now uses the same
proposal-only guard. `/v1/actions/confirm` and `/cancel` retain their existing
explicit-ID behavior and the native player's deliberate hotkey compatibility
(blank ID selects the newest held offer). The existing voice `/v1/ask` intentionally
accepts a player's explicit spoken confirmation. These compatibility surfaces
still use the core's live validation and duplicate-dispatch guard. Browser apply
must use the new explicit-ID endpoints. Native clients can migrate hotkeys to the
ID obtained from `/v1/state` without engine/protobuf changes.

## Portable source launch

Consumer sessions must first copy the entire frozen source input supplied in
S04's `CONSUMER-CONTRACT.json` to their own writable directory. Create a private
Python3.11+ virtual environment and install `services/companion` and
`services/worldgen` from that copy. The validated Python runtime is3.12. NumPy is
required by tactical vision; a plain system Python without it cannot launch the
full companion. The S04 lock receipt records resolved local dependency versions.
Use isolated `OPENRA_AI_DATA_DIR`, `PYTHONPYCACHEPREFIX`, model/scratch paths and
available ports. Do not copy user settings, credentials or installed model state.

Set `OPENRA_AI_MODEL_PROVIDER=local`, `OPENRA_AI_HOSTED_ENABLED=0`,
`OPENRA_AI_ROUTER_URL=http://127.0.0.1:<own local/mock gateway port>`,
`OPENRA_AI_ROOT=<private source>`, `OPENRA_AI_CATALOG=<private catalog/factions.json>`,
`OPENRA_AI_FACTION_DIGEST_DIR=<private digest dir>`,
`OPENRA_AI_ENGINE_DIR=<private copied fixed-engine vocabulary or native engine>`, and
`OPENAI_AGENTS_DISABLE_TRACING=1`. Start with the private interpreter:

```sh
python -m openra_ai_companion.cli watch \
  --bridge 127.0.0.1:<own gRPC bridge port> \
  --control-port <own HTTP port> --no-speak
```

Enable speech only after local audio acceptance. For HTTP-only contract tests,
`python -m openra_ai_companion.cli serve --host 127.0.0.1 --port <own HTTP port>`
starts without a game bridge. The browser's same-origin local proxy supplies
snapshots via its existing gRPC relay and proxies companion HTTP; keep that
separate from static hosting. The native client uses the same HTTP contract and
its native gRPC bridge. No Python `.exe` path is assumed on macOS/Linux. The frozen engine-vocabulary
input contains the shipping engine's generated `mods/ra/fluent/rules.ftl`; it
supplies full legacy English names without reading a live sibling/old worktree.
It is vocabulary, not an executable engine or a claim that the historical
owned-game add-on is the product's Classic mode.

## Hosted server seam

`HostedPolicy.dispatch` is a tested, single-process reference adoption seam for
a remote authenticated proxy: verified UID, atomic worst-case reservations,
integer micro-USD, per-user/global spend/rate/concurrency, server-only provider
closure, conservative timeout settlement. It has deny-by-default limits. It is
not deployed cost enforcement. Production must use the remote durable store,
verified server authentication, conservative token/image/output caps, secret
management and an approved budget before activation. No client API key or
client-provided UID can be authoritative. All provider integration/deployment
and any real-cost acceptance remain pending with the owner.
