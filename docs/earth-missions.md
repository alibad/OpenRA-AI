# Earth mission generation

## Goal

Choose a location on Earth and receive a playable, stylized OpenRA map with
terrain, resources, spawn points, objectives, briefing, and optional scripted
events inspired by that place.

The system does not attempt to reproduce a location building-for-building.
It translates recognizable geographic structure into readable RTS terrain.

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

- roads, waterways, coastlines, land use, and buildings;
- elevation and slope;
- land cover and biome;
- place names and public geographic context;
- optional historical or current-event sources.

Every source must retain its license and attribution. Source imagery is never
assumed to be redistributable.

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

## Implemented first slice

The first generator is deliberately narrow:

1. choose any coordinate or click the web map;
2. import nearby water and major roads from OpenStreetMap;
3. generate a two-player Red Alert skirmish with a deterministic seed;
4. repair and validate connectivity, spawns, binary layout, and resource fairness;
5. emit a normal `.oramap`, preview, briefing, and attribution manifest.

When the geographic endpoint is unavailable, the generator labels and uses a
deterministic terrain fallback. Elevation, buildings, Lua objectives, and
source-backed narrative context remain later stages; current-event stories are
not presented as factual simulations.
