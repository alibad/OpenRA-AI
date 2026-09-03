# Integrated RA2 Mac preview — 2026-09-03

This is a **local playable preview**, not an official public release or the
complete requested RA2/custom-faction experience.

## Installed build

- Application: `/Applications/OpenRA AI RA2 Preview.app`
- In-game version: `0.1.0-alpha.18-ra2-preview.5`
- Product snapshot: `d87bf56995b7183a1af9f12b4566933c417a119a`
- Engine: `c84262d9b2ab82da8a1d12a146c6dbc7b72e2922`
- OpenRA RA2 source: `61e24e3c1d7b586aa55a86096d29e1559aa9b994`
- Artifact: `artifacts/releases/OpenRA-AI-0.1.0-alpha.18-ra2-preview.5-macos-arm64.dmg`
- SHA-256: `677b25561f883d310d77eb005c6eaf7e9173f870e31a55f29764b8ad9cf57f1d`
- Signer: `Developer ID Application: HUMAN QUEST LLC (75E8FZ9444)`
- Apple notarization: **Accepted**, submission
  `ab23bb4f-cd1c-43c8-a26c-dbbf1c074330`.
- DMG checksum, deep/strict app signature, stapled DMG ticket and installed-app
  ticket validated. Gatekeeper accepted the installed copy as
  `Notarized Developer ID`. The app was copied from this exact read-only DMG.

The existing OpenRA AI, alpha.17 and standalone Red Alert 2 Preview apps were
not replaced. Owned RA2 game archives remain outside the application bundle.
The broken preview.3 install was moved, not deleted, to
`artifacts/ra2-integrated/superseded-installed-preview.3.app` before replacement.
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

- 515 engine tests passed; two pre-existing skips. 199 companion tests passed.
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
- Normal no-argument launch from Applications and the signed package passed.
  The launcher waits for companion readiness before starting the game and
  cleans up the game, companion and model runtime on exit.
- After an extended menu wait, preview.5 received its first companion snapshot
  1.453 seconds after the live bridge began listening, at tick 20. AUTO was
  already enabled; the two-second screenshot shows the deployed Construction
  Yard and power production underway. Earlier runs reached power/refinery
  construction. The local bridge backoff is capped at one second.
- In-process game switching preserved the companion and showed the original
  World War III factions. The final build changes RA2's misleading zero-packs
  start message to distinguish native countries/shared AI from custom packs.
- The final frozen companion successfully started its bundled game-tool
  service (28 tools). A live question correctly identified Iraq and its
  Construction Yard in 3578 ms, with `mcp.connected` and `battlefield_read`
  both true, matching the independently read bridge state. Compact live
  context is fetched explicitly and uses RA2 actor names. Bundled local
  profiles provide 8192 context tokens for the tool instructions.
- Local Whisper readiness and bundled microphone-device availability passed.
- Ctrl+Shift+A switched AUTO off; Ctrl+Shift+M muted voice in the game. Original
  AUTO-on/voice-on preferences were restored after testing.
- Exiting the controlled test games cleaned up their game/companion processes.

Evidence is retained under `artifacts/ra2-integrated/`. Preview.1 was rejected
during testing because of the GI crash. Preview.2 was superseded by UI/intent
corrections. Preview.3 exposed a normal-launch Bash error and missing frozen
game-tool dispatch; both were fixed and regression-tested in preview.4.
Preview.5 adds grounded local prompts, adequate context and prompt bridge
reconnection. Only preview.5 is the current installed integrated preview.

## Still incomplete / release blockers

- Custom modern faction/ability ports to RA2 need actual roster/art/ability
  adaptation; selecting RA2 does not enable the World War III packs.
- End-to-end voice capture is not verified. Superwhisper appears to intercept
  the default Ask binding on this Mac. No Superwhisper settings were changed;
  permission to remap only OpenRA to Option+Shift+Space was requested.
- Accept/reject shortcuts and unmuting were not fully verified end to end.
- A Soviet AUTO run stayed active through tick 6240 but did not produce a
  Conscript within 260 seconds. Early production pacing needs tuning.
- Natural-language orders are not yet consistently reliable: a power-plant
  request previously proposed placement before production and was safely
  rejected; a later small-model request produced repetitive malformed output
  and no accepted action. Correct grounded answers do not prove arbitrary
  spoken/text commands are release-ready. Native AUTO is a separate system.
- No Windows RA2 artifact was built, signed or validated. No public release,
  download upload, website deployment or GitHub Actions change was made.

Do not promote this preview as a complete or official cross-platform release.
