# RA2 modern factions — playable preview

China, Iran and Turkey are independent RA2 experience packs. They use original
project voxel models, native infantry/defense sprites and original portraits,
not the World War III sprite camera or a reskinned vanilla tank icon. All nine original RA2 countries
remain selectable.

Fresh profiles use **Red Alert 2 — Modern Factions**. Existing saved/custom
experience choices are preserved; choose **Change Experience → Modern Factions**
to enable the new packs. The **Original Countries** preset disables all three.
The modern preset starts with the native medium-force class so a signature tank
is visible immediately. MCV-only, light and heavy starts remain selectable.
Saved skirmish options also persist: if a previous game used MCV-only, change
**Starting units → Medium** in the lobby to get the signature tank immediately.

| Country | Signature roster | Preview mechanic |
| --- | --- | --- |
| China | Qilin, Lynx, Mantis, Cloud | Lynx gives nearby Chinese units 15% shorter reloads; overlapping networks do not stack. |
| Iran | Karrar, Raad, Fajr, Mohajer | Layered AA/artillery; Fajr has a four-rocket salvo, minimum range and 20% shorter reload while stationary. |
| Turkey | 16 units and three defenses; full list below | Mechanized infantry, target designation, mobile screening and combined land/air/naval forces. |

China uses the complete Allied economy, infantry, technology and naval tree.
Iran uses the Soviet equivalents. Their four units are faction-gated
and built through the native war factory; reconnaissance drones also require
radar. Drones use light ground-attack missiles with a cooldown rather than a new
ammunition/rearming system. Native repair depots service landed drones.

## Turkey — full combat roster

Select **Modern Factions → Skirmish → Turkey**. Medium starting forces include
Turkish riflemen, an AT specialist and a Bozkir tank. Existing MCV-only choices
stay MCV-only; choose Medium explicitly if you want troops immediately.

| Production | Turkey units | Technology |
| --- | --- | --- |
| Barracks | Mechanized Rifleman; Portable AT Specialist | Barracks |
| Barracks | Forward Drone Operator; Grey Wolf | Radar; Battle Lab respectively |
| War Factory | Bozkir tank; Aras-8 carrier; Yildirim howitzer; Gokkalkan mobile AA; Sancak screening vehicle | War Factory |
| War Factory | Deniz Kaplan amphibious carrier; Kuzgun-M drone; Turna-AH gunship | Radar for carrier/drone; Battle Lab for gunship |
| Airfield | Sahin-X interceptor | Airfield and Battle Lab; four missiles, native return-to-base rearming |
| Naval Yard | Poyraz patrol boat; Ege missile corvette; Marmara frigate | Yard; radar for Ege; Battle Lab for Marmara |
| Defenses tab | Hisar sentry; Siper AA battery; Boran AT emplacement | Barracks for Hisar; radar for Siper/Boran; power required |

- Aras and Deniz carry five infantry and improve nearby Turkish infantry's
  firepower by 15% and movement speed by 10%. Deniz crosses water and unloads
  on land/coasts. Overlapping copies do not stack these bonuses.
- The drone operator spots cloaked enemies and marks ground/water targets for
  20% increased incoming damage. Grey Wolf is a one-at-a-time command infantry
  unit: cloak while stationary, long-range rifle, 10% shorter nearby infantry
  reloads. He is not a demolition commando.
- Sancak retains its 15% nearby damage reduction. Keep the lightly armored
  support vehicles close to their formation. Howitzers and AT emplacements
  have minimum ranges; mobile AA and the interceptor cannot shoot ground units.
- Ege can attack submarines; Marmara combines long-range naval guns with AA.
  Ships retain native naval movement/repair and require a water-accessible yard.
- Shared Allied construction/economy/technology buildings, MCV, miner,
  engineer, dog, spy and landing craft remain available. **This is a complete
  Turkish combat roster, not a newly illustrated economy-building set.** Stock
  Allied combat substitutes are removed only for Turkey; other countries keep
  their existing unit choices.
- All five native bot profiles know the new recruitment/defense/air/naval
  roles. Manual transport loading works; sophisticated AI transport assaults
  and competitive balance are not validated.

Infantry use original eight-facing animated SHPs; defenses have separate
32-facing turrets, build animations and ownership colors. Aircraft/vehicles/
ships use native RA2 voxels, including an animated gunship rotor. The original
Turkey mesh designs and Turkish/English voice performances are reused, while
projection, palette, depth and sizing are adapted to RA2. The faction preview
shows all 19 entries rather than four tanks.

This is a focused RA2 adaptation, **not a claim that every World War III unit,
faction, special ability or mission has been ported**. Campaigns and Yuri's
Revenge are not included. Competitive balance and long-session multiplayer
testing remain future work. The shared AI/voice implementation is unchanged;
this faction work does not resolve the previously documented macOS microphone
shortcut interception or free-form local-model reliability limitations.

## Implementation and verification

Maintained overlay: `apps/installer/ra2/modern-factions/`. Packaging copies it
onto the pinned RA2 source through `scripts/prepare-ra2.py`. Gameplay files load
only with the relevant pack/dependency. Model declarations are manifest-level
and unused models do not enable disabled countries. The modern preset also
raises native bot production/technology priorities; the original-country preset
retains upstream bot tuning.

- `scripts/build-ra2-faction-art.py`: reproducible 36 native models (20 bodies,
  15 turrets, one animated rotor), HVA transforms, custom palettes, 27 icons,
  three previews and seven animated Turkey SHPs.
- `test_ra2_modern_factions.py`: independent VXL span decoding, SHA-256 evidence,
  native normal/remap indices, bounds, transforms, deterministic regeneration,
  every unit's team-color coverage, exact icon dimensions and country contracts.
- `scripts/validate-ra2-faction-art.py`: genuine GPU-rendered game captures with
  stock Grizzly/Rhino/IFV/GI scale references. Never substitutes telemetry art.
- `scripts/validate-ra2-rosters.py`: native faction-gated production, foreign
  unit exclusion, attack-role metadata and exact-cell movement, using a private
  prebuilt economy and fast-build to bound smoke-test duration. No all-tech cheat.
- `scripts/validate-ra2.py --faction COUNTRY --require-unit ACTOR`: normal-speed
  AUTO from MCV-only starts; starting units cannot falsely satisfy production.
- `test_ra2_turkey.py`: full-roster contracts, native SHP frame decoding,
  reproducibility, team remap, borders/depth, inherited effects and bot coverage.
- `scripts/validate-ra2-turkey.py`: all 19 native production entries, faction
  gates, cargo round-trip and amphibious/naval water movement. `--visual` uses
  actual GPU captures, with infantry/armor/navy review scenes.
- `scripts/validate-ra2-turkey-combat.py`: isolated attack range with an inert
  opponent, paired targets, native weapons and a marked/control damage test.

Evidence and release/install results are recorded in the dated todo changelog
and local `artifacts/ra2-modern/` directory. All tests use disposable profiles.
Owned RA2 game data remains outside the application and release payload.

Installed Mac build at the start of this work: **0.1.0-alpha.18-ra2-preview.7**,
**OpenRA AI RA2 Preview**. It does not contain the expanded Turkey roster.
Build/install/signature status is recorded in `todo/2026-09-03.md`; source
changes alone do not update the installed app or public website/Windows release.
