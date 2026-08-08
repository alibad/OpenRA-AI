# Earth mission generation

## Goal

Choose a location on Earth and receive a playable, stylized OpenRA map with
terrain, resources, spawn points, objectives, briefing, and optional scripted
events inspired by that place.

The system reads recognizable terrain, water, roads, urban form, and biome as
geographic evidence, then maps that evidence onto one of OpenRA's supported
native generator profiles. It does not claim that every street or coastline is
reproduced cell-for-cell. The source view and every translation choice remain
available for comparison.

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
- radius-matched Sentinel-2 Cloudless satellite imagery by default, with an
  OpenTopoMap terrain layer available when explicit relief is more useful;
- elevation and slope;
- land cover and biome;
- place names and public geographic context;
- optional historical or current-event sources.

Every source retains its license and attribution. The selected terrain view is
cached locally, passed through the configured AI layer, and stored in the map
package so a creator can compare source evidence with the OpenRA translation.

### 3. Translate

The terrain translator:

- classifies biome, relief, water, vegetation, and urban intensity;
- selects a compatible OpenRA tileset and native terrain profile;
- chooses symmetry, civilian density, resources, and map scale;
- passes those constraints to OpenRA's `ClassicMapGenerator`;
- lets OpenRA's Terraformer build legal transitions, passages, roads, spawn
  regions, resources, and neutral structures.

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

- connectivity using the selected mod's real tracked-unit locomotor rules;
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

1. searching or clicking any place in a radius-matched satellite or terrain view;
2. choosing Earth + Balance (the default), Reality First, or Creative Remix generation;
3. routing that exact displayed PNG through the local AI layer's multimodal route;
4. reconciling the vision result with OSM water, seasonal waterways, roads,
   rail, land use, vegetation, sand, and rock evidence;
5. converting that evidence into native ClassicMapGenerator settings and
   allowing OpenRA's Terraformer to construct the battlefield;
6. rejecting any result where OpenRA's tracked locomotor cannot reach both
   spawns or where a spawn lacks a usable base zone;
7. storing the terrain source, model analysis, confidence, feature counts,
   attribution, preview, and validation report inside the `.oramap`.

When geographic or vision services are unavailable, the manifest explicitly
labels the degraded path and uses conservative climate/profile fallback.
Detailed building footprints, exact street tracing, Lua objectives, and
source-backed narrative context remain later stages.
