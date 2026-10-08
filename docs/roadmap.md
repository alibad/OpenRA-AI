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
- [x] Windows per-user EXE installer and portable ZIP with checksums (`0.4.0-alpha.1`).
- [ ] Clean-machine acceptance outside the development machine.
- [ ] Independently play through all mission outcomes and broader roster/balance combinations.
- [ ] Port additional historical Classic mechanics, maps and presentation retained in the older fork. This Classic profile presents shared standalone army rules on a rectangular grid; it does not reproduce every old Classic feature.
- [ ] Native-speaker review of outstanding voice sheet entries.
- [ ] Optional signing and public distribution after an explicit release request.
- [ ] macOS package and acceptance on the owner's Mac.

One launch path: `RTSAI-Mod/launch-game.cmd`; choose the mode in **Game modes**. Packages have the same choice in `RTSAI.exe`.

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
- [ ] Explicitly authorized deployment. Pushing RTSAI-Web main deploys production.

The browser model co-commander uses a local companion service. Native bots, tactical personalities and scenario drills work without a model. Hosted or in-browser model inference is not delivered.

## Preservation and integration

- [x] Safety branches, all-ref Git bundles and dirty-file snapshots for all eight repositories: `D:/rtsai-consolidation/20261009`.
- [x] Main integration of current catalog, companion, harness, art, mission and mod work.
- [x] Commit loose art models/candidates and film resources on their main branches.
- [x] Preserve 5,104 legacy resource entries; verify 4,019 installed original-content resources.
- [ ] Resolve older branch variants and engine differences without replacing newer reviewed assets or intentional build targets blindly.
- [ ] Retire redundant worktrees only after unique files and commits have verified destinations. No deletion is part of this delivery.

Native slim and browser engine branches are build dependencies with different runtime requirements. Older worktree folders are not additional game releases. Research, generated alternatives and superseded installers remain source history; preservation is distinct from runtime activation.

Development stays local. No new hosted CI, paid service, certificate purchase, public release or production deployment is implied.
