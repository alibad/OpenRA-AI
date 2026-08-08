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
                 <-> OpenAI API initially
                 <-> local model later

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

Routine, important, and critical notification levels are selected before the
model is called. Routine updates are text-only by default; automatic voice is
reserved for critical events. The player can change the pace and voice
threshold from OpenRA's native AI settings tab.

The model never receives raw game frames continuously. Deterministic code
decides when an event is worth interpreting.

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
imagery by default (or an optional OpenTopoMap terrain PNG) and sends that exact
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
