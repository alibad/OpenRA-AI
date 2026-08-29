# Turkey faction delivery and validation

Validated locally on 2026-08-12 first from the dedicated worktree `OpenRA-AI-turkey` and then from the exact canonical OpenRA `main` tree at `2ee9396c7a`. No deployment or hosted CI was used.

## Delivered scope

- The faction selector exposes `Turkey`, with Turkey-specific starting units and Random Allies integration.
- The native Allied construction, power, ore economy, repair, radar, airfield, helipad, technology, naval-yard, rearm, veterancy, transport, deploy, targeting, and projectile contracts underpin the faction.
- The combat roster contains four infantry actors, six ground vehicles, three aircraft, and three naval actors: Mechanized Rifleman, Portable AT Specialist, Forward Drone Operator, Grey Wolf, Bozkir tank, Aras-8 wheeled carrier, Yildirim artillery, Gokkalkan layered air defense, Sancak electronic-warfare/designation vehicle, Deniz Kaplan amphibious assault vehicle, Kuzgun-M UCAV, Turna-AH rotorcraft, Sahin-X fighter, Marmara frigate, Ege corvette, and Poyraz unmanned surface vessel.
- Grey Wolf is fictional, build-limit-one, has a close-support/team identity, and remains detectable and counterable. No real leader or recent attack is represented.
- Beginner, easy, medium, rush, normal, turtle, and naval bot personalities have Turkey production and squad composition rules.
- `03: Straits Shield` is a construction-enabled combined land, drone, amphibious, and maritime mission with the complete technology progression, economy, relay capture, air and naval objectives, and active opposition.
- Original SHP sprites, directional husks and sinks, effects, icons, cameos, WAV effects, and generic Turkish/English responses are generated reproducibly by the checked-in scripts. Voice generation provenance is recorded in `assets/turkey-faction/voice-provenance.json`.

## Changed-file groups

- OpenRA wiring and rules: `engine/openra/mods/ra/{mod.yaml,missions.yaml,rules/world.yaml,rules/turkey.yaml,weapons/turkey.yaml,sequences/turkey.yaml,audio/voices.yaml,fluent/rules.ftl}`.
- Shipped mission: `engine/openra/mods/ra/maps/straits-shield-2026.oramap` and the editable sources under `missions/turkey-faction/straits-shield/`.
- Runtime art and audio: Turkey SHP/WAV packages under `engine/openra/mods/ra/bits/` and the three Red Sea UI glyph atlases under `engine/openra/mods/ra/uibits/`.
- Reproducible generation and checks: `scripts/build-turkey-assets.ps1`, `scripts/build-turkey-mission.py`, `scripts/build-turkey-sprites.py`, `scripts/turkey_directional_assets.py`, `scripts/generate-turkey-sfx.py`, `scripts/generate-turkey-voices.py`, `scripts/validate-turkey-live.py`, `scripts/build-turkey-ai-validation-map.py`, and `scripts/validate-turkey-ai-progression.py`.
- Contracts and documentation: `services/worldgen/tests/test_turkey_faction.py`, `docs/turkey-faction-research.md`, this report, and `assets/turkey-faction/`.

## Exact validation results

### Clean asset build and data contracts

