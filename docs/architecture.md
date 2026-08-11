# Architecture

## Product surfaces

OpenRA AI has two user-facing applications:

1. The Windows alpha launcher verifies required game content, installs generated
   maps, starts the local companion and Earth Mission Studio, and launches
   OpenRA. Main-menu entry points open native OpenRA dialogs for AI
   configuration/diagnostics, Earth mission generation, and map editing. The
   loopback services remain invisible implementation details.
2. The web application lets a player choose a place, create or discover a
   mission, download the launcher, and send a generated mission to an installed
   launcher through a deep link.

A browser cannot reliably install or launch an arbitrary native game by
itself. The launcher is therefore the trusted bridge between the web
experience and the local game.

## Runtime

```text
OpenRA engine
  <-> OpenRA adapter
       <-> companion service
            <-> private AI layer
                 <-> local models by default
                 <-> hosted OpenAI-compatible routes by explicit opt-in

Native Earth Mission Studio (plus the optional marketing web picker)
  <-> world-generation service
       <-> geographic data adapters
       <-> terrain compiler
       <-> mission compiler
       <-> playability validator
       -> signed mission package
       -> launcher
       -> OpenRA
```

## Boundaries

### OpenRA engine

The engine stays in a pinned submodule. Engine-level C# changes are published
to the dedicated `alibad/OpenRA` fork.

### OpenRA adapter

The adapter turns engine state into versioned observations and events. It also
installs and validates generated map packages. Useful OpenRA-RL concepts are
extracted here without making its Python environment the product shell.

### Companion

The companion owns:

- deterministic event detection and relevance scoring;
- compact, fog-respecting game snapshots;
- player questions and short responses;
- interruption, cancellation, cooldowns, and speech queues;
- model-provider routing through the private AI layer;
- transcripts, latency measurements, and cost measurements.

AUTO authority is implemented as a two-speed assistant. OpenRA's native
`ModularBot` owns the real-time loop and executes its complete condition-gated
module stack for the local human slot without changing that slot into a bot.
The companion owns a persistent strategy contract and can activate the normal,
rush, turtle, naval, or medium native profile. Exact voice strategy commands
switch profiles immediately; adaptive selection is event-driven and rate
limited. Disabling AUTO deactivates the native brain and preserves ordinary
manual control.

The language model is deliberately outside the tick loop. It receives compact,
fog-respecting strategic events, chooses only a durable native profile, and
explains the resulting notable sequence. Routine building placement, harvesters,
production, repairs, support powers, squad formation, combat responses, and
micro remain native deterministic algorithms. This makes gameplay latency and
cost independent from the model response interval.

For action requests, the model produces a typed proposal rather than a game
order. Python validates it against the latest fog-respecting snapshot and keeps
it pending until the player separately confirms or cancels it. Confirmation
submits a stable request id and fresh snapshot tick to the engine. The engine
then repeats all security-relevant validation on the game thread and returns a
structured receipt. The initial action surface is single-player only,
allowlisted, capped at twelve orders, and excludes surrender, hidden state,
support powers, and match-lifecycle commands.

Routine, important, and critical notification levels are selected before the
model is called. Routine updates are text-only by default; automatic voice is
reserved for critical events. The player can change the pace and voice
threshold from OpenRA's native AI settings tab.

The deterministic threat detector scores only the fog-respecting snapshot and
publishes `calm`, `guarded`, `high`, or `critical` plus a 0–100 value to the
native HUD. Calm and guarded notifications share a 1,500-tick global budget;
high and critical play shorten this to 250 and 100 ticks, and upward escalation
can speak immediately. The detector can attach an allowlisted contextual action
proposal, but it uses the same confirmation and engine-validation boundary as a
player-requested action.

For explicit questions and action requests, the vision route receives two
bounded, fog-respecting images: OpenRA's rendered player viewport and a
deterministic whole-map tactical overview built from the spatial tensor. Heated
automatic alerts may use the same pair. Frames are captured on demand rather
than streamed continuously; calm event selection stays deterministic. Hidden
cells render black, hidden actors are absent, and unexplored resource density is
removed at serialization. Typed actor ids and coordinates remain the only
authority for executable proposals.

### Autonomous game agent

The headless evaluation path uses one OpenAI Agents SDK commander and one local
stdio MCP server bound to an exact multi-session OpenRA match. The server
publishes fog-respecting battlefield/status reads, interruptible simulation
advance, and the complete safe gameplay action allowlist. It has no external
application connectors, arbitrary RPC, shell/filesystem access, surrender, or
session-destruction tool.

The MCP runtime validates ownership, visibility, capabilities, map bounds, and
observed production IDs before sending commands. OpenRA repeats the authoritative
checks on the game thread. Fast advance is confined to the headless test bridge;
it is not available to the live interactive companion. Every tool call and the
final engine outcome are persisted as machine-gradable evidence.

The controller reads `OPENAI_API_KEY` from its process environment or nearest
project `.env` and supplies it only to the Agents SDK process. Neither OpenRA nor
the MCP gameplay server receives the credential.

### World generation

World generation runs off the game tick and is reproducible for the same
inputs. Every output records:

- geographic bounds and projection;
- data sources and attribution;
- generator and rules versions;
- random seed;
- story sources and generation settings;
- validation results.

The current native flow captures radius-matched Sentinel-2 Cloudless satellite
imagery at regional scale and OpenTopoMap street/building detail at tactical
scale (with explicit satellite, map, and hybrid overrides) and sends that exact
displayed image as a multimodal request through the same provider-neutral AI
layer as the companion. The model returns constrained biome/relief/density guidance;
deterministic code combines that guidance with OSM evidence to select OpenRA
`ClassicMapGenerator` options. OpenRA's Terraformer then owns legal tile
transitions, passages, roads, spawns, resources, and scenery. The exact terrain
PNG, analysis, native options, and tracked-locomotor validation are embedded in
the `.oramap` for human comparison in the editor.

### Contracts

Contracts are provider-neutral and versioned. Initial concepts include:

- `GameSnapshot`
- `GameEvent`
- `InsightCandidate`
- `CompanionRequest`
- `CompanionResponse`
- `GeoSelection`
- `TerrainPlan`
- `MissionPlan`
- `MissionPackage`
- `ValidationReport`

## Distribution

Local scripts currently build:

- a self-contained Windows x64 ZIP with the engine, companion, launcher, and a
  sample mission;
- a SHA-256 checksum and release manifest;
- normal `.oramap` mission packages generated in Python or directly in the
  browser.

Code signing, a native installer, protocol deep links, automatic updates, and a
notarized macOS application are later distribution stages. The public site must
label them as unavailable until their artifacts exist.

Release uploads remain an explicit local operation. No hosted workflows are
required.
