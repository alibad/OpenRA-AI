# Windows and web release acceptance — 9 October 2026

The owner requested online Windows downloads and end-to-end testing. Windows **0.4.0-alpha.1** is published at [rtsai.net/download](https://rtsai.net/download), and the consolidated static browser game is live at [rtsai.net/play](https://rtsai.net/play/). The [GitHub release](https://github.com/alibad/RTSAI-Mod/releases/tag/v0.4.0-alpha.1) contains the EXE installer, portable ZIP and checksums. This alpha is unsigned; macOS is pending the owner's Mac.

Neither product requires owning Red Alert or Red Alert 2. Windows includes Classic/rectangular and RA2-inspired/isometric profiles, 16 country choices, six campaigns, native bots and the optional local companion. Classic currently shares the modern army; full historical Classic parity remains unfinished. Browser Classic and complete browser/native workshop/call parity also remain open.

## Observed checks

- The real public website button downloaded the installer. SHA-256: `2157f33369d4dbce08a445799d7242803500ef5d79cace8e496c4923dd3accfe`.
- Installation with No AI, configuration, shortcut, rendered mode switch, installed skirmishes in both profiles, and uninstall passed. Existing registration and unrelated user files were preserved. Browser-downloaded unsigned files produce the expected Windows trust prompt; the website describes verification and launch instructions.
- Public browser: two independent clients, 16 factions, both human deploy commands, 199 matching hashes through frame 200, peer chat and synthetic video/audio, zero room API requests, no page errors. This does not establish different-network or real-camera acceptance.
- Website build/typecheck and full suite: 261 passed, four skipped. Art/content synchronization passed. A healthless refinery upgrade is preserved in the catalog and excluded from standalone map placement.
- Native strict content/standalone checks passed. All 4,019 installed resource hashes and 5,104 preserved source entries verified; 1,338 audio provenance entries checked.
- Local Studio starts from canonical `RTSAI-Web`, without detaching its branch. Its existing Startup launcher was updated. Art generator defaults use canonical source paths.

## Source cleanup and preservation

31 redundant or historical checkouts were retired: 44 reduced to 13. Eight primary repositories remain on main. The five additional folders are pinned native/browser engines, the preview/public mod build inputs and a generator-history source checkout. They are dependencies, not user-selectable product versions.

The tracked recovery index is `resources/history/workspace-retirement-20261009.json`; full snapshots and directory-link records are in `D:/rtsai-consolidation/cleanup-20261009/index.json`. Historical sources have recovery refs and archived dirty files. Their preservation does not claim that all historical engine/asset variants are runtime-integrated. Editable art, audio, maps, generators and film work remain recoverable. Regenerable dependencies can be installed from the archived lockfiles.

During initial cleanup, Git followed shared directory links and removed committed files from the canonical mod checkout. Those files were restored from Git, original line endings recovered against the inventory, all installed hashes verified and strict native tests rerun successfully. Directory reparse points are now indexed and unlinked explicitly before deletion. Private legacy support content was checked and remained present.

Unused interrupted backup files remain alongside the verified snapshots because automatic approval review rejected their deletion with the stated reason “blocked by policy.” They are not active workspaces.

## Evidence and visual report

- `C:/Users/Admin/Code/hq/games/artifacts/consolidation-20261009/delivery-report.html`
- `D:/rtsai-release/online-e2e-20261009/online-browser-acceptance.json`
- `D:/rtsai-release/online-e2e-20261009-skirmishes-final/installer-acceptance.json`
- `artifacts/consolidation-20261009/site-release-tests.log`, `online-peer-tests.log`, `online-installed-skirmish-tests.log`, `post-cleanup-native-tests.log`, `cleanup-final.log`, `canonical-studio-launch.log`

The active roadmap retains clean-machine, cross-network, broader campaign/balance, historical Classic, voice review, Mac and trailer/signing work. No hosted CI or paid service was added.
