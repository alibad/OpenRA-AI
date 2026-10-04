# Israel and Hezbollah — local faction packs

The owner requested both factions on 4 October 2026. RA2 is implemented in the
canonical `RTSAI-Mod` checkout; Classic loads the packs in the World War III
experience in the canonical `OpenRA` checkout. All work is local. Public release
coverage, deployment, final art approval and broad balance are separate gates.

## Roster scope — measured

| New authored entries per mode | Israel | Hezbollah |
|---|---:|---:|
| Infantry | 4 | 4 |
| Vehicles | 4 | 4 |
| Aircraft | 2 | 1 |
| Naval | 3 | 3 |
| Defenses | 3 | 3 |
| Support buildings | 2 | 2 |
| Total | 18 | 17 |

Economy, construction, production, technology and superweapon trees retain
appropriate shared buildings. Classic also has an Israel fixed-wing airfield.
The shared catalog names both factions and all 35 new entries; Studio and the
website include the full rule-derived rosters, including shared actors.

## Gameplay direction — inferred

Israel emphasizes protected armor, observers and finite-ammunition aircraft.
Powered coordination relays support eligible infantry and vehicles; field service
stations restore eligible damaged vehicles. Expensive formations depend on
vulnerable support buildings and power.

Hezbollah emphasizes fragile mobile vehicles, stationary concealment, guided
fire and deployable sensors. Signal posts support eligible guided units and field
workshops repair vehicles. Detection, close attacks and destruction of support
nodes are intended counters. These are fictional game abstractions, not claims
about real-world capability. The two modes have separate inherited mechanics and
descriptions; do not assume numerical parity.

## Verification — measured

`RTSAI-Art/rebuild/levant-native-evidence.json` records four passing native suites
and 50 passing assertions against clean commits `fce87fdd10ee` (RA2) and
`af0ad5794eac` (Classic). They cover all 35 new actor instantiations in each
mode, actual queues for infantry/vehicle/air production, faction prerequisites,
eligible-only repair, loss of repair on power failure, stationary concealment,
movement revealing infantry, legal anti-air targets, falling aircraft husks and
movement of all six new ships. Classic skiff movement supplies its accepted
external radio-link condition; RA2 uses the faction's native shipyard relay.

Both native YAML validators pass. Classic retains two pre-existing feedback
localization warnings. The local website passes typecheck, build, lint and its
tests, including both faction dossiers in both modes and browser policy presets.

The local website E2E check also completed two native armor-policy trials and
eight native air-defense trials, with browser comparisons and placement/combat
of both new vehicles in the map Workshop. Classic defense metadata now uses
the reusable building defense roles. These are encounter smoke checks.

Two RA2 `levant-smoke` bot matches completed without crashes, with both spawn
orientations and production of each new faction's roster. Both reached the
15,000-tick limit (10 minutes of normal game time). This is production/combat
smoke evidence, **not a balance certificate**. Reports remain in the local
`.codex-qa/levant-bots` directory.

Repeat the native regression scenarios without companion/model autostart:

```powershell
python OpenRA-AI/scripts/verify-levant-native.py --mode ra2 --output .codex-qa/levant-rerun
python OpenRA-AI/scripts/verify-levant-native.py --mode ra --output .codex-qa/levant-rerun
python OpenRA-AI/scripts/verify-levant-native.py --mode ra2 --naval --output .codex-qa/levant-rerun
python OpenRA-AI/scripts/verify-levant-native.py --mode ra --naval --output .codex-qa/levant-rerun
```

Use a fresh output directory for a new run. Fixtures link installed local content;
they do not copy or return original game images. The script disables companion
autostart explicitly and records whether mod files are dirty. Policy evaluations
are available through the website's local numerical runner on port 3462.

## Art and remaining gates

**Measured:** all new assets are CPU-authored geometry and animation, with no
EA-image inputs or model calls. RA2 uses VXL/HVA for moving vehicles, full SHP
infantry animations and construction/damage sequences for structures. Classic
uses separately projected sprites, including nonuniform 32-facing ground/naval
angles, 16-facing aircraft, turret layers and sinking animations. Infantry sheets
contain 713 frames; defense/support sheets contain 42. Provenance and hashes are
in the mod's `modern-factions/levant-art-provenance.json`. Larger source renders
live in `RTSAI-Art/rebuild/levant-media`, with fingerprinted website copies.

**Inferred/open:** native visual quality, encounter coverage beyond these
regressions, whole-faction balance, premium art polish and owner acceptance are
not complete. Source renders are labeled as source evidence; they do not prove
native appearance. No owner gate was approved automatically. New voxel units
retain the existing faction lighting/scale; the earlier lighting approval was
Qilin-only. No pushes, releases, deployment or paid generation occurred.

The local authoring order is rules (`build-levant-factions.py`), art
(`build-levant-art.py`), flags (`build-levant-flags.py`), validation and game
commits, catalog (`catalog-levant-factions.py`), Studio dependency/roster export,
then website media/content sync. Refresh snapshots whenever game commits change.
