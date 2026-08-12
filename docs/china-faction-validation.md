# China faction validation

Validation date: 2026-08-12 (Asia/Riyadh)

## Delivery identity

- Dedicated worktree: `C:\Users\Admin\Code\hq\games\OpenRA-AI-china`
- Outer branch: `codex/china-faction`
- Base outer commit: `c9294e60b3bffb0e1deb7bf8eed7290dddea16fd`
- OpenRA engine commit: `a5ae3f69e04d297f60b29cacc55b93fc75f9975f`
- No publishing, deployment, or hosted CI was performed.

## Implemented contracts

- The faction selector registers `China` as an Allied-side country and supplies 1x, 2x, and 3x flags plus explicit China aliases for every in-game sidebar and command-button chrome state.
- China inherits the complete native Allied construction yard, power, refinery/harvester, repair, radar, advanced-tech, barracks, war factory, helipad, and shipyard chains.
- The original roster is `CNRIFLE`, `CNNETWORK`, `CNPORTABLE`, `REDSPEAR`, `CNQILIN`, `CNLYNX`, `CNZBD`, `CNPHL`, `CNSKYSPEAR`, `CNCLOUD`, `CNCRANE`, `CNLUYANG`, and `CNHAIWANG`.
- Native traits handle infantry deployment, selectable portable-missile roles, the command-network condition, transports, amphibious locomotion, aircraft ammo/rearming, veterancy, body/turret layering, wakes, naval targeting, sinking, directional husks, and projectile flight.
- `Red Spear` is fictional, build-limit-one, command-network/precision focused, and has no Tanya-style demolition/C4 behavior.
- AI personality configuration covers economy and the complete land, air, and naval build/attack roster.
- Audio contains 25 original procedural effects plus 26 generic synthetic Mandarin/English unit and scenario voice lines. Provenance explicitly records that no real person is represented or imitated.
- `03: Haitan Network` is a fictional RTS mission with a live network-specialist deployment, water-gated amphibious landing, ground/air/naval waves, a full starting production base, and 240 surplus power at tick 2.

## Sprite contract regeneration

`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-china-assets.ps1` was run after moving the old ignored staging directory to recoverable artifact storage. The command exited 0 in 93.9 seconds. Its exact contract lines were:

```text
cnrifle: 378 authored frames at 24x24
cnnetwork: 378 authored frames at 24x24
cnportable: 378 authored frames at 24x24
redspear: 378 authored frames at 24x24
cnqilin: 64 authored frames at 44x44
cnqilinhusk: 64 authored frames at 44x44
cnlynx: 64 authored frames at 32x32
cnlynxhusk: 64 authored frames at 32x32
cnzbd: 64 authored frames at 42x42
cnzbdhusk: 64 authored frames at 42x42
cnphl: 64 authored frames at 44x44
cnphlhusk: 32 authored frames at 44x44
cnskyspear: 16 authored frames at 56x56
cnskyspearhusk: 16 authored frames at 56x56
cncloud: 16 authored frames at 48x48
cncloudhusk: 16 authored frames at 48x48
cncrane: 32 authored frames at 56x56
cncranehusk: 32 authored frames at 56x56
cnluyang: 16 authored frames at 64x64
cnluyangturret: 32 authored frames at 64x64
cnluyangsink: 64 authored frames at 64x64
cnhaiwang: 16 authored frames at 72x72
cnhaiwangturret: 32 authored frames at 72x72
cnhaiwangsink: 64 authored frames at 72x72
cncranerotor: 12 authored frames at 56x56
China faction assets built successfully.
```

The four infantry SHPs each use the native 378-frame E1 layout: eight genuinely authored facings across stand, alternate stand, run, fire, lie-down, prone, stand-up, prone-fire, idle, five death families, and parachute. Planes author 16 source facings and declare 64-facing interpolation; the helicopter authors 32 classic facings with a separate rotor; ground units use 32-facing body/turret layers and directional wrecks; ships use directional turrets, wakes, production exits, naval movement, and sinking sequences.

## Exact validation output

Clean engine compile:

```text
Build succeeded.
    0 Warning(s)
    0 Error(s)
Time Elapsed 00:00:00.71
Clean complete.
Building in Release configuration...
Build succeeded.
    0 Warning(s)
    0 Error(s)
Time Elapsed 00:00:07.91
Build succeeded.
```

Faction, sprite, mission, research, resolved-rules, and Saudi/Yemen/air regression contracts:

```text
.........................................                                [100%]
41 passed in 12.60s
```

