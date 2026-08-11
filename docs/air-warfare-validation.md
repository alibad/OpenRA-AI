# Air-warfare implementation and validation

Validation date: **2026-08-11**. Inventory research cutoff: **2026-08-11**; see
[air-warfare-research.md](air-warfare-research.md) for the authoritative-source
record and the limits of the real-world claims.

## Delivered roles

- **F-15SA:** premium Saudi air-superiority fighter. It uses the native fixed-wing
  flight and attack-run pipeline, four air-to-air missiles, a limited cannon,
  helipad rearming, a dedicated 16-facing mesh, directional muzzle effects,
  shadow, cameo, and airborne husk.
- **AH-64E:** Saudi close-support helicopter. It uses the native helicopter
  movement pipeline, distinct cannon and rocket ammunition, separate 12-frame
  fast/slow rotor animation, a dedicated 32-facing mesh, shadow, cameo, and husk.
- **Samad:** Yemen/Houthi-inspired scouting and one-way strike UAV. It has 16
  level facings plus 16 independently rendered terminal-dive facings. `AttackDive`
  monotonically reduces its altitude, commits at contact range, consumes its one
  payload, and destroys the actor. It cannot return or rearm.

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
`--check-missing-sprites`. The Python suite checks facing counts and uniqueness,
native-scale bounds, separate rotor/effect animations, irreversible Samad dive
semantics, F-15/AH-64 rearming and factory contracts, AI roster registration,
multi-ammo observation serialization, and PCM audio format/duration.

Final results: clean generation and both OpenRA checks passed; **6 pytest tests
passed**; `OpenRA.Mods.Common` built with **0 warnings and 0 errors**.

## Live rendered evidence

The evidence is under `artifacts/air-warfare/` and was captured from the running
local game, not from sprite sheets or YAML inspection.

| Behavior | Evidence | Observation |
|---|---|---|
| F-15 turning | `live-f15-turn-1.png`, `live-f15-turn-2.png` | Opposed headings show stable scale, changing geometry, contrails, and aligned shadow. |
| F-15 attack/rearm | `live-f15-paused-attack.png`, `live-f15-direct-rearm-telemetry.json`, `live-f15-rearmed-base.png` | Cannon ammunition fell from 12 to 0; a direct follow-up order entered `ReturnToBase`; pools refilled to 16 on the helipad. |
| F-15 destruction | `live-f15-destruction.png` | Airborne destruction produced the dedicated dark aircraft husk and explosion presentation. |
| AH-64 movement/attack/rearm | `live-ah64-moving-east.png`, `live-ah64-paused-attack.png`, `live-ah64-attack-telemetry.json`, `drive-live-air-ah64-result.json` | Rotor and aircraft stay separated in flight; ammunition fell from 30 to 26 during close support, the destroyed target is rendered burning, and the pool returned to 30 at base. |
| Samad loiter/turn | `live-samad-moving-east.png`, `live-samad-turn.png` | The actor maintains its shadow and scale through a complete heading change. |
| Samad terminal strike | `live-samad-dive-1.png`, `live-samad-dive-2.png`, `live-samad2-00.png` through `live-samad2-12.png` | Repeated live actors entered `DiveAttack`, closed from cell 91 to 95, reduced the target MCV by about 25.7 percentage points each, then disappeared without a return activity. |
| AI production | `live-saudi-air-production.png`, replay `live-support/Replays/ra/{DEV_VERSION}/ra-2026-08-11T185332Z.orarep` | A normal Saudi AI issued F-15SA production orders (including ticks 4054 and 5328), independent of the direct-control test harness. |

## Remaining subjective concerns

- The F-15's twin tails necessarily compress at due-north and due-south headings
  at native Red Alert scale. They remain readable in motion, but this is the
  weakest silhouette pair.
- The Samad intentionally changes apparent aspect between the loiter and steep
  dive meshes. The pivot stays fixed, but the transition is conspicuous and is
  worth reassessing after broader player feedback.
- Fast-advance live capture skipped the brief Samad impact-flash frame, so the
  screenshots prove the rendered dive and disappearance while observation
  telemetry proves target damage. The transient impact sprite itself is covered
  by the frame tests and OpenRA missing-sprite validation, not a frozen live frame.
- Costs, AI weights, damage, reloads, and counter relationships are internally
  differentiated and passed functional tests, but competitive balance remains a
  playtest judgment rather than a mechanically provable result.
