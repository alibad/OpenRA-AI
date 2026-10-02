# Hosted AI (Phase 3)

Updated 2 October 2026. Branches: `rtsai/hosted-ai` in OpenRA-AI and in
RTSAI-Web. Neither branch is pushed or deployed.

On a first launch with no AI setup, the co-commander's text and vision go to
a proxy on rtsai.net that calls **Claude Haiku 4.5** (`claude-haiku-4-5`, chosen
by the owner). Speech stays on the player's machine: Whisper for speech-in,
Kokoro for speech-out. The model API key never leaves the server. When the
proxy is offline, paused, over the daily allowance or failing, the game falls
back to the installed local model (`local-coder`) if there is one, and to its
deterministic alert lines if not. The HUD says which of these is happening.

## How it fits together

```text
OpenRA ── companion (Python) ── loopback gateway :40xx ──HTTPS──> rtsai.net/api/ai/v1 ──> Anthropic Messages API
                                   │  install token (DPAPI)          │  ANTHROPIC_API_KEY (server only)
                                   │                                 │  quotas in Firestore
                                   ├─ /v1/audio/transcriptions ─> whisper-server (local)
                                   ├─ /v1/audio/speech ─────────> Kokoro (local)
                                   └─ fallback ─────────────────> llama-server local-coder (started on demand)
```

The game-facing contract is unchanged: the companion still speaks the
OpenAI-compatible chat-completions surface to its loopback gateway. Only the
gateway knows that a hosted proxy exists.

## The proxy (RTSAI-Web)

Code: `lib/hosted-ai/*`, routes under `app/api/ai/v1/`. Nitro packages every
route into the single Node.js Vercel function (`.vc-config.json`:
`launcherType: Nodejs`); there is no Edge runtime.

| Route | Purpose |
|---|---|
| `POST /api/ai/v1/install` | Zero-click registration. Returns an HS256 install token (jose, one-year expiry). Limited per hashed client IP per day. |
| `POST /api/ai/v1/chat/completions` | OpenAI-compatible chat completions served by Claude Haiku 4.5 through the official `@anthropic-ai/sdk`. |
| `GET /api/ai/v1/status` | Allowance, spend and service state for the HUD, without a model call. |
| `POST /api/ai/v1/link` | Account-linking seam: install token plus a Firebase ID token (verified with the existing `lib/firebase-token.ts`) raises the allowance. No UI calls it yet. |
| `GET /api/ai/v1/models` | Lists `claude-haiku-4-5`. |

### Translation

The companion does not stream: `router.py` and the Agents SDK runner used by
the MCP planner both make non-streaming calls. `stream: true` is refused with
400 `streaming_not_supported`.

| OpenAI chat completions | Anthropic Messages |
|---|---|
| `system` / `developer` messages | top-level `system` |
| `user` text and `image_url` base64 data URLs | `text` and base64 `image` blocks; remote image URLs are refused |
| `assistant.tool_calls` | `tool_use` blocks |
| `tool` messages | `tool_result` blocks in one user turn |
| `tools` (function) | `tools` with `input_schema` |
| `tool_choice` `auto` / `none` / `required` / named | `auto` / `none` / `any` / `tool` |
| `parallel_tool_calls: false` | `disable_parallel_tool_use: true` |
| `response_format` `json_schema` | `output_config.format` (schema sanitised to the supported subset: `additionalProperties: false`, numeric and length bounds removed; the companion re-validates) |
| `response_format` `json_object` | a system instruction |
| `max_tokens` / `max_completion_tokens` | clamped to `RTSAI_AI_MAX_TOKENS` (1,024) |
| `temperature`, `stop` | `temperature` (clamped to 0–1), `stop_sequences` |
| `reasoning_effort`, `verbosity`, `top_p`, `store`, `metadata`, `extra_body` | ignored |

