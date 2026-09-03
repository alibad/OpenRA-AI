# Integrated RA2 Mac preview — 2026-09-03

This is a **local playable preview**, not an official public release or the
complete requested RA2/custom-faction experience.

## Installed build

- Application: `/Applications/OpenRA AI RA2 Preview.app`
- In-game version: `0.1.0-alpha.18-ra2-preview.3`
- Product snapshot: `6e07985d2c5e6323bc8b441494ae3862875bfdbb`
- Engine: `c84262d9b2ab82da8a1d12a146c6dbc7b72e2922`
- OpenRA RA2 source: `61e24e3c1d7b586aa55a86096d29e1559aa9b994`
- Artifact: `artifacts/releases/OpenRA-AI-0.1.0-alpha.18-ra2-preview.3-macos-arm64.dmg`
- SHA-256: `efe41003c9375a88c268b736567c7c4f0e211dfb49bf03585b53927cde5a507b`
- Signer: `Developer ID Application: HUMAN QUEST LLC (75E8FZ9444)`
- Apple notarization: **Accepted**, submission
  `651fc5ed-41a4-4dd7-8b26-fac21adb8757`.
- DMG checksum, deep/strict app signature, stapled DMG ticket and installed-app
  ticket validated. Gatekeeper accepted the installed copy as
  `Notarized Developer ID`. The app was copied from this exact read-only DMG.

The existing OpenRA AI, alpha.17 and standalone Red Alert 2 Preview apps were
not replaced. Owned RA2 game archives remain outside the application bundle.
Finder's bundle metadata still reports `0.1.0`; the full preview identifier is
shown in-game and recorded in `Resources/VERSION` and `RA2-BUILD.json`.

## Included

- RA2 skirmishes with nine native countries, isometric terrain and owned artwork.
- Shared native assistant/model settings, local AI library, AUTO and AI HUD.
- A remembered World War III / Red Alert 2 selector.
- The visible configured Ask shortcut; macOS default is Option+Space.
- Existing five modern factions and 31 capabilities remain in World War III.
  They have not been ported to RA2. Original campaigns and Yuri's Revenge are
  not included.

## Verification

- 515 engine tests passed; two pre-existing skips. 192 companion tests passed.
- Shell syntax, whitespace and diff checks passed.
- All 27 playable RA2 maps passed startup/AUTO deployment after the GI crash
  correction. The final signed package additionally passed Heartland,
  Golden State Freeway and Heck Freezes Over startup checks.
- Two longer Allied runs produced GIs, accepted native deploy orders and
  changed their observed weapon range from 4096 to 5120 (4 to 5 cells), at
  ticks 4730 and 6680. This exercises the multiple-attack-mode crash fix.
- A manual isometric MCV move from storage cell (60,179) reached exactly
  (62,181), with an accepted bridge receipt and arrival at tick 130.
- Final packaged RA2 rules/maps validation passed with 793 upstream warnings.
  The previous integrated package's World War III rules validation passed with
  11,543 warnings. Native engine builds had no compiler warnings; the bundled
  Whisper build emitted upstream C++ deprecation warnings.
- Live packaged launches waited for companion readiness and showed AUTO active
  in a fresh match, deploying the MCV and constructing power/refinery buildings.
- In-process game switching preserved the companion and showed the original
  World War III factions. The final build changes RA2's misleading zero-packs
  start message to distinguish native countries/shared AI from custom packs.
- A live local-model buildings question was answered correctly in 782 ms.
- Local Whisper readiness and bundled microphone-device availability passed.
- Ctrl+Shift+A switched AUTO off; Ctrl+Shift+M muted voice in the game. Original
  AUTO-on/voice-on preferences were restored after testing.
- Exiting the controlled test games cleaned up their game/companion processes.

Evidence is retained under `artifacts/ra2-integrated/`. The first signed build
was not installed because live play found the GI crash. The second was
superseded by the final UI/intent corrections. Pre-sign attempts to execute
self-contained binaries were killed by macOS; all three checks passed after
signing. None of these earlier builds is the installed preview.

## Still incomplete / release blockers

- Custom modern faction/ability ports to RA2 need actual roster/art/ability
  adaptation; selecting RA2 does not enable the World War III packs.
- End-to-end voice capture is not verified. Superwhisper appears to intercept
  the default Ask binding on this Mac. No Superwhisper settings were changed;
  permission to remap only OpenRA to Option+Shift+Space was requested.
- Accept/reject shortcuts and unmuting were not fully verified end to end.
- A Soviet AUTO run stayed active through tick 6240 but did not produce a
  Conscript within 260 seconds. Early production pacing needs tuning.
- The frozen companion cannot currently launch its `game_mcp` module through
  its Python-style subprocess entry point. Text/vision fallback works, but full
  tool-backed assistant operation remains a release blocker.
- Natural-language orders are not yet consistently reliable: a power-plant
  request proposed placement before production and was safely rejected.
  The final model also confused the map name with the country in a country
  question. Fixing intent routing did not by itself fix answer accuracy.
- No Windows RA2 artifact was built, signed or validated. No public release,
  download upload, website deployment or GitHub Actions change was made.

Do not promote this preview as a complete or official cross-platform release.
