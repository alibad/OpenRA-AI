# OpenRA community-mod reuse portfolio

This is the curated layer above the generated catalog. The catalog answers “what exists”; this review answers “what creates product value for OpenRA AI, what can be reused safely, and in what order.”

## Portfolio result

Nine pinned projects were inspected as source trees. Together they expose more than 20,000 declared actor blocks, 7,000 weapons, 320 selectable or internal faction definitions, 150 mission-script folders, and hundreds of engine traits not present in the current target. Those counts are search space, not a promise to merge everything.

The portfolio has four reuse classes:

1. **Direct code adaptation** — small GPL-compatible traits that fit the current engine and need no upstream art.
2. **Native enhancement** — upstream behavior folded into an existing OpenRA component so there is one maintained API.
3. **Pattern extraction** — reuse the architecture, roles, balance relationships, and mission beats while writing original data and content.
4. **Quarantined content** — sprites, audio, music, movies, names, and story text stay out until their exact provenance permits redistribution.

The machine-readable decisions and dependencies are in [`roadmap.json`](roadmap.json). Exact actors, weapons, traits, files, factions, assets, Lua calls, and story-pattern tags are in [`generated/catalog.json`](generated/catalog.json).

## Integrated foundation slice

Four opt-in components now prove the pipeline end to end:

- `^ReusableMinefieldGenerator` maintains deterministic, non-stacking mine patterns.
- The native turtle minelayer AI now supports mission marker seeds, accelerated opening scans, roster filtering, and stuck recovery.
- `^ReusablePointDefense` intercepts explicitly tagged native Missile or Bullet projectiles, with harmless removal as the safe default.
- `^ReusableSalvageable` can create value-carrying battlefield salvage using the stock RA crate presentation.

The three actor components do not change an existing concrete unit merely by being loaded; a faction, actor, or mission must opt in. The minelayer enhancement is explicitly enabled for the existing turtle AI, where it performs two faster opening scans and remains compatible with mission marker overrides.

## Source-by-source judgment

| Source | Best reusable value | Main caution | Decision |
|---|---|---|---|
| OpenRA Mod SDK | canonical mod packaging, manifest layout, lint flow | examples are not a content library | use as structural baseline |
| Combined Arms | broadest mechanic library; layered defense, carriers, abilities, AI compositions, campaigns | mixed binary provenance and a substantial engine fork | primary code/pattern reference; quarantine binaries |
| Generals Alpha | asymmetric modern factions, supply logistics, generals-style progression, collector AI | much presentation content derives from classic C&C games | port logistics/mechanics; create original presentation |
| RA+ | countries, subfactions, national bonuses, roster gates, naval/air variants | Westwood art and sounds | synthesize the faction contract; mechanics only |
| Shattered Paradise | strong faction differentiation, mutation/status ideas, mission-aware bots | non-code content is non-commercial Creative Commons | code/pattern reference; no production asset reuse |
| Romanov’s Vengeance | garrisons, amphibious production, RA2/YR faction logic | requires commercial game content and mixed placeholders | mechanics only; prefer cleaner OpenRA RA2 reference where possible |
| OpenRA RA2 | clean RA2 behavior reference for carriers, weather, mind control, disguise | original RA2 content is outside the code license | use code architecture, never assume content rights |
| Cameo | huge experimental mechanic laboratory: promotions, conditions, AI, factions, weapons | mixed non-free/CC-BY-NC content and extreme breadth | mine for isolated mechanics; never bulk-import |
| OpenHV | strongest open-content-oriented reference: missions, bots, salvage, terrain, carriers, teleport | license varies by content folder | preferred source when an exact folder license is compatible |

## What we should build first

The first wave is chosen for leverage across new factions rather than spectacle:

- A stable **faction/doctrine contract**. Every soldier, vehicle, ship, aircraft, building, defense, support power, and AI preference can then opt into a country plus doctrine without duplicating whole rulesets.
- **Supply logistics**, because collectors, depots, and convoys create both asymmetric economy and ready-made mission objectives.
- **Point defense**, because missile interception connects SAM sites, ships, aircraft, cruise missiles, drones, and artillery into one layered system.
- **Garrisons**, because a modern Earth game needs cities to matter to infantry and AI.
- **Carrier/drone wings**, as one parent/child abstraction usable by navy, air, missiles, and unmanned systems.
- **Unit-composition AI**, after units receive stable role tags. This converts a roster into actual doctrine.
- **Commander promotions**, after doctrine identifiers stabilize; otherwise the upgrade tree would encode throwaway faction assumptions.
- A **campaign objective toolkit**, extracted from recurring Lua structures while all story, dialogue, and mission geography remains original.

## Domain coverage

