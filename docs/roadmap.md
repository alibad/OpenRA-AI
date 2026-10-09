# RTS AI delivery roadmap

Owner direction: 9 October 2026. Two ways to play one standalone game: **Web RTS** and **Downloadable RTS**. Windows first; macOS is built and checked later on the owner's Mac. Neither mode requires owning Red Alert or Red Alert 2. Keep custom resources and earlier work recoverable.

The full earlier roadmap is preserved in `roadmap-before-consolidation-20261009.md`. This is the current delivery view; unfinished historical research and review gates remain open.

## Downloadable RTS — RTSAI-Mod main

- [x] Consolidate standalone and reviewed art work into the canonical checkout.
- [x] One game entry with a working in-game **Game modes** dialog.
- [x] RA2/isometric profile (`rtsai`).
- [x] Classic/rectangular profile (`rtsai-topdown`) with original square terrain and maps.
- [x] Both profiles share modern army rules, authored faction assets and companion contracts.
- [x] Restore nine historical country rule sets alongside seven modern factions: 16 choices total.
- [x] Six campaign maps with native objectives, civilian convoys, enemy waves and difficulty.
- [x] Validate both profiles with empty owned-content folders and strict standalone checks.
- [x] Bundle local companion, catalog and inference runtimes. Models are optional downloads, not embedded.
- [x] Windows per-user EXE installer and portable ZIP with checksums (`0.4.0-alpha.2`), including the canonical campaign and Classic rendering fixes.
- [ ] Clean-machine acceptance outside the development machine.
- [ ] Independently play through all mission outcomes and broader roster/balance combinations.
- [ ] Port additional historical Classic mechanics, maps and presentation retained in the older fork. This Classic profile presents shared standalone army rules on a rectangular grid; it does not reproduce every old Classic feature.
- [ ] Integrate the complete browser workshop, coaching and call experience into the downloadable suite and verify parity.
- [ ] Native-speaker review of outstanding voice sheet entries.
- [x] Public Windows release `v0.4.0-alpha.2`; verified installer and portable payload. Website delivery at https://rtsai.net/download.
- [x] Anonymous release download, real website button, SHA-256, installation, shortcut, mode switch, installed skirmishes in both profiles and uninstall checks.
- [ ] Optional code signing: no certificate/configuration selected; alpha.2 is explicitly unsigned. No certificate was purchased.
- [ ] macOS package and acceptance on the owner's Mac.

One launch path: `RTSAI-Mod/launch-game.cmd`; choose the mode in **Game modes**. Packages have the same choice in `RTSAI.exe`.

Release trailer: the completed 42-second current release cut uses actual gameplay, native mode acceptance stills and the original project soundtrack. Historical story film/reels remain preserved. Rebuild and provenance: `RTSAI-Film/RELEASE-20261009.md`. No Windows system narration is used. The Windows alpha.2 installer passed fresh installation, configuration, shortcut, rendered mode switching, both bot skirmishes and uninstallation on the owner's PC; it is then reinstalled at `%LOCALAPPDATA%/Programs/RTS AI`. All 6,398 portable payload hashes match. This is host acceptance, not a fresh Windows OS result.

## Web RTS — RTSAI-WebGame main

- [x] Browser-hosted OpenRA simulation using project-owned public content.
- [x] 16 country choices and six campaigns.
- [x] Native production, contextual commands, stances, support powers and rally/primary controls.
- [x] Local saves, read-only replay, deterministic restore and persistent settings.
- [x] Existing private-room lockstep multiplayer, room chat and read-only spectators; this option uses a room service.
- [x] Local AI strategy selection, proposal annotations, sampled replay coaching, repeatable combat drills, tactical bot personalities and editable scenario workshop.
- [x] Direct WebRTC multiplayer, peer chat and video/audio without a room service: two independent browsers, 200 matching frames and human deploy orders, tested against the static bundle.
- [ ] Classic presentation in the browser bundle, with both mode choices verified.
- [x] Fully static public bundle with a local preview tool; direct games make zero room API requests. Static hosting must preserve the supplied compression and isolation headers.
- [ ] Cross-network WebRTC acceptance. Manual signaling and public STUN avoid an owned room server; restrictive networks may still need TURN. Do not promise universal connectivity without a relay.
- [x] Chrome–Edge and Chrome–Firefox direct peers on separate processes on the owner's PC: 399 synchronized frames, both deploy orders, bidirectional chat and synthetic audio/video, zero room API requests; disconnect stops simulation. Separate devices/networks and real Safari remain pending. Windows WebKit's test build lacks WebRTC and is not Safari proof.
- [x] Owner-authorized production deployment at https://rtsai.net/play/; public two-client direct peer acceptance: 199 matching hashes through frame 200, both human deploy orders, chat and synthetic video/audio, zero room API requests.

The browser model co-commander uses a local companion service. Native bots, tactical personalities and scenario drills work without a model. Hosted or in-browser model inference is not delivered.

## Preservation and integration

- [x] Safety branches, all-ref Git bundles and dirty-file snapshots for all eight repositories: `D:/rtsai-consolidation/20261009`.
- [x] Main integration of current catalog, companion, harness, art, mission and mod work.
- [x] Commit loose art models/candidates and film resources on their main branches.
- [x] Preserve 5,104 legacy resource entries; verify 4,019 installed original-content resources.
- [x] Preserve and hash-check 182 changed entries from six older overlapping companion/faction/installer branches in `resources/history/branch-variants-20261009.zip` with a tracked index.
- [x] Reconcile the six historical companion/faction branches with their existing main integrations; retain newer reviewed assets and verify all 182 historical entries.
- [x] Unify native/browser engine inputs on published `rtsai/engine` revision `aed51fe4b1`; backport compatible rotation, missile, model-depth and headless fixes to historical OpenRA main. The older Classic rendering ABI remains intentionally separate. See `engine-branch-resolution-20261009.md` for file decisions and validation.
- [x] Retire 31 redundant/historical workspaces with verified snapshots and recovery refs; 44 checkouts reduced to 13. Index: `resources/history/workspace-retirement-20261009.json`. Five retained extra folders support native/browser builds, preview tooling and pinned generator history.
- [x] After canonical reconciliation and validation, retire the duplicate browser-engine checkout: 12 checkouts now remain, including four required inputs. The shared engine source snapshot and exact tested-tree record are under `D:/rtsai-consolidation/engine-resolution-20261009`; no directory links or unique source commits were removed.

Native and browser consumers now share one engine input. Browser runtime adaptations are optional or guarded; their previous engine branch remains a historical reference. Historical Classic main retains its older rendering ABI with compatible fixes backported. Older worktree folders are not additional game releases. Research, generated alternatives and superseded installers remain source history; preservation is distinct from runtime activation.

The owner explicitly requested online downloads and end-to-end testing on 9 October. Windows and the static web build were published for that request. No hosted CI, paid service or certificate purchase was added.
