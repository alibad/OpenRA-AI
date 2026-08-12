# Air-warfare implementation and validation

Validation date: **2026-08-12**. Inventory research cutoff: **2026-08-11**; see
[air-warfare-research.md](air-warfare-research.md) for the authoritative-source
record and the limits of the real-world claims.

## Delivered roles

- **F-15SA:** premium Saudi air-superiority fighter. It uses OpenRA's native
  fixed-wing `^Plane` movement and `AttackAircraft` attack-run pipeline, separate
  missile and cannon ammunition, a Saudi copy of the stock airfield for Plane
  production and rearming, a dedicated 16-facing mesh interpolated to 64 runtime
  facings, directional muzzle effects, shadow, cameo, and airborne husk.
- **AH-64E:** Saudi close-support helicopter. It uses the native helicopter
  movement and `AttackAircraft` pipeline, distinct cannon and rocket ammunition,
  stock helipad production/rearming, separate 12-frame fast/slow rotor animation,
  a dedicated 32-facing mesh, shadow, cameo, and husk.
- **Samad:** Yemen/Houthi-inspired scouting and one-way strike UAV. It has 16
  level facings plus 16 independently rendered terminal-dive projectile facings.
  The loitering actor uses native `^Plane` movement and `AttackAircraft`; firing
  launches a player-coloured OpenRA `Missile` using the dive sequence, consumes
  the one payload, and removes the launch actor. Combat destruction instead spawns
  its dedicated 16-facing aircraft husk. It cannot return or rearm.

The former custom `AttackDive` trait and `DiveAttack` activity were deleted. The
three aircraft now share the same engine-owned movement, turn interpolation,
targeting, attack, stance, veterancy, and production conventions as stock Red
Alert aircraft. Their unit art follows the stock contracts rather than substituting
one rotated image: F-15SA and Samad have 16 authored body headings, AH-64E has 32,
and OpenRA interpolates the configured sequences to 64 runtime facings.

All airframe frames are projected from fixed-camera 3D geometry. No directional
aircraft sequence is made by rotating a flat source image. The generated WAV
effects are deterministic original synthesis. The Arabic/English responses use
generic Microsoft Edge synthetic voices; the scripts and provenance file disclose
the providers, voice IDs, text, and hashes. They are not intended to imitate a
real person.

## Automated validation

Run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-red-sea-air-assets.ps1
.\.venv\Scripts\python.exe -m pytest services/worldgen/tests/test_air_warfare_assets.py -q
Push-Location engine/openra
..\..\.dotnet\dotnet.exe build OpenRA.Mods.Common/OpenRA.Mods.Common.csproj -c Debug -p:EngineRootPath='..\..\generated\air-warfare-build'
Pop-Location
```

The clean asset command deletes only the scoped generated air assets, regenerates
and packs the sprites and audio, then runs OpenRA `--check-yaml` and
`--check-missing-sprites`. The focused Python suite checks facing counts and
uniqueness, native-scale bounds, separate rotor/effect animations, the native
Samad aircraft/projectile contract, F-15/AH-64 rearming and factory contracts,
stock stances and veterancy, AI roster registration, multi-ammo observation
serialization, and PCM audio format/duration. The broader asset suite checks the
same actors in the complete faction/build-tree package.

Final results: clean generation and both OpenRA checks passed; **7 focused pytest
tests and 22 broader asset tests passed**; `OpenRA.Mods.Common` built with
**0 warnings and 0 errors**.

## Live rendered evidence

The current native-pipeline telemetry is under `artifacts/aircraft-native-live/`.
The older rendered captures under `artifacts/air-warfare/` predate the native
Samad conversion and are retained only as historical visual references; they are
not evidence for the current implementation.

| Behavior | Evidence | Observation |
|---|---|---|
| Saudi production chain | `saudi/telemetry.json` | A live normal Saudi match built Weapons Factory, Radar Dome, Tech Center, Saudi Airfield, and Helipad before producing F-15SA and AH-64E through their native Plane/Helicopter queues. |
| Four-direction flight | `saudi/telemetry.json` | Both aircraft completed east, north, west, and south movement legs; their reported facings changed on every leg and neither aircraft was lost. |
| Native attack runs | `saudi/telemetry.json` | A live attack-move consumed F-15 ammunition from 16 to 4 and AH-64 ammunition from 30 to 5 while destroying enemy targets. No custom movement or attack activity was loaded. |
| Samad air-defense interaction | `samad/telemetry.json` | Starting Samads used native `FlyIdle`/aircraft state and were intercepted by long-range Saudi air defense when committed before suppression, confirming that the drone participates in normal OpenRA air targeting and counterplay. Projectile release is covered by the rules/sequence tests and OpenRA asset validation, not claimed as a successful live strike in this run. |

## Remaining subjective concerns

- The F-15's twin tails necessarily compress at due-north and due-south headings
  at native Red Alert scale. They remain readable in motion, but this is the
  weakest silhouette pair.
- The Samad dive is now a separate missile projectile rather than a body-state
  change. This follows the stock weapon pipeline and avoids a discontinuous body
  rotation, but a successful current-build strike still needs a human visual
  playtest after suppressing the mission's long-range air defense.
- Costs, AI weights, damage, reloads, and counter relationships are internally
  differentiated and passed functional tests, but competitive balance remains a
  playtest judgment rather than a mechanically provable result.
