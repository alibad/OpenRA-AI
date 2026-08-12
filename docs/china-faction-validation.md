# China faction validation

Validation date: 2026-08-12 (Asia/Riyadh)

## Delivery identity

- Dedicated worktree: `C:\Users\Admin\Code\hq\games\OpenRA-AI-china`
- Outer branch: `codex/china-faction`
- Base outer commit: `c9294e60b3bffb0e1deb7bf8eed7290dddea16fd`
- Feature-engine commit: `667687c52f2d826dcb5f04581698e0f7b93c6fb6`
- Canonical OpenRA `main`: `69e693344bd07656dd03d8b86855d518b8254c7c`
- `alibad/OpenRA:main`: `69e693344bd07656dd03d8b86855d518b8254c7c`
- No deployment or hosted CI was performed; validation was local and the validated engine commit was pushed to `main`.

## Implemented contracts

- The faction selector registers `China` as an Allied-side country and supplies 1x, 2x, and 3x flags plus explicit China aliases for every in-game sidebar and command-button chrome state.
- China inherits the complete native Allied construction yard, power, refinery/harvester, repair, radar, advanced-tech, barracks, war factory, helipad, and shipyard chains.
- The original combat roster is `CNRIFLE`, `CNNETWORK`, `CNPORTABLE`, `REDSPEAR`, `CNQILIN`, `CNLYNX`, `CNZBD`, `CNPHL`, `CNMANTIS`, `CNSKYSPEAR`, `CNCLOUD`, `CNCRANE`, `CNLUYANG`, `CNHAIWANG`, `CNHAIYING`, `CNKUNLUN`, and `CNJIAOLONG`.
- Original fixed defenses are `CNBASTION`, `CNSKYSHIELD`, and `CNSPECTRUM`, covering direct fire, anti-air, and sensor/jammer/shroud-control roles.
- Native traits handle infantry deployment, selectable portable-missile roles, the command-network condition, transports, amphibious locomotion, aircraft ammo/rearming, veterancy, body/turret layering, wakes, naval targeting, sinking, directional husks, and projectile flight.
- `Red Spear` is fictional, build-limit-one, command-network/precision focused, and has no Tanya-style demolition/C4 behavior.
- AI personality configuration covers economy and the complete land, air, and naval build/attack roster.
- Audio contains 32 original procedural effects plus 26 generic synthetic Mandarin/English unit and scenario voice lines. Provenance explicitly records that no real person is represented or imitated.
- `03: Haitan Network` is a fictional RTS mission with a live network-specialist deployment, water-gated amphibious landing, ground/air/naval waves, a full starting production base, and 240 surplus power at tick 2.

## Sprite contract regeneration

`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-china-assets.ps1` was rerun clean after the gap-completion work. The command exited 0 in 101 seconds. Its exact new and identifying contract lines were:

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
cnmantis: 64 authored frames at 44x44
cnmantishusk: 64 authored frames at 44x44
cnhaiying: 16 authored frames at 56x56
cnhaiyingturret: 32 authored frames at 56x56
cnhaiyingsink: 64 authored frames at 56x56
cnkunlun: 144 authored frames at 72x72
cnkunlunturret: 32 authored frames at 72x72
cnkunlunsink: 64 authored frames at 72x72
cnjiaolong: 16 authored frames at 56x56
cnjiaolongsink: 64 authored frames at 56x56
cnbastion: 12 authored frames at 48x48
cnbastiontop: 64 authored frames at 48x48
cnskyshield: 12 authored frames at 48x48
cnskyshieldtop: 64 authored frames at 48x48
cnspectrum: 12 authored frames at 48x48
cnspectrumtop: 32 authored frames at 48x48
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
Time Elapsed 00:00:00.40
Clean complete.
Building in Release configuration...
Build succeeded.
    0 Warning(s)
    0 Error(s)
Time Elapsed 00:00:07.09
Build succeeded.
```

Full combined-main worldgen, companion, and evaluation suites (including Saudi/Yemen, Turkey, Iran, and China):

```text
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 96%]
........                                                                 [100%]
224 passed, 1 warning in 29.78s
```

The warning is an external `pydantic-settings` incomplete-forward-reference warning. The China contract suite was also pointed at the exact final integration worktree:

```text
..............                                                           [100%]
14 passed in 3.52s
```

Engine unit tests:

```text
Passed!  - Failed:     0, Passed:   476, Skipped:     2, Total:   478, Duration: 306 ms - OpenRA.Test.dll (net8.0)
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
{"ok": true, "tick": 11525, "buildings": 15, "units": 22, "evidence": "C:\\Users\\Admin\\Code\\hq\\games\\OpenRA-AI-china\\.artifacts\\china-faction\\ai-build-tree\\ai-build-tree.json"}
```

Its evidence has `missing_buildings: []` and `missing_units: []`. The required building contract includes `fact`, `proc`, `tent`, `weap`, `dome`, `atek`, `fix`, `hpad`, `syrd`, `cnbastion`, `cnskyshield`, and `cnspectrum`; all 17 custom China combat actors were produced organically from an MCV-only start.

Live movement/combat verification exited 0 with:

```json
{"ok": true, "map": "03: Haitan Network", "start_tick": 2, "combat_tick": 3406, "orders": 0, "kills": 10, "losses": 20, "moved_actors": 17, "visible_enemies": 3}
```

The engine telemetry records actual movement vectors for all 17 custom combat roles; completion of both the network-deployment and sea-gate/eastern-beach amphibious objectives by tick 1605; aircraft ammo/rearming state; active ground, air, and naval combat; 10 kills and 20 losses by tick 3406; and starting power `240`. The bridge's aggregate `orders` counter remains zero in multi-session mode, so success is asserted from actor movement vectors, objective states, activities, ammo, targets, kills, and losses instead.

Mission package:

```text
SHA256: F5758014FAC89F5F1E9FC63D2233FA6FFC6895177B039908924D4B369542D670
Testing map: 03: Haitan Network
```

Native renderer capture:

```text
Captured OpenRA PID 61780 to C:\Users\Admin\Code\hq\games\OpenRA-AI-china\.artifacts\china-faction\live\04-native-renderer.png (2902x1676).
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
- Mantis and Sky Shield overlap strongly when massed. Their shared no-ground-attack weakness is intentional, but range/cost should be watched on air-heavy maps.
- Kunlun adds a large transport body and modest self-defense to amphibious play; beach maps should test whether its capacity justifies enough escort risk.
- The verification battle is intentionally punishing (10 kills, 20 losses) and shows that unsupported forward pushes fail. Mission difficulty-wave sizes should receive broader human playtesting before a balance freeze.

## Integration

The validated result is already integrated and pushed. The single user-facing launch path is the canonical checkout:

```powershell
Set-Location C:\Users\Admin\Code\hq\games\OpenRA
.\launch-game.cmd Game.Mod=ra
```

Select `China` in a skirmish, or open Missions -> OpenRA AI -> `03: Haitan Network`. The committed SHP/WAV/mission assets are already playable; regeneration is only required when changing source art, audio, or mission inputs.
