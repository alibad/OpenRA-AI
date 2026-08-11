# OpenRA AI strategy and spatial doctrine

This document defines the behavior used by the companion and autonomous commander. It is grounded in the Red Alert rules shipped with this OpenRA checkout and the engine's fog-respecting observation data. The AI may use explored terrain and resources, owned actors, and visible or remembered enemy structures. It must not use hidden enemy state.

## Opening

The default opening is:

1. Deploy the Construction Yard.
2. Build power.
3. Build a Barracks/Tent.
4. Train 2-4 Rifle Infantry according to map size and attack-move them toward separate reachable hidden regions.
5. Build a Refinery at the best legal ore-facing site.
6. Build a War Factory with a clear vehicle lane.
7. Set production rally points in open staging space beyond the production doors.

Scouts are intentionally cheap Rifle Infantry. They reveal approaches without risking the early harvester or delaying the armored core. Scout targets are selected from cells reachable on observed passable terrain, prefer fogged cells, and maximize angular and physical separation.

## Map-size policy

Map size is classified by playable cell count so rectangular maps behave sensibly.

| Scale | Cells | Opening scouts | Economy target | Base and tempo doctrine |
| --- | ---: | ---: | ---: | --- |
| Small | up to 4,096 | 2 | 2 harvesters | Compact base, one clean production avenue, expect early contact. |
| Medium | 4,097-9,216 | 3 | 3 harvesters | Ore-facing economy, two production lanes, reveal three approaches. |
| Large | 9,217-16,384 | 4 | 4 harvesters | Distributed layout, room for expansion, mobility and forward staging. |
| Huge | above 16,384 | 4 | 5 harvesters | Multiple clusters connected by open routes, mobile reserve, repeated scouting. |

These are strategic targets, not unconditional queues. Power, current cash flow, production availability, threats, and build-queue occupancy still gate actual orders.

## Structure placement

Normal AI placement omits coordinates. The engine evaluates every legal site within construction range and minimizes a weighted spatial cost:

- refinery dock distance to the nearest explored ore or gem cell;
- density of explored resources within a 12-cell radius;
- three-cell-wide, six-cell-long clear lanes beyond every production exit;
- open service space around the footprint;
- separation from existing structures and decorative bib congestion;
- passability for all relevant land locomotors;
- door alignment away from the Construction Yard and toward open ground.

The refinery calculation uses its bottom-center dock rather than the top-left footprint coordinate. Resource cells behind fog are excluded. Barracks and War Factory rally points are separately selected on explored, passable, low-density ground, away from structures and resource fields.

The Red Alert rules define the War Factory as a 3x3 structure with its vehicle exit on the bottom edge, Barracks/Tent exits on the bottom edge, and the Refinery as a 3x4 structure with a bottom-facing dock. The optimizer reads the actual `BuildingInfo` and `ExitInfo` traits, so it remains rule-driven instead of relying only on those dimensions.

## Faction doctrine

The commander receives the actual player and known enemy faction from the game bridge.

| Faction | Identity in shipped rules | Behavior bias |
| --- | --- | --- |
| England | Counterintelligence; British Spy and Mobile Gap Generator | Early vision, mobile combined arms, open staging lane for the gap generator behind the main force. |
| France | Deception; fake structures and Phase Transport | Map control and naval access where relevant; fake structures only after the real economy is secure. |
| Germany | Advanced Chronoshift and Chrono Tank | Spacious vehicle staging, mobility, and attacks that exploit newly revealed weak points. |
| Russia | Tesla Tank and Shock Trooper | Extra power headroom, armored pressure, and separate infantry/vehicle staging from harvester traffic. |
| Ukraine | Parabombs and Demolition Truck | Airfield timing and especially wide, direct vehicle routes that keep demolition units out of the base interior. |

Faction doctrine is a production and positioning bias, never permission to build an unavailable item. The commander always uses exact IDs reported by `available_production` and counters the enemy composition it can actually see.

## Native OpenRA real-time controller

