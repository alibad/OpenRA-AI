# Architecture

## Product surfaces

OpenRA AI has two user-facing applications:

1. The Windows alpha launcher verifies required game content, installs generated
   maps, starts the local companion and Earth Mission Studio, and launches
   OpenRA. Main-menu entry points open the local AI configuration/diagnostics
   console, the Earth map picker, and OpenRA's native map editor.
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

Web map picker
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

The model never receives raw game frames continuously. Deterministic code
decides when an event is worth interpreting.

### World generation

World generation is asynchronous and reproducible. Every output records:

- geographic bounds and projection;
- data sources and attribution;
- generator and rules versions;
- random seed;
- story sources and generation settings;
- validation results.

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