Full Red Alert YAML/Fluent/map validation exited 0 after testing all bundled maps. The identifying output was:

```text
Testing mod: Red Alert
Testing default sequences for SNOW
Testing default sequences for INTERIOR
Testing default sequences for TEMPERAT
Testing default sequences for DESERT
Testing Fluent references
...
Testing map: 03: Haitan Network
...
Testing map: Ysmir
```

Missing-sprite validation exited 0 with exactly:

```text
Tileset: SNOW
Tileset: INTERIOR
Tileset: TEMPERAT
Tileset: DESERT
```

Normal-AI full build-tree verification exited 0 with:

```json
{"ok": true, "tick": 12527, "buildings": 12, "units": 24, "evidence": "C:\\Users\\Admin\\Code\\hq\\games\\OpenRA-AI-china\\.artifacts\\china-faction\\ai-build-tree\\ai-build-tree.json"}
```

Its evidence has `missing_buildings: []` and `missing_units: []`. Observed buildings include `fact`, `powr`, `apwr`, `proc`, `tent`, `weap`, `fix`, `dome`, `atek`, `hpad`, `syrd`, and `mslo`; all 13 China roster actors were produced.

Live movement/combat verification exited 0 with:

```json
{"ok": true, "map": "03: Haitan Network", "start_tick": 2, "combat_tick": 3406, "orders": 0, "kills": 8, "losses": 15, "moved_actors": 15, "visible_enemies": 5}
```

The engine telemetry records actual movement vectors in 15 distinct directions/paths; completion of both the network-deployment and sea-gate/eastern-beach amphibious objectives by tick 1605; aircraft ammo/rearming state; active ground, air, and naval combat; 8 kills and 15 losses by tick 3406; and starting power `240`. The bridge's aggregate `orders` counter remains zero in multi-session mode, so success is asserted from actor movement vectors, objective states, activities, ammo, targets, kills, and losses instead.

Mission package:

```text
SHA256: 79ac11a0649efcac441c2e05e799ad835196a1b998216a09f64adbaeff7d73f2
Testing map: 03: Haitan Network
```

Native renderer capture:

```text
Captured OpenRA PID 53304 to C:\Users\Admin\Code\hq\games\OpenRA-AI-china\.artifacts\china-faction\live\04-native-renderer.png (2902x1676).
```

## Visual and telemetry evidence

- Native renderer: `.artifacts/china-faction/live/04-native-renderer.png`
- Live deployment: `.artifacts/china-faction/live/01-china-deployment.png`
- Network/amphibious maneuver: `.artifacts/china-faction/live/02-network-and-amphibious-maneuver.png`
- Combined-arms contact: `.artifacts/china-faction/live/03-combined-arms-contact.png`
- Full live telemetry: `.artifacts/china-faction/live/telemetry.json`
- AI build timeline: `.artifacts/china-faction/ai-build-tree/ai-build-tree.json`

The three tactical evidence frames are transparently labeled `live-engine-telemetry-fallback`: the multi-session renderer exposes live actors and telemetry but not `CaptureCompanionFrame`, so the verifier renders those live engine positions over the native map preview. `04-native-renderer.png` is an independent direct screenshot from the visible OpenRA renderer.

## Balance concerns

- The command-network aura's 12% firepower and 10% reload improvement makes tightly grouped Qilin/Longbow formations efficient; competitive tuning should watch aura uptime and overlap with veterancy.
- Sea Dragon combines amphibious access, transport capacity, autocannon, and missiles. Its current price is meant to pay for flexibility, but island maps may magnify that value.
- Longbow and Haiwang standoff ranges can dominate narrow chokepoints if scouting is too easy. Counter-battery pressure, ammo cadence, and vision sharing are the first knobs to revisit.
- Portable Missile Team mode switching is deliberately manual and tactical; AI weights produce it, but automated role timing remains less precise than a human player's.
- The verification battle is intentionally punishing (8 kills, 15 losses) and shows that unsupported forward pushes fail. Mission difficulty-wave sizes should receive broader human playtesting before a balance freeze.

## Integration

The outer repository records the engine submodule at `a5ae3f69e04d297f60b29cacc55b93fc75f9975f`. To integrate locally:

```powershell
git switch codex/china-faction
git submodule update --init engine/openra
$env:DOTNET_ROOT = 'C:\path\to\dotnet-8'
.\engine\openra\make.cmd all
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-china-assets.ps1
```

The committed SHP/WAV/mission assets are already playable; regeneration is only required when changing source art, audio, or mission inputs.
