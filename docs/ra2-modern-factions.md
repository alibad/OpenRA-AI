# RA2 modern factions — playable prototype

China, Iran and Turkey are independent RA2 experience packs. They use original
project voxel models and new illustrated portraits, not the World War III
sprite camera or a reskinned vanilla tank icon. All nine original RA2 countries
remain selectable.

Fresh profiles use **Red Alert 2 — Modern Factions**. Existing saved/custom
experience choices are preserved; choose **Change Experience → Modern Factions**
to enable the new packs. The **Original Countries** preset disables all three.
The modern preset starts with the native medium-force class so a signature tank
is visible immediately. MCV-only, light and heavy starts remain selectable.

| Country | Four signature units | Prototype mechanic |
| --- | --- | --- |
| China | Qilin, Lynx, Mantis, Cloud | Lynx gives nearby Chinese units 15% shorter reloads; overlapping networks do not stack. |
| Iran | Karrar, Raad, Fajr, Mohajer | Layered AA/artillery; Fajr has a four-rocket salvo, minimum range and 20% shorter reload while stationary. |
| Turkey | Bozkir, Yildirim, Sancak, Kuzgun | Sancak detects cloak and reduces incoming damage to nearby Turkish units by 15%; screens do not stack. |

China and Turkey use the complete Allied economy, infantry, technology and
naval tree. Iran uses the Soviet equivalents. Their four units are faction-gated
and built through the native war factory; reconnaissance drones also require
radar. Drones use light ground-attack missiles with a cooldown rather than a new
ammunition/rearming system. Native repair depots service landed drones.

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

- `scripts/build-ra2-faction-art.py`: reproducible 21 native models (12 bodies,
  nine turrets), HVA transforms, custom palette, 12 icons and three previews.
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

Evidence and release/install results are recorded in the dated todo changelog
and local `artifacts/ra2-modern/` directory. All tests use disposable profiles.
Owned RA2 game data remains outside the application and release payload.
