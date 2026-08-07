# Architecture

## Product surfaces

OpenRA AI has two user-facing applications:

1. The installed launcher downloads and updates the game, manages local
   services, registers the `openra-ai://` protocol, installs generated maps,
   and launches OpenRA on Windows and macOS.
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
            <-> BeTenshi AI router
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
- model-provider routing through BeTenshi;
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

Local scripts will build:

- a signed Windows installer;
- a signed, notarized macOS application;
- versioned game and mission packages;
- checksums and a release manifest consumed by the web application.

Release uploads remain an explicit local operation. No hosted workflows are
required.
