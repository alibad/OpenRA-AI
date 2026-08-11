# Red Sea 2026 vertical slice

The polished vertical slice adds **Saudi Arabia** and **Yemen** to Red Alert and
ships two authored campaign missions over deterministic Red Sea terrain. It proves
country-gated units, original directional sprites, native bot production,
bilingual radio, a playable construction/harvesting economy, scripted
objectives, source-dated Earth content, and a reproducible audiovisual pipeline.

## Play it

After running `scripts/setup.ps1`, double-click:

```text
Play-Red-Sea-2026.cmd
```

Double-clicking launches `Jizan Corridor` with **Saudi Arabia** as the player.
Both packages are rebuilt, validated, and installed. Launch the playable Yemen
mission directly with:

```powershell
.\scripts\play-red-sea-2026.ps1 -Mission hodeidah-lifeline-2026
```

Pass `-Regenerate` to rebuild the Earth terrain before repackaging the mission.

## Live roster

Saudi Arabia:

- M1A2S: durable, expensive medium-tech main battle tank;
- Mobile Air Defense System: radar-guided long-range anti-air platform.

Yemen:

- Armed Technical: inexpensive high-speed raider;
- Mobile Missile Launcher: fragile, mobile long-range strike system;
- Samad Drone: low-altitude one-way loitering munition with a close-range dive,
  dedicated impact animation, blast, camera shake, and layered strike audio.

All five actors use original SHP art rendered from fixed-camera 3D geometry,
never a single bitmap rotated in 2D. Every ground vehicle has 32 native Red
Alert classic facings; the M1A2S, air-defense vehicle, and technical have
independently rotating turrets; the missile launcher has visibly different
loaded and empty states; and the drone has 16 authored airframe views
interpolated to 64 in-game facings. Front/rear details, wheel or track depth,
launcher geometry, and cannon foreshortening therefore remain coherent through
a complete turn. All four ground vehicles also leave matching 32-facing
scorched wrecks instead of disappearing or reverting to a stock tank husk.

Every custom unit also has a separate opaque 64x48 illustrated production
cameo and one-frame icon SHP, matching the native Red Alert split between world
animation packages and sidebar icon packages. No production item reuses a tiny
battlefield frame as its menu artwork.

Vehicle canvases and silhouettes are calibrated against the native actors they
inherit: 2TNK, FTRK, JEEP, V2RL, and YAK. The mission filters legacy combat
vehicles, Spy, and Tanya from Saudi production while retaining harvesters and
MCVs for a complete economy loop.

## Complete faction foundations

Saudi Arabia inherits the complete Allied construction, infantry, vehicle,
air, and naval prerequisite chains; Yemen inherits the complete Soviet chains.
Both can therefore construct the normal economy and progression buildings,
including service/repair facilities, radar, advanced power, Tech Center,
airfield or helipad, defenses, naval production, MCVs, and harvesters. Their
custom rosters are additive country identity, not truncated replacements.

Every stock bot personality has reachable production weights and unit limits
for the custom ground roster. Medium and higher bots also build the required air
production and classify Samad drones as air squad units.

## Jizan Corridor

The forward base starts with a construction yard, refinery, power, barracks,
and repair facility. Players can immediately place a war factory, expand the
base, harvest nearby ore, and replace combat losses.

`Jizan Corridor` contains four linked objectives:

1. capture Radar Node Seven with the engineer;
2. use the restored network to locate and destroy two mobile launchers;
3. escort at least two of three relief trucks into the port on easy/normal, or
   all three on hard;
4. optionally preserve Port Control and the desalination plant.

Drone pressure, technical/infantry ambushes, reinforcement timing, and convoy
tolerance scale with difficulty. Mission radio alternates between English and
Arabic with bilingual subtitles.

## Hodeidah Lifeline

The second mission reverses the playable side. Yemen begins with a complete
base, two missile launchers, two technicals, and two Samad drones. Four linked
objectives require the player to protect civilian infrastructure, escort relief
supplies inland, disperse mobile assets before a surveillance sweep, and cover
the evacuation convoy on its return. Saudi combined-arms waves, the sweep
deadline, exposure tolerance, and required convoy survivors scale by difficulty.

## Scenario boundary

Each scenario stores a factual cutoff, sources, country profiles, authored
objectives, and an editorial boundary. The background is source-dated; force
composition, routes, timing, positions, and outcomes are gameplay abstractions.

The two playable contracts are:

- `jizan-corridor-2026`;
- `hodeidah-lifeline-2026`.

The mission packages are reproducible via `scripts/build-red-sea-mission.py` and
are listed under **Red Sea 2026** in the mission browser. Remaining release
gates are hands-on balance/mix playtests and eventual separation into a
standalone `redsea` mod shell.

Rebuild every deterministic asset and validate it with
`scripts/build-red-sea-assets.ps1`. Pass `-RegenerateVoices` only when the
network-backed disclosed synthetic voice sources should be regenerated.

## Validation

- OpenRA map YAML and missing-sprite checks for both installed packages;
- a full real-engine headless Hodeidah run to victory with all four objectives
  completed, plus a Jizan game/world load with zero Lua or engine errors;
- 186 automated companion, AI, world-generation, SHP frame-count, bilingual
  provenance, WAV layout/headroom, scripted-reference, and deterministic-package
  checks;
- rendered live-app inspection of the populated production tree, Arabic
  subtitles, convoy script, and custom vehicles changing facings while moving;
- the playtest matrix in `docs/red-sea-2026-playtest.md` for the final human
  feel and mix pass.