Command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-turkey-assets.ps1
```

Result on integrated `main`: exit 0 in 125.2 seconds against OpenRA commit `2ee9396c7a`. The build started with an empty Turkey staging directory, regenerated and installed 54 SHP packages, rebuilt the mission, and produced `artifacts/turkey-faction/asset-build-telemetry.json` with `validation: passed`. The mission packer canonicalizes source line endings, and the shipped mission SHA-256 is reproducibly `c55bb30b0cadcb863f5a7b3fb3ed2ccd515c0b9a9172ed7bce3019be08e6d90d` across the feature and main worktrees.

- Full OpenRA `--check-yaml` validation passed for the RA mod and every shipped map, including Straits Shield.
- `--check-missing-sprites` passed for SNOW, INTERIOR, TEMPERAT, and DESERT.
- `services.worldgen.tests.test_turkey_faction`: 8/8 tests passed in 0.221 seconds on the final integrated `main` tree.
- Selector contracts verify the `turkey` faction entry, its flag region, Random Allies membership, and exactly one matching chrome region.

### Sprite frame and uniqueness audit

Command:

```powershell
python C:\Users\Admin\.codex\skills\audit-openra-vehicle-sprites\scripts\audit_vehicle_sprites.py --input-root generated\turkey-sprites --vehicles bozkir aras8 yildirim gokkalkan sancak denizkaplan --output artifacts\turkey-faction\directional-audit
```

Result: exit 0. Bozkir, Aras-8, Yildirim, Gokkalkan, Sancak, and Deniz Kaplan each contain 64 authored frames: 32/32 unique hull facings and 32/32 unique turret facings. Every structural contract passed. Cardinal front-landmark placement, facing continuity, and independent turret layers were visually inspected in the generated audit sheets.

- Mechanized Rifleman, Portable AT Specialist, Forward Drone Operator, and Grey Wolf each contain 378 authored frames supporting eight authored facings and idle, run, fire, prone, and death sequences. Their respective pixel-unique frame counts are 164, 169, 160, and 163; repeated frames are intentional animation holds and mirrored timing, not rotated source art.
- Kuzgun-M and Sahin-X each contain 16/16 authored unique aircraft facings and use the native 16-to-64 interpolation contract.
- Turna-AH contains 32/32 authored unique classic facings plus an independent 12/12-frame rotor sequence.
- Marmara, Ege, and Poyraz each contain 48/48 unique live frames and 96/96-frame sinking sequences, with native wake, targeting, naval-yard, movement, and death traits.
- All six directional ground husks contain 64 frames matching their layered live-body contracts.

### Engine compilation

Command (using the repository's configured local .NET SDK):

```powershell
dotnet build OpenRA.slnx -c Debug --nologo
```

Result on integrated `main`: exit 0 in 24.37 seconds; build succeeded with 75 analyzer warnings and 0 errors. The warnings are in unchanged pre-existing C# engine/AI bridge files; this faction commit adds no C# or custom engine code.

### Live mission movement and combat

Result: `artifacts/turkey-faction/live/live-validation-telemetry.json` reports `passed: true` on `03: Straits Shield`.

- Four synchronized orders were accepted and completed: Aras-8 moved north 3 cells and faced 0; Deniz Kaplan moved east 3 cells and faced 768; one Mechanized Rifleman moved south 3 cells and faced 512; another moved west 3 cells and faced 256.
- Attack-move and focus-fire orders were accepted. Target acquisition, damage/destruction, kill-counter change, and enemy return fire were all observed.
- The final sample at tick 1120 recorded one enemy Ege corvette destroyed and two attacking units lost. This confirms actual combat/counterplay rather than a passive visual scene.

### Live AI progression

Result: `artifacts/turkey-faction/ai-progression-telemetry.json` reports `passed: true` for a locked Turkey player delegated to the native `normal` bot personality.

- Tick 730: MCV present.
- Tick 850: construction yard deployed.
- Tick 1100: power plant complete.
- Tick 1980: refinery and harvester complete.
- Tick 3240: war factory complete.
- Tick 3740: first Turkey-specific Aras-8 produced.

The persistent faction rules also list full production and air/naval squad compositions for every standard bot personality. The temporary validation range was not added to the shipped map catalog.

### Selector stability

A current-build RA process successfully passed mod initialization and launched the Turkey mission after selector registration. The final automated contract suite also checks that the Turkey chrome region is unique. An earlier duplicate-region failure discovered during live launch was corrected before the results above were recorded.

## Visual evidence

- `artifacts/turkey-faction/live/straits-shield-opening.png`: current-build 1280x720 player viewport at tick 390.
- `artifacts/turkey-faction/live/straits-shield-live-combat.png`: current-build 1280x720 player viewport after the live engagement at tick 1120.
- `artifacts/turkey-faction/turkey-ai-progression.png`: current-build 1280x720 native-bot base at tick 3743.
- `artifacts/turkey-faction/directional-audit/all-facing-composites.png`: six complete live hull/turret facing sets.
- `artifacts/turkey-faction/directional-audit/cardinal-handedness-check.png`: explicit north/west/south/east landmark check.
- `artifacts/turkey-faction/directional-audit/layer-breakdown.png` and `bozkir-independent-turret.png`: body/turret separation evidence.

## Balance risks and follow-up targets

- Forward designation currently adds a 25% damage multiplier. The Sancak and Drone Operator can create high uptime, so simultaneous-source behavior and team-game focus fire should be measured.
- The Mechanized Rifleman's transport-proximity bonus rewards intended combined-arms play, but carrier-heavy blobs may outperform unsupported infantry too efficiently.
- Grey Wolf's support aura and stealth are deliberately countered by detection, anti-infantry fire, and a one-unit cap; clustered infantry efficiency still needs multiplayer sampling.
- Air-defense layering, Sancak support, and Gokkalkan coverage may become oppressive on choke-heavy maps, while the live naval engagement suggests unsupported amphibious/UCAV attacks remain costly.
- Fighter, drone, frigate, and corvette prices were tuned against native RA pacing. Long high-income matches and naval-only maps need broader matchup data.
- Amphibious path selection and ship maneuvering should be sampled on additional community maps with narrow coastlines and congested yards.

## Local integration

This repository uses `engine/openra` as a nested Git repository, so integrate in dependency order:

1. Merge or cherry-pick the Turkey commit from `engine/openra` into the intended OpenRA integration branch.
2. Merge or cherry-pick the parent `OpenRA-AI` commit, which records that nested commit and adds source generators, mission sources, research, tests, and evidence.
3. Initialize/update the nested repository to the recorded commit.
4. Re-run `scripts\build-turkey-assets.ps1`, then `dotnet build OpenRA.slnx -c Debug --nologo` from `engine/openra`.

No remote push is required for local integration, and no deployment artifacts were created.
