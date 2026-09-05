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

| Country | Combat/support roster | Gameplay identity |
| --- | --- | --- |
| China | 17 units + 3 defenses | Networked formations, deployable missile teams, amphibious armor, airlift and carrier wings. |
| Iran | 14 units + 3 defenses | Ambush infantry, stationary artillery, drone guidance and mobile coastal denial. |
| Turkey | 16 units + 3 defenses | Mechanized infantry, target designation, mobile screening and naval escorts. |

These are asymmetric armies, not identical rosters with different flags.
Construction, economy and utility buildings use the native Allied/Soviet trees.
Combat units have country-specific prerequisites and replace the corresponding
stock options only for that country. Original countries keep their unit stats.

## China — networked combined arms

- Barracks: Rifleman, Portable Missile Team, Network Technician and the
  one-at-a-time Red Spear commando.
- War Factory: Qilin tank, Lynx command scout, Mantis AA, Sea Dragon amphibious
  carrier, Longbow rocket artillery, Cloud recon drone and Crane airlift.
- Airfield: Skyspear interceptor, with limited ammunition and native rearming.
- Naval Yard: Luyang ASW destroyer, Haiying missile corvette, Haiwang drone
  carrier, Kunlun landing ship and Jiaolong submarine.
- Defenses: Bastion anti-infantry turret, Skyshield AA and Spectrum radar/
  network tower. Spectrum is unarmed and loses its powered functions when
  the base is short of electricity.

Keep Qilin armor near a Lynx or deployed technician: the network shortens reloads
by 15%, without stacking duplicate networks. Deploy the portable missile team
to switch between AT and AA; moving technicians retracts their relay.
Fragile support units give opponents a concrete target. Longbow artillery has
a minimum range; tanks and infantry must protect it from close attackers.
Sea Dragon carries four infantry, Crane six, and Kunlun up to 16 cargo weight.
Carrier aircraft are attached wing units, not extra build-menu entries.

## Iran — layered denial

- Barracks: Basij rifleman, Toophan AT ambusher, Drone Coordinator and the
  one-at-a-time Shadow One infiltrator.
- War Factory: Karrar tank, Raad AA, Fajr rocket artillery, Coastal Missile
  Launcher, Mohajer reconnaissance drone, Toufan gunship, Azar strike aircraft
  and expendable Loiter Munition.
- Naval Yard: Peykaap missile craft and Ghadir concealed submarine; the native
  Soviet amphibious transport remains available.
- Defenses: Gun Bunker, Raad AA Site and Coastal Denial Battery.

Stationary launchers and ambushers gain their emplacement bonuses, so flanking
and forcing them to relocate are useful counters. The coordinator improves
nearby compatible drones, not the entire army. A loiter munition is consumed
after its attack; it cannot be reused as a cheap permanent aircraft.
Peykaap carries a separate AA weapon; Ghadir supplies submerged attack.
The native Flak Track is retained as an infantry transport.

Iran has no invented Soviet airfield: its aircraft use the War Factory,
cooldowns and native repair facilities. They do not claim an Allied-style
ammunition/rearm cycle. Coastal weapons cannot replace a general-purpose
ground army; their target restrictions and minimum ranges are deliberate.

## Experiences and AI

The default modern experience enables all three country packs and
**Combined-arms AI**. **Original Armies, Smarter Bots** enables the same AI for
the original nine countries; **Original Countries** retains upstream tuning.
Custom selections stay saved and are not silently enrolled in new options.

Combined-arms AI chooses production by missing battlefield role, respects
tech/cost/unit limits, and gives rush, defensive and naval bots different
priorities. Role weights are normalized within each production queue so a
growing infantry/naval force cannot indefinitely crowd factory-built aircraft
out of production. Its formation-size setting is 3–20 units (default 8). This changes
bot production and squad assembly, not human controls or unit health/damage.
It is not omniscient counter-picking. Tactical deployment and sophisticated
multi-transport assaults are not promised as automated micro.
Original-country specialists retain positive recruitment roles. Snipers,
desolators, bomb specialists and mind-control infantry have small bot-only
caps as conservative preview tuning; human unit statistics and limits stay
unchanged. Roles describe actual weapons, not assumptions based on unit names.

Faction packs compose their air/naval/defense registrations without overwriting
one another. Experience dependencies load before their consumers; disabling a
module removes its effects without deleting saved parameter choices. The UI
separates gameplay modules from authoring contracts that provide tools or
extension definitions rather than standalone match behavior.

## Turkey — full combat roster

Select **Modern Factions → Skirmish → Turkey**. Medium starting forces include
Turkish riflemen, an AT specialist and a Bozkir tank. Existing MCV-only choices
stay MCV-only; choose Medium explicitly if you want troops immediately.

| Production | Turkey units | Technology |
| --- | --- | --- |
| Barracks | Mechanized Rifleman; Portable AT Specialist | Barracks |
| Barracks | Forward Drone Operator; Grey Wolf | Radar; Battle Lab respectively |
| War Factory | Bozkir tank; Aras-8 carrier; Gokkalkan mobile AA; Sancak screening vehicle | War Factory |
| War Factory | Yildirim howitzer | Radar |
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
testing remain future work. Voice setup is unchanged;
this faction work does not resolve the previously documented macOS microphone
shortcut interception or free-form local-model reliability limitations.

## Implementation and verification

Maintained overlay: `apps/installer/ra2/modern-factions/`. Packaging copies it
onto the pinned RA2 source through `scripts/prepare-ra2.py`. Gameplay files load
only with the relevant pack/dependency. Model declarations are manifest-level
and unused models do not enable disabled countries. The modern preset also
raises native bot production/technology priorities; the original-country preset
retains upstream bot tuning.

- `scripts/build-ra2-faction-art.py`: 58 native models (35 bodies, 20 turrets,
  three animated rotors), HVA transforms, custom palettes, 56 icons, three
  full-roster previews and 21 animated infantry/defense SHPs.
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
- `scripts/validate-ra2-china.py`: complete production, three cargo round-trips,
  six water movers, native combat, carrier wing, network and deployable roles.
- `scripts/validate-ra2-iran.py`: complete production, water movement, native
  combat, drone guidance, stationary bonuses and expendable loiter attacks.
- `scripts/validate-ra2-experiences.py`: all 16 combinations of the three packs
  and doctrine AI, original-country preservation and isolated native map lint.
- `scripts/validate-ra2-ai-composition.py`: native AUTO recruitment of six
  battlefield roles from an empty army, with no manual recruitment. This uses
  prebuilt full technology, fast build, a fixed 50,000-credit budget and no base
  expansion; it complements rather than replaces normal-economy start tests.

Evidence and release/install results are recorded in the dated todo changelog
and local `artifacts/ra2-modern/` directory. All tests use disposable profiles.
Owned RA2 game data remains outside the application and release payload.

Installed Mac build at the start of this work: **0.1.0-alpha.18-ra2-preview.7**,
**OpenRA AI RA2 Preview**. It does not contain the expanded Turkey roster.
Build/install/signature status is recorded in `todo/2026-09-03.md`; source
changes alone do not update the installed app or public website/Windows release.
