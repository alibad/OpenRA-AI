# Earth mission generation

## Goal

Choose a location on Earth and receive a playable, stylized OpenRA map with
terrain, resources, spawn points, objectives, briefing, and optional scripted
events inspired by that place.

The system preserves recognizable terrain, water, arterial roads, urban form,
and biome as closely as OpenRA's discrete tiles allow. Playability repairs are
recorded separately from geographic evidence.

## Generation pipeline

### 1. Select

The player chooses:

- a point or rectangular area;
- physical scale and map size;
- mission, skirmish, or cooperative scenario;
- desired match length and player count;
- an optional theme or story prompt.

### 2. Acquire

Adapters retrieve appropriately licensed data such as:

- roads, waterways, coastlines, land use, and vegetation from OpenStreetMap;
- a radius-matched OpenTopoMap terrain view with relief and settlement context;
- elevation and slope;
- land cover and biome;
- place names and public geographic context;
- optional historical or current-event sources.

Every source retains its license and attribution. The selected terrain view is
cached locally, passed through the configured AI layer, and stored in the map
package so a creator can compare source evidence with the OpenRA translation.

### 3. Translate

The terrain compiler:

- projects geographic data onto the OpenRA cell grid;
- classifies water, passable land, cliffs, roads, bridges, and obstacles;
- simplifies noisy geometry;
- exaggerates strategically meaningful features;
- assigns a compatible OpenRA tileset;
- creates candidate resource and spawn regions.

### 4. Design

The scenario designer creates:

- balanced or intentionally asymmetric starting positions;
- resources, neutral structures, and tactical landmarks;
- objectives and failure conditions;
- factions and unit restrictions;
- a briefing and optional Lua mission script.

Real places can inspire the setting without representing real people or
ongoing violence as factual simulation. News-aware scenarios must show their
sources, generation date, fictionalization, and user-selected framing.

### 5. Validate

Before a map reaches the player, automated local checks test:

- connectivity and pathfinding;
- valid spawn and construction space;
- resource access and travel-time balance;
- reachable objectives;
- Lua loading and deterministic startup;
- missing assets and rules;
- performance budgets.

Unplayable generations are repaired or rejected, never silently shipped.

### 6. Package

The output is a normal versioned OpenRA map package containing terrain,
metadata, rules, Lua scripts, preview imagery, attribution, and a generation
manifest. It can be opened in OpenRA's in-game map editor for human editing.

## Implemented reality-grounded slice

The native editor now supports:

1. searching or clicking any place in a radius-matched terrain view;
2. choosing Reality First, Balanced, or Creative Remix generation;
3. routing that exact terrain PNG through the local AI layer's multimodal route;
4. reconciling the vision result with OSM water, seasonal waterways, arterial
   and local roads, rail, land use, vegetation, sand, and rock geometry;
5. compiling real road cells, biome-appropriate Red Alert tilesets, urban
   scenery, resources, and two playable starts;
6. repairing and validating connectivity, spawns, binary layout, and resource
   fairness before the map is installed;
7. storing the terrain source, model analysis, confidence, feature counts,
   attribution, preview, and validation report inside the `.oramap`.

When geographic or vision services are unavailable, the manifest explicitly
labels the degraded path and uses conservative geometry/climate fallback. It
never invents water. Elevation-derived cliffs, detailed building footprints,
Lua objectives, and source-backed narrative context remain later stages.
