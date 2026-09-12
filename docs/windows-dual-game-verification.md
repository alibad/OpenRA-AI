# Windows dual-game launch and packaging

Development has one user launch path: `C:\Users\Admin\Code\hq\games\OpenRA\launch-game.cmd`.
The product wrapper delegates to that canonical sibling checkout. Installed packages use
their own self-contained engine and companion executables; Python and .NET installation
are development prerequisites, not player prerequisites.

## First-run contract

- Both World War III (`ra`) and integrated Red Alert 2 (`ra2`) ship in the same package.
- Source launches prepare a fingerprinted, data-only RA2 overlay without replacing the
  canonical shared RA2/fusion assembly. Both modes retain the same AI companion.
- Classic content installs through the supported quick-install path. RA2 checks registered
  Steam libraries (including secondary drives) and imports an owned installation safely.
  It never bundles commercial RA2 archives. If no owned installation exists, the game
  explains the prerequisite; ownership/purchase cannot be supplied by our package.
- Default Windows packaging includes the checksum-pinned local model/runtime payload.
  `-ExcludeLocalAI` is an explicit smaller, external-provider/separate-pack build option.
- NSIS setup uses an adjacent, verified AI-pack ZIP automatically (or its release URL),
  avoiding NSIS's data-block size limit. Distribute the setup EXE and matching AI-pack ZIP
  together for offline setup. The portable ZIP already contains the complete payload.
- Local AI selects free loopback ports and starts its own gateway. An unrelated service
  on port 4000 is not reused or stopped. Explicit custom-provider choices remain supported.
- New packages are staged under a distinct version; existing stages are preserved.

## Local evidence — 2026-09-12

- Canonical engine build: zero warnings/errors; engine tests: 543 passed, 2 skipped.
- Full companion suite: 248 passed, 3 skipped, 71 passing subtests. One skip is the
  Windows symlink-creation privilege; no security settings were changed to enable it.
- RA2 YAML/map validation: exit 0, 793 warnings (not a warning-free content baseline).
- Native computer use: switched both modes in the menu, played a Turkey RA2 skirmish
  and a China classic-based skirmish. AUTO deployed, built economy/production, recruited
  units and fought. A subsequent China RA2 match also showed the active AI HUD and base.
- Live local-model explanation returned in 2.9 seconds without creating orders.
- Local text-and-speech diagnostic passed: text ~0.4 seconds, speech ~5.1 seconds.
- Local speech-to-transcription round trip reproduced the sentence exactly (~0.9-second
  transcription), without microphone recording.
- The full 2.04 GB portable `0.1.0-windows-dual.3` package built with self-contained .NET
  10.0.11, frozen Python services and local models. Its own companion imported Steam RA2
  into an empty support directory, downloaded classic content, and passed text/speech
  diagnostics. Native UI reached the RA2 first-run flow; telemetry consent was left
  unsubmitted. No fresh-machine privacy preferences were changed.
- Closing the canonical game shut down its companion, gateway, chat and whisper services.
- NSIS setup built successfully (240,509,979 bytes), with a checksum-verified adjacent
  model ZIP (1,761,038,160 bytes). Regression tests cover installation from a local ZIP
  with spaces in its path and refusal of a mismatched digest without damaging an install.
- Windows currently chooses the lightweight CPU profile: text plus speech; visual-model
  inference and microphone capture are not claimed as tested.

Local development packages are unsigned and are not published releases. A signed
installer and clean-machine installation remain separate release acceptance checks.
