# Companion service

The companion service turns relevant game context and player speech into short,
interruptible responses.

It owns relevance scoring, cooldowns, deduplication, conversation state,
transcription, speech playback coordination, cancellation, and private AI-layer
routing. The default stack is fully local: `local-coder`, `local-whisper`, and
`local-kokoro` are selected through the BeTenshi router.

The companion can propose a bounded set of game orders, but every proposal
requires a separate player confirmation. The OpenRA engine validates the
confirmed request again on the game thread and returns a structured receipt.
Actions are single-player only and never use the RL bridge's pause or
fast-forward behavior.

The in-game `AUTO` toggle is a separate, explicit authority mode. While it is
on, the local human slot is delegated to OpenRA's complete native `ModularBot`
stack. Native economy, production, placement, harvesting, expansion, repair,
support-power, squad, defense, retreat, and attack modules keep running at game
speed. The slower LLM stays above that loop: it selects and explains a durable
strategy only at major events and never tries to duplicate per-unit micro.
Turning AUTO off immediately deactivates the native bot and returns to manual
`ACCEPT` / `CANCEL` proposals.

The strategy contract is controlled by voice or the local AI console. Examples
include `What strategy are we using?`, `Play aggressive strategy`, `Switch to
defensive strategy`, `Use naval strategy`, and `Use adaptive strategy`. Exact
strategy questions and commands are deterministic and require no model call.
Adaptive mode starts with OpenRA's general-purpose normal profile and may move
between normal, rush, turtle, naval, and medium profiles when strategic evidence
changes. Explicit player choices persist and override adaptive selection.

Automatic observations share a global pacing budget: at most one per minute in
calm or guarded play, every ten seconds at high threat, and every four seconds
at critical threat. Threat escalation can interrupt the calmer budget. A
deterministic, fog-respecting threat score is continuously published to the HUD.
Selected alerts can include contextual power, harvester, repair, or defensive
movement proposals; they never execute without a separate confirmation.
The in-game AI strip opens a scrollable tactical feed that preserves 80 signals
and visually distinguishes player transcripts, advice, alerts, pending orders,
executed orders, and rejected or cancelled orders.
Persistent economy, power, production, and damage conditions use local
deterministic wording and emit only on state transitions. They do not call any
model, regardless of how long the condition remains active.

Full game vision combines an on-demand PNG of OpenRA's already fogged rendered
viewport with a deterministic whole-map tactical overview derived from the
nine-channel spatial observation. Questions and action interpretation use both
when available; high/critical automatic alerts can also use them. Headless or
unavailable renderers fall back to the tactical overview and structured state.

## Run it

The OpenRA fork publishes a read-only, fog-respecting snapshot on port 9998
when launched with `OPENRA_AI_COMPANION=1`. It does not pause the match or
advance the match. Confirmed companion actions use a separate unary RPC and are
queued as normal synchronized local-player orders.

```powershell
python -m pip install -e "services/companion[voice]"
$env:OPENRA_AI_COMPANION="1"
openra-ai-companion watch --speak --voice-hotkeys
```

On Windows, hold `Ctrl+Space` for push-to-talk, press `Ctrl+Enter` to accept a
proposal, `Ctrl+Backspace` to reject it, `Ctrl+Shift+M` to mute, and
`Ctrl+Shift+A` to toggle AUTO delegation. All five bindings are remappable in
OpenRA under **Settings > Hotkeys > AI Assistant**. The launcher supplies the OpenRA process ID so
the watcher shuts down with the game. Speech recognition uses the app's
two-letter UI language (`OPENRA_AI_APP_LANGUAGE`) and falls back to English;
`OPENRA_AI_TRANSCRIBE_LANGUAGE` can explicitly override it.

For local application integration, run `openra-ai-companion serve`. Its small
HTTP API supports snapshot observation, player questions, transcription,
speech, mute/disable controls, notification priority, session cost estimates,
immediate interruption, and proposal/confirmation endpoints under
`/v1/actions`. OpenRA's native AI settings tab uses `/v1/state`,
`/v1/usage`, and the diagnostic routes; users do not need the HTTP console. All model traffic
uses the named AI-layer routes in the project `.env`; provider keys stay in
the router and are never copied into this repository.

## Autonomous MCP commander

`openra-ai-companion autoplay` starts a disposable headless match, connects one
router-backed Agents SDK commander to the local `openra-game` MCP server, and records
every command, advance, interrupt, and engine outcome as JSON evidence. It
defaults to the routed `local-coder` model. Local mode disables SDK tracing and
does not read, print, or forward `OPENAI_API_KEY`.

The MCP surface contains observation/status/advance plus 19 safe local gameplay
actions: move, attack-move, visible-target attack, stop, harvest, build, train,
deploy, sell, repair, place/cancel production, rally, guard, stance, transport
load/unload, power-down, and primary-production selection. Python validates the
latest observed state before dispatch, and the engine validates again. There is
no surrender, session-destruction, arbitrary RPC, filesystem, shell, or
external-app tool.

```powershell
openra-ai-companion autoplay --provider local --model local-coder --opponent beginner --evidence-dir .artifacts/autoplay/manual
python services/companion/evals/grade_victory.py .artifacts/autoplay/manual
openra-ai-companion learn --provider local --model local-coder --opponent beginner --attempts 3 --evidence-root .artifacts/autoplay/learning-runs
```

`learn` is the feedback-loop runner. It stops on the first engine-verified win,
persists a match review and decision timeline in `.artifacts/autoplay/learning`,
and supplies the relevant lessons to the next attempt. The web admin exposes
the aggregate at `/v1/learning`, the latest full review at
`/v1/learning/latest`, and individual matches at
`/v1/learning/matches/{attempt_id}`. The same information appears in the
**Autonomous Learning** panel.

This autonomous path is intentionally separate from the interactive companion:
starting it grants action authority only for its disposable local match. Live
player matches continue to require proposal confirmation.
