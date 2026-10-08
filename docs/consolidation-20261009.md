# Local consolidation — 9 October 2026

The full roadmap is **not complete**. Local main integrations, preservation and development builds are completed as described below. Historical Classic migration, engine consolidation, downloadable/browser parity and wider release acceptance remain open. No push, deployment or public release was performed.

## Product outputs

Windows standalone `0.4.0-alpha.1` has an unsigned NSIS EXE installer and portable ZIP under `D:/rtsai-release/dual-20261009/out-verified`. Both package the same game assembly, catalog, original content and frozen local companion. No models are embedded; optional local-model downloads remain available. The package excludes the owned-content importer and historical owned-RA2 manifest.

The actual packaged version was launched with an empty support directory; its preview handler, Game modes dialog and reload into `rtsai-topdown` were exercised. The resulting menu renders as Classic. Both profiles pass standalone checks and load their campaigns. Classic is currently the shared modern army on a rectangular grid, not complete historical Classic parity.

Static Web RTS is under `D:/rtsai-release/dual-20261009/web-public`, with Brotli/isolation hosting headers and BUILD.json. `RTSAI-WebGame/tools/serve-static.mjs` previews it at `http://127.0.0.1:3507/`. Direct peers exchange offer/answer codes, chat and optional calls without a room API. Public STUN is used; restrictive networks may need a relay that is not included. Cross-network acceptance is still open. A model co-commander needs a local companion; browser Classic remains unimplemented.

## Main and folder inventory

Eight repositories have 44 registered worktrees: eight primary checkouts and 36 additional checkouts. These are source/build workspaces, not 44 game releases. No worktree was deleted.

| Repository | Current local main work | Remaining boundary |
|---|---|---|
| RTSAI-Mod | Standalone resources, reviewed art, two modes, 16-country overlay, six campaigns, native objectives, companion contracts and packaging | Additional historical Classic and full browser/native parity |
| RTSAI-WebGame | AI lab, strategy/annotations/coaching/drills/personalities/scenario workshop, production/context controls, saves/replays/settings, room multiplayer and direct WebRTC | Classic, cross-network/device/browser acceptance; no remote configured |
| OpenRA-AI | Catalog, companion, harness, missions, art and loose docs integrated | Six older historical branch variants preserved on main, but distinct commits remain outside main |
| RTSAI-Web | Website and reviewed Studio/Workshop work; two-surface/local-AI story | Public production unchanged |
| RTSAI-Art | Loose editable models, candidate art, metadata and review history committed | Source library retained for regeneration/review |
| RTSAI-Film | Loose copy, notes and audio-finishing scripts committed | Final trailer not rendered |
| OpenRA | Reviewed catalog, mission fixes, USA concept and art audit integrated | Slim native/browser engine and upstream branches differ from legacy main; 38-conflict merge preview needs migration |
| OpenRA-RL | Historical research retained on main | Not a separate shipped game |

The pinned native engine `68c1e955578d804921f4907753af932fa7ed0e14` already resolves on the public fork. Native and browser engine branches retain different build requirements. Their history must not be replaced or falsely marked as merged merely to reduce folder counts.

## Preservation

- All-ref bundles, safety branches and dirty-file snapshots: `D:/rtsai-consolidation/20261009/index.json`.
- `RTSAI-Mod/resources/resource-transition.json`: 5,104 legacy source entries, 4,019 installed original-content entries and editable Art sources. Earlier installed hashes and their Git commits are retained. The corresponding legacy ZIP is local, excluded from release packages.
- `OpenRA-AI/resources/history/branch-variants-20261009.json` and ZIP: 182 exact changed entries from six historical branches, hash verified. Their code is archived source, not active runtime behavior.
- Read-only refresh: `python OpenRA-AI/scripts/audit-workspaces.py --out artifacts/consolidation-20261009/workspace-state.json`.

## Observed checks

Native build passed with zero warnings/errors; native YAML/strict standalone checks passed, including both profiles. 1,338 audio provenance entries and 73 neutral-name messages pass. Resource hashes pass. Companion tests: 398, three skipped. Website build/typecheck pass; 15 rendered tests pass, two admin-only tests skipped. Static direct-peer acceptance: 200 matching engine frames, both human deploy orders, peer chat, bidirectional synthetic video/audio, visible stop on disconnect and zero room API requests. Lockstep unit checks reject malformed/conflicting packets and mismatched synchronization hashes. The portable ZIP's assembly/manifests/catalog match the verified staged game.

These checks do not establish clean-machine acceptance, all campaign win/loss outcomes, full legacy/native/browser parity, native-speaker approval, real-phone performance or universal peer connectivity. Mac remains deferred to the owner's Mac. The complete earlier roadmap is retained alongside the active roadmap.

Interactive report: `C:/Users/Admin/Code/hq/games/artifacts/consolidation-20261009/delivery-report.html`. Evidence logs and screenshots are in the same directory; browser peer evidence is in `RTSAI-WebGame/artifacts`.