Haiku 4.5 runs with no extended thinking and no `effort`. Requests that carry
tools (agent loops) set top-level automatic prompt caching so later turns read
the repeated tool schemas at 0.1×. Responses come back as `chat.completion`
objects with `usage` and an extra `rtsai` object (`cost_usd`,
`remaining_usd`, `daily_allowance_usd`, `resets_at`).

### Errors the game maps to HUD states

Every error carries `error.code`, `error.rtsai_state` and an
`x-rtsai-ai-state` header.

| HTTP | `code` | State | Game behaviour |
|---|---|---|---|
| 400 | `model_not_allowed`, `too_many_images`, `image_too_large`, `images_too_large`, `unsupported_image`, `streaming_not_supported`, `invalid_*`, `upstream_rejected` | `invalid` | Passed through; no fallback |
| 413 | `request_too_large` | `invalid` | Passed through |
| 401 | `install_token_missing`, `install_token_invalid`, `install_token_revoked` | `unauthorized` | Gateway re-registers once, then falls back |
| 429 | `daily_allowance_exhausted` (Retry-After: seconds to 00:00 UTC) | `allowance` | Fallback; retry after ≤15 min |
| 429 | `rate_limited`, `install_rate_limited` | `rate_limited` | Fallback; retry after ≤30 s |
| 503 | `service_paused` (kill switch) | `paused` | Fallback; retry after 5 min |
| 503 | `global_budget_exhausted` | `budget` | Fallback; retry after ≤15 min |
| 503 | `store_unavailable`, `upstream_not_configured` | `unavailable` | Fallback; retry after 1 min |
| 503 / 502 | `upstream_unavailable`, `upstream_busy`, `upstream_error` | `upstream` | Fallback; retry after 20 s |

### Quotas and spend

All accounting is integer micro-USD from the API's `usage`: input $1, output
$5, cache write $1.25 and cache read $0.10 per million tokens.

1. Before calling the model, a request reserves its worst case: input
   characters ÷ 3 plus image tokens (width × height ÷ 750) plus the full
   clamped output.
2. One atomic Firestore `commit` increments the install's daily total, the
   global daily total and the install's per-minute counter, and returns the new
   values. If any limit is exceeded, a second commit rolls the increments back
   and the request is refused (increment-then-check, so concurrent calls
   cannot overspend).
3. After the call, settlement replaces the reservation with the exact cost and
   records tokens. A failed upstream call releases its reservation.

The store sits behind one interface (`lib/hosted-ai/store.ts`): Firestore
REST with a server-only service account in production, and an in-memory store
for tests and local runs (refused when `VERCEL_ENV=production`).

| Collection | Contents | TTL field |
|---|---|---|
| `aiInstalls/{installId}` | creation time, `linkedUid`, `revoked` | none |
| `aiInstallIps/{hmac(ip)}_{day}` | installs issued per hashed IP | `expireAt` (+2 days) |
| `aiUsage/{installId}_{day}` | charged and spent micro-USD, calls, tokens | `expireAt` (+3 days) |
| `aiSpend/{day}` | global daily totals | `expireAt` (+60 days) |
| `aiRate/{installId}_{minute}` | per-minute request count | `expireAt` (+1 day) |

The global total is a single document. Firestore sustains about one write per
second per document comfortably; past roughly 30 concurrent players, shard
`aiSpend` before raising the cap.

### Guardrails