With `AUTO: ON`, the assistant delegates the local human slot to the complete
OpenRA `ModularBot` stack. The slot remains a human slot, so AUTO can be released
without ending the match. Native modules own resource mapping, harvesting,
power, production, structure placement, repair, support powers, MCV expansion,
unit composition, squad formation, attack response, defense, retreat, and
assault timing. They run with the game tick and do not wait for a model.

The voice/LLM layer owns durable intent rather than individual clicks:

| Assistant strategy | Native profile | Intent |
| --- | --- | --- |
| Adaptive | normal initially | Balanced default; change profile only when strategic evidence invalidates it. |
| Balanced | normal | Economy, combined arms, counters, expansion, and concentrated attacks. |
| Aggressive | rush | Minimum viable economy followed by early and continuous pressure. |
| Fortified | turtle | Strong economy, static defense, reserve forces, and favorable counterattacks. |
| Naval | naval | Secure water access, naval production, scouting, and shore pressure. |
| Measured | medium | Lower-complexity pressure with a moderate economy and attack threshold. |

Voice commands such as `Play aggressive strategy`, `Switch to defensive
strategy`, and `Use adaptive strategy` change this contract immediately.
Questions such as `What strategy are we using?` return the intent, major event
sequence, and switching conditions without calling a model. In adaptive mode,
the local routed model may reconsider the profile only after a major event such
as enemy discovery, sustained pressure, a failed assault, or decisive economic
change. It never duplicates native unit micro.

## Advisory and confirmed-action controller

When AUTO is off, suggested and player-requested actions still use the bounded
proposal/confirmation path. Its production guidance reuses the strongest parts
of OpenRA's shipped `UnitBuilderBotModule` instead of selecting the first
available unit. It starts from the medium/normal Red Alert `UnitsToBuild`
shares, chooses the most under-represented available type, respects specialist
`UnitLimits`, requires a rearm building for every aircraft, and rotates free
infantry, vehicle, aircraft, and naval queues. A single overflow batch prefers
distinct infantry types, so storage pressure cannot create a Grenadier or Rifle
Infantry monoculture.

Visible contacts adjust those base weights without reading through fog: anti-infantry gains weight against infantry, rockets and durable armor against vehicles, anti-air against aircraft, and protected siege against structures. When contact disappears, production returns to the base OpenRA mix instead of preserving a stale counter indefinitely.

The squad layer mirrors `SquadManagerBotModule`: new combat units gather at the base, a map-scaled mixed-role threshold gates attacks, and a separate defense reserve remains near harvesters and production. Local tactical intelligence improves on the generic squad behavior by keeping siege behind armor, retreating badly damaged units, respecting weapon-range edges, and using powered defenses as fallback cover.

## Tactical cycle

Each decision cycle follows this order:

1. Handle immediate survival: visible threats, power failure, missing harvesters, and critical repairs.
2. Place completed structures; placement-ready buildings must not block their queue.
3. Maintain production exits and rally points.
4. Complete the map-scaled scout fan-out.
5. Reach the map-scaled economy target without starving power or combat production.
6. Build a faction-appropriate mixed force, concentrate it, and attack visible priority production and economy targets.
7. Advance time, re-observe, and revise from fog-respecting evidence.

Silo count is capped at the map-scaled harvester target. Above 80% storage, the AI builds one silo only below that cap; at the cap it spends reserves on combat production and map control.

## Sources

- [OpenRA source repository](https://github.com/OpenRA/OpenRA), including the shipped Red Alert actor, faction, exit, refinery, and AI rules mirrored under `engine/openra/mods/ra`.
- [OpenRA release 20250330](https://www.openra.net/news/release-20250330/) documents harvester behavior that keeps harvesters closer to refineries and rally-point fixes.
- [OpenRA release 20120504](https://www.openra.net/news/release-20120504/) documents attack-move behavior for rally points.
- [OpenRA release 20150424](https://www.openra.net/news/release-20150424/) documents the playable Red Alert factions.

Implementation lives in
`services/companion/src/openra_ai_companion/strategy_contracts.py`,
`services/companion/src/openra_ai_companion/strategy_director.py`,
`services/companion/src/openra_ai_companion/core.py`, and
`engine/openra/OpenRA.Mods.Common/Traits/Player/CompanionBridge.cs`.
