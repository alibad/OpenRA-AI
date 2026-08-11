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
twelve-channel spatial observation. Questions and action interpretation use both
when available; high/critical automatic alerts can also use them. Headless or
unavailable renderers fall back to the tactical overview and structured state.

## Brain architecture

Action authority is explicit. A brain arbiter leases actor, production, economy,
mission, and support-power scopes to the player, the safety controller, the
scripted-mission controller, OpenRA's native bot, or the slower strategy model.
Higher-priority safety and player work preempts lower-priority work; two brains
cannot silently issue conflicting orders in the same scope.

Every dispatched proposal becomes a durable goal in
`.artifacts/runtime/brain-blackboard.jsonl`. A later, snapshot-bound observation
must prove the requested effect on the specified actor, target, queue, building,
or support power. Unproved automatic goals retry with a bounded attempt count;
manual goals fail visibly, and in-flight orders are never blindly replayed after
a process restart. The in-game/web **Brain Blackboard** exposes the current owner,
leases, strategy program, next fast-controller decision, active goals, and their
verification evidence.

The control stack is intentionally layered:

1. the deterministic safety controller handles dog avoidance, damaged-armor
   retreat, siege spacing, anti-air response, range kiting, defensive lures, and
   tank regrouping at observation speed;
2. scripted missions compile localized live objectives and briefing directives
   into reusable capture, infiltrate, extract, escort, defend, destroy, explore,
   and scripted-trigger goal nodes;
3. OpenRA's native ModularBot owns real-time skirmish economy, production,
   placement, repair, squads, defense, and combat under a bounded
   `StrategyProgram` selected by the player or strategy model;
4. the routed model answers questions, explains state, and selects durable
   strategy. It does not compete with the real-time layers for unit micro.

Combat telemetry includes armor/target classes, unit value, weapon and burst,
minimum/maximum range, reload state, current targets, move targets, air/ground
targeting, last-seen ticks, support-power readiness, friendly/enemy threat
coverage, and movement cost. Destructive support powers require a ready native
power, a visible enemy concentration, and a friendly-fire-clear target; the
engine revalidates the order on the synchronized game thread.

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

The MCP surface contains observation/status/advance plus the complete safe local
gameplay action set: move, attack-move, visible-target attack, stop, harvest,
build, train, deploy, sell, repair, place/cancel production, rally, guard,
stance, transport load/unload, disguise, infiltration, capture, demolition,
power-down, primary-production selection, and support-power targeting. Python validates the
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

Candidate policies are not promoted from prose or one lucky match. Promotion
requires at least three evaluated games, a two-thirds win rate, at least a
five-point improvement over the declared baseline, and zero recorded safety
violations. Policy state and the evidence behind promotion remain visible to the
admin.

This autonomous path is intentionally separate from the interactive companion:
starting it grants action authority only for its disposable local match. Live
player matches continue to require proposal confirmation.

## Campaign mission evaluation

`mission-eval` inventories every mission declared by the Red Alert mod, detects
the required human slot from each map package, runs the same deterministic
mission brain used by AUTO mode, and preserves a result, objective state,
decision/command timeline, and fog-respecting tactical frame every five game
seconds. One broken or unsupported mission is recorded without aborting the
rest of the corpus.

```powershell
openra-ai-companion mission-eval --evidence-root artifacts/mission-eval
openra-ai-companion mission-eval --campaign "Allied Campaign" --max-ticks 30000
openra-ai-companion mission-eval --mission allies-01 --mission exodus
```

The evidence root contains `summary.json`, a readable `report.md`, engine logs,
and one numbered directory per mission. Each mission directory includes rendered
tactical frames, a command/decision timeline, and fog-respecting actor-level
`observations.jsonl` for diagnosis and replay. `unsupported` means the planner could
not translate the live objective into an executable order; `engine_timeout`
means the map loaded but the headless engine stopped completing simulation
ticks, so no planner verdict is inferred.

Run the repeatable architecture gates with:

```powershell
./scripts/run-ai-quality-gates.ps1
./scripts/run-ai-quality-gates.ps1 -FullMissions -MissionMaxTicks 30000
```