Model allowlist (`claude-haiku-4-5`, `rtsai-hosted`, `hosted-brain`; all served
by Haiku 4.5), output clamp of 1,024 tokens, at most 2 inline images, 400 KB
per image and 600 KB per request, a 2 MB body cap (hard ceiling 4 MB, under
Vercel's 4.5 MB), 80 messages, 64 tools, a 15 s upstream timeout with no SDK
retries, and the kill switch. Prompts and completions are never logged; the
proxy logs one line per call with an 8-character install prefix, token counts,
image count and size, cost and latency.

## The game (OpenRA-AI `services/companion`)

### Modes

`model_provider` selects one of three gateway modes. A first launch with no
saved provider (no environment variable, no `settings.json` value) now
defaults to `hosted`. Explicit choices always win.

| Provider | Gateway mode | Thinking | Voice |
|---|---|---|---|
| `hosted` (new default) | `hosted` | rtsai.net proxy (Claude Haiku 4.5) | local Whisper and Kokoro |
| `local` | `local` | local-coder (Qwen3-VL 2B) | local |
| `custom` | `external` | the endpoint chosen at install | the endpoint |

`openra-ai-runtime configure --mode hosted [--hosted-endpoint URL]` writes
`provider.json` and `settings.json` for an installer. The NSIS installer is
unchanged on this branch.

### First launch and the install token

The gateway (`local_runtime.py` + `hosted_gateway.py`) registers in the
background as soon as it starts in hosted mode. The token is stored in
`%APPDATA%/OpenRA-AI/provider.json` as `protected_install_token`, encrypted
with the existing DPAPI helper (`protect_secret`). It is never written to
`settings.json`, logged, or given to the companion or OpenRA. If the proxy
rejects the token, the gateway re-registers once. Re-running `configure` keeps
the token, so an install keeps its allowance.

### Fallback order

1. Hosted proxy.
2. On offline, 401, 429 or 5xx: the installed `local-coder`. The gateway starts
   llama-server on the first failure (it is not kept in memory while hosted AI
   works). Map images are dropped if the local profile has no projector.
3. While the local model loads, or if it is not installed: the gateway returns
   the error. The companion speaks the deterministic alert lines and answers
   questions with a one-sentence explanation ("Today's free hosted AI allowance
   is used up; it resets at midnight UTC. Critical alerts continue.").

After a failure the gateway backs off (offline 30 s, upstream 20 s, paused 5
min, allowance and budget up to 15 min, capped by `Retry-After`), so a dead
proxy does not add latency to every alert.

### HUD

The gateway marks every brain reply with `X-RTSAI-AI-Route`
(`hosted` | `local-fallback` | `none`) and `X-RTSAI-AI-State`. The router keeps
the latest pair; `Companion.ai_service_status()` turns it into:

- the idle line, for example `AI READY • LOCAL MODEL STANDING IN: DAILY HOSTED
  ALLOWANCE USED, RESETS 00:00 UTC` or `AI ALERTS ONLY • HOSTED AI PAUSED`
  (the state code stays `ready:<profile>`, so OpenRA's AUTO semantics are
  unchanged);
- one orange `SYSTEM // DEGRADED` feed line when the route changes (state
  `error`), and the normal idle line when hosted AI returns;
- `ai_service` in `/v1/state` and `/health`, and `hosted`, `gateway` and
  `capabilities.assistant: "hosted"` in `/v1/local-ai`.

### Voice-only pack

`packaging/ai-pack.lock.json` gains the `voice-only` profile (`"brain":
"hosted"`): Whisper base.en, Kokoro int8 and its voices, 268,539,880 bytes.
Hosted mode selects it unless a full local profile is already installed, in
which case that profile stays selected so `local-coder` can stand in. The
existing in-game install action downloads only the voice pack; the voice
readiness check prompts for it before the first push-to-talk.

### External mode fix

External installs never download the model pack, so `LocalAIManager` never
started the gateway and the companion called a dead `:4000`. The gateway now
starts for External and hosted modes without the pack, and the companion
follows the per-launch gateway port that `launch-game.ps1` assigns
(`OPENRA_AI_LOCAL_ROUTER_URL`). `serve --mode` also no longer drops the saved
endpoint and key.

### Cost guardrails

- The interactive MCP planner (Agents SDK) uses the loopback gateway for
  `hosted`, `local` and `custom`, with the companion's live route. It never
  reads `OPENAI_API_KEY`; only the explicit `openai` research provider used by
  `autoplay`/`learn` does.
- AUTO's periodic LLM/MCP planner does not run in hosted mode. Deterministic
  tactical steps and scripted mission steps still run.
- Every vision call carries at most two images within about 300 KB: the
  viewport's long edge is capped at 1,024 px and it is re-encoded as JPEG
  (quality 72 down to 34) until it fits; the small tactical overview stays PNG.
  Pillow is now a runtime dependency.
- Single-call voice orders: `codex/nl-orders` is merged (one schema-constrained
  request per ambiguous order; explicit phrasing needs no model call).

## Environment variables (RTSAI-Web, server only)

Required: `ANTHROPIC_API_KEY`, `RTSAI_AI_TOKEN_SECRET` (at least 32
characters), `RTSAI_AI_FIREBASE_SERVICE_ACCOUNT` (service-account JSON key, raw
or base64).

| Variable | Default |
|---|---|
| `RTSAI_AI_STORE` | `firestore` on Vercel, `memory` elsewhere; `memory` is refused in production |
| `RTSAI_AI_KILL_SWITCH` | off; `1` pauses every model call with 503 |
| `RTSAI_AI_ANON_DAILY_USD` | 0.25 |
| `RTSAI_AI_LINKED_DAILY_USD` | 1.00 |
| `RTSAI_AI_GLOBAL_DAILY_CAP_USD` | 10 |
| `RTSAI_AI_REQUESTS_PER_MINUTE` | 12 per install |
| `RTSAI_AI_INSTALLS_PER_IP_PER_DAY` | 5 |
| `RTSAI_AI_MAX_TOKENS` | 1024 |
| `RTSAI_AI_MAX_IMAGES` | 2 |
| `RTSAI_AI_MAX_IMAGE_BYTES` / `RTSAI_AI_MAX_TOTAL_IMAGE_BYTES` | 400,000 / 600,000 |
| `RTSAI_AI_MAX_BODY_BYTES` | 2,000,000 (ceiling 4,000,000) |
| `RTSAI_AI_UPSTREAM_TIMEOUT_MS` | 15000 |

`.env.example` lists them without values. Game side (development only):
`OPENRA_AI_HOSTED_ENDPOINT` overrides `https://rtsai.net/api/ai/v1`.

## What the owner must do before deploying

1. **Anthropic.** In the Console, create a workspace for RTS AI with a monthly
   spend limit as the hard backstop, and an API key in it. Confirm the
   workspace can use `claude-haiku-4-5`.
2. **Vercel environment (Production only).** Add `ANTHROPIC_API_KEY`,
   `RTSAI_AI_TOKEN_SECRET` (for example
   `node -e "console.log(require('crypto').randomBytes(48).toString('base64url'))"`)
   and `RTSAI_AI_FIREBASE_SERVICE_ACCOUNT`, all marked sensitive. Set
   `RTSAI_AI_ANON_DAILY_USD` and `RTSAI_AI_GLOBAL_DAILY_CAP_USD` to the
   amounts you accept. Leave the model key out of Preview, where the proxy then
   answers 503 and nothing is spent.
3. **Firestore.** In the RTS AI Firebase project, make sure a Native-mode
   `(default)` database exists, ideally in a region near the Vercel function.
   Create a service account with only **Cloud Datastore User**
   (`roles/datastore.user`), download its JSON key, and store it (base64) as
   `RTSAI_AI_FIREBASE_SERVICE_ACCOUNT`. Delete the local key file afterwards.
4. **Firestore TTL and rules.** Enable TTL on field `expireAt` for collection
   groups `aiUsage`, `aiRate`, `aiInstallIps` and `aiSpend`
   (`gcloud firestore fields ttls update expireAt --collection-group=aiUsage --enable-ttl`,
   and so on). Make sure client security rules deny the five `ai*`
   collections; the service account bypasses rules.
5. **Merge, then deploy deliberately.** Merge RTSAI-Web `rtsai/hosted-ai`
   after the variables exist; pushing `main` deploys rtsai.net. Both branches
   merge cleanly with today's `main`.
6. **Smoke test with real calls** (not done here; see below): register, ask
   one text and one vision question, and confirm `used_usd` in `/status`.
7. **Know the stop buttons.** The kill switch is an environment variable, so
   it takes effect on the next deployment. To stop spend instantly, disable
   the API key in the Anthropic Console: the proxy answers 503 and the game
   falls back.
8. **Separate decisions still open:** making hosted the installer default
   (NSIS untouched here), and the engine `launch-game.ps1` (another branch)
   treating a missing provider as hosted rather than running the 1.8 GB local
   setup, and exporting `OPENRA_AI_ROUTER_URL` for hosted mode.

## Measured costs

No `ANTHROPIC_API_KEY` or `ant` credential was available, so no real Haiku
call was made. The rehearsal ran the full chain: the companion from this
branch, the gateway in hosted mode, the proxy built with the Node preset from
the RTSAI-Web branch, and `scripts/mock-anthropic.mjs` behind the official SDK
(`ANTHROPIC_BASE_URL`). The mock estimates tokens (4 characters per text
token, width × height ÷ 750 per image); the costs below are what the proxy
charged from those estimates at Haiku 4.5 prices. The snapshot is the captured
`ra2-china-army` fixture; the viewport is a real 2902×1676 OpenRA frame.

| Call | Input / output tokens | Cost |
|---|---|---|
| Player question, text only | 812 / 39 | $0.00101 |
| Player question with 2 images (82.7 KB JPEG 1024×591 + 10.1 KB PNG overview; 3.3 MB source) | 1,986 / 39 | $0.00218 |
| Typed order, one structured call (the mock's answer did not ground, so nl-orders retried once) | 1,133 / 21 and 1,170 / 21 | $0.00126 per call |
| Agents SDK tool loop, 1 small tool, 2 model calls | 339 / 19 and 388 / 22 | $0.00093 |
| Whisper and Kokoro through the hosted gateway | — | $0 (local) |

Inferred for real use: Claude's tokenizer gives roughly 20–30% more tokens
than the mock's estimate on compact JSON, so about $0.0012 per text question
and $0.0025–0.003 per vision question. The real MCP planner sends 28 tool
schemas (11,750 characters) and 4,408 characters of instructions, about 6,000
tokens a turn; a 3–4 turn question costs roughly $0.015–0.03, less with the
prompt caching above. The default $0.25 anonymous allowance therefore covers
about 200 text questions or 100 vision questions a day; at one automatic or
player call per minute, a session costs about $0.06–0.15 an hour.

## Verification

- RTSAI-Web: `npm run lint` passes; `npm test` passes (45 tests, including 14
  hosted-AI tests against the mock and a fake Firestore REST API).
  `check:content` passes against `--product=../OpenRA-AI-wt-hosted-ai`; it now
  fails against the sibling `../OpenRA-AI` only because that `main` moved its
  catalog after this branch was cut.
- OpenRA-AI: 314 companion tests pass (17 new in `tests/test_hosted_ai.py`),
  plus 42 repository tests. The worktree's engine submodule was filled from the
  local engine checkout at the pinned commit for the asset tests.
- End to end: zero-click registration (token stored as `dpapi:`), text and
  vision answered through the proxy, local Whisper and Kokoro in hosted mode,
  allowance exhaustion falling back to the real local Qwen3-VL model and, with
  no local model, to deterministic lines, and the kill switch (no model calls,
  HUD `AI ALERTS ONLY • HOSTED AI PAUSED`).

## Known gaps

- No real Anthropic call was made; the Firestore store was tested against a
  fake of its REST API, not Google.
- `docs/natural-language-orders.md`, referenced from `docs/models.md` by the
  merged `codex/nl-orders`, exists only as an uncommitted file in that branch's
  worktree.
- macOS uses the same code; DPAPI falls back to the existing portable
  encoding there, as for External keys today.