### Factions and strategies

RA+ gives the clearest roster/subfaction model, Combined Arms adds captured-technology and composition-aware AI, Generals Alpha demonstrates asymmetric economies and general powers, and Cameo stress-tests very large faction/promotion graphs. We should combine these as a small contract: country, doctrine, role tags, prerequisites, bonuses, AI composition IDs, and presentation metadata.

The critical lesson is to avoid cloning an entire rules file per faction. Shared role templates should carry baseline behavior; doctrine components should grant small, explicit deltas.

### Soldiers and ground vehicles

The reusable value is the counter-role grammar, not thousands of copyrighted identities. Infantry roles should include rifle, anti-tank, anti-air, engineer, reconnaissance, medic/support, special forces, and heavy/suppression. Vehicle roles should include scout, APC/IFV, main battle tank, tank destroyer, artillery, MLRS, air defense, engineering/recovery, amphibious, and logistics.

Each role needs a target-type contract, production role tag, AI value, veterancy curve, transport footprint, counter set, and original sprite. The catalog retains every upstream example for balancing comparisons.

### Buildings and defenses

The common base grammar is reusable: command/construction, power, refinery/logistics, infantry, vehicle, air, naval, radar, technology, repair, storage, and superweapon/support structures. Defensive components should be composable: direct fire, anti-armor, anti-air, artillery, detection/jamming, point defense, garrison, and mines.

The integrated `^ReusableMinefieldGenerator` is the first example of this model: it changes no existing actor until a concrete building opts in.

### Navy and air

Combined Arms, RA+, Romanov’s Vengeance, Cameo, and OpenHV collectively cover patrol boats, submarines, destroyers, missile ships, landing craft, carriers, amphibious units, interceptors, bombers, gunships, transports, and drones. We should derive role templates and behavior contracts, then create original faction-specific actors and sprites.

Carrier code is especially reusable because the same parent/child lifecycle can support aircraft wings, loitering munitions, reconnaissance drones, and replenishing missile pods.

### Effects and weapons

The high-value mechanic set is guided/ballistic missiles, beams, trails, projectile husks, point-defense tags, weather, thermal/status conditions, suppression/jamming, shields, and targeted abilities. These must be ported in small groups with deterministic tests and performance budgets. Visual effects and audio are separate assets and need original or clearly compatible sources.

### Missions and stories

The scanner now extracts Lua calls and tags recurring beats rather than copying prose. Combined Arms provides the deepest library, while OpenHV has the best open-project mission reference. The most reusable patterns are:

- primary/secondary objective lifecycles;
- reinforcements and timed escalation;
- convoy escort/interdiction and evacuation;
- capture/infiltration and technology rewards;
- base-building versus fixed-force phases;
- patrols, hunts, waves, and survival pressure;
- camera/reveal/beacon beats;
- localized briefings, dialogue, and notifications;
- difficulty-dependent composition and timing.

Our stories, characters, dialogue, geography, and briefing media should remain original. Only the scripting architecture and tested objective machinery should be shared.

## Asset rule

No bulk copy of `.shp`, `.vxl`, `.hva`, audio, music, movies, or icons is approved by this analysis. GPL code headers do not license unrelated content. An asset may enter only with:

- exact source path and commit;
- author/credits evidence;
- an explicit redistribution license compatible with the game’s intended distribution;
- palette, canvas, pivot, frame, and facing validation;
- in-game turning/render validation for directional units;
- an original replacement plan when provenance is missing or non-commercial-only.

OpenHV is the first place to look for potentially reusable assets because it records per-folder licenses, but those licenses still need to be resolved individually.

## Delivery sequence

**Foundation (current):** pinned sources, reproducible scanner, component schema, licensing gates, abstract component rules, isolated build path, and full RA lint.

**Systems wave:** faction/doctrine contract, supply economy, point defense, garrisons, carrier/drone wings, role tags, and composition AI.

**Content wave:** original Saudi/Yemen and future-faction soldiers, tanks, defenses, naval and air rosters built on those systems. Every directional sprite passes the vehicle-sprite audit before acceptance.

**Campaign wave:** objective toolkit, convoy/extraction patterns, authored mission templates, original briefings/dialogue, and AI marker support.

**Expansion wave:** promotions, capture technology, salvage, weather/status, advanced projectiles, terrain enrichment, and more experimental systems.

## Definition of plug-in ready

A component is plug-in ready only when its manifest records pinned sources and licenses, engine code compiles, RA MiniYAML and all bundled maps validate, a concrete fixture exercises its YAML contract, automated behavior checks exist where practical, and live play verifies the actual player-facing behavior. “Found upstream” and “compiles” are intermediate states, not completion.
