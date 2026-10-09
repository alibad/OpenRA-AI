# RTS AI continuation — 9 October 2026

## Repository responsibilities

Workspace: `C:/Users/Admin/Code/hq/games`.

| Repository | Responsibility | Git destination |
|---|---|---|
| RTSAI-Mod | Canonical standalone product, rules, factions, campaigns, map generators and original content | alibad/RTSAI-Mod, main |
| OpenRA-wt-rtsai-engine | Minimal engine changes; push before changing the mod's engine pin | alibad/OpenRA, rtsai/engine |
| OpenRA | Preserved Classic implementation and integration history | alibad/OpenRA, main |
| OpenRA-AI | Companion service, shared catalogs, roadmap and handoff documents | alibad/OpenRA-AI, main |
| RTSAI-Web | Next.js website at rtsai.net; main pushes deploy via Vercel | alibad/RTSAI-Web, main |
| RTSAI-WebGame | Actual browser engine, React game UI, local adapters and public build tools | alibad/RTSAI-WebGame, main (private) |
| RTSAI-Art | Preserved art, generators and provenance | alibad/RTSAI-Art, main (private) |
| RTSAI-Film | Preserved film sources and release tooling | alibad/RTSAI-Film, main (private) |
| OpenRA-RL | Reinforcement-learning bridge | alibad/OpenRA-RL, main |

The worktrees are checkouts of these repositories, not separate products. Nested OpenRA-Upstreams repositories are clean third-party reference sources. Do not push them to upstream maintainers. The unrelated ai-game folder is AI Quest: Operator Academy and is outside this RTS consolidation.

## Categorized commits from this pass

- RTSAI-Mod `99048bc`: map inventory, preserved Classic-to-isometric adaptations and deterministic Earth battlefield compiler. Also pushed existing `e92fd1b`, the original Lines of Hope campaign narrative source.
- RTSAI-WebGame `e8bc05c`: G applies the newest co-commander recommendation; repeated keys and text entry are protected, bindings reserve G, UI and tests explain the shortcut.
- RTSAI-WebGame `71f1f67`: local Map studio, worker map mounting and multiplayer catalog compatibility checks.
- RTSAI-WebGame `12b4dd0`: walkthrough capture, packaging, player checks and local Kokoro neural narration tooling.
- Earlier committed browser changes include faction/mission expansion, campaign story source, ground/resource rendering, actor occlusion fixes, public local-service hiding, multiplayer labeling and dropdown improvements (`ed12eef`, `b44c3e6`).

## Verification and deployment boundary

This pass passed the full browser TypeScript/Vite build, room API tests (including map compatibility), Node syntax checks for the new server/video scripts, and deterministic Earth compiler tests. The default Python lacks NumPy; use the bundled Python below. This pass did not rebuild every native target, rerun the live companion strategy test, or regenerate the narrated videos.

The public game is https://rtsai.net/play/. The last verified deployment is `dpl_DB24bk1W63YqzmF2cXeetpMW8bAJ`, from the preserved `RTSAI-WebGame/build/public-dropdowns-20261009` artifact. Its public runtime is `rt-848227494802/`, data `data-c7c240400e18/`, bundle `0bc86750788b7b02a0dd`. Live mission difficulty and multiplayer faction search passed. This commit/push pass does not deploy the newly preserved Map studio, companion controls or video tools. Local services remain hidden in static builds.

The Git repositories hold source. Ignored builds, runtime packs, local geographic evidence, preserved legacy resources and rendered videos remain on this machine; a source push is not a complete asset backup. Preserve them and their provenance before cleanup. Never upload owned-game content or advertise unreviewed archived resources as integrated.

## Where to focus next

1. **Reproducible release:** consolidate the public build procedure around current main, verify runtime manifest hashes, and test fresh boot, resource harvesting, crates, missions and two-browser multiplayer. Restore lean AOT only after the assembly-integrity issue is resolved; the working deployment uses the larger stable runtime. Review source provenance before publishing generated maps or campaign assets.
2. **Multiplayer usability:** private invite flow, NAT/TURN needs, disconnect/reconnect behavior and clear host/join controls. Public direct peer-to-peer and local room-server multiplayer are distinct transports. Public static hosting has no room API or hosted companion service.
3. **AI with controlled cost:** keep authoritative gameplay deterministic. Use local companion tools for development; decide hosted authentication, per-user limits, budgets and key storage before enabling paid APIs publicly. Never expose API keys to browser builds.
4. **Audio and localization:** replace unsuitable animal effects with licensed or project-made recordings; neural TTS is for speech. Inspect Kokoro/Chatterbox locally, retain Kokoro am_michael for existing walkthrough revisions. Add explicit voice-language and English override choices rather than tying UI language irreversibly to faction. Do not use Windows system voices.
5. **Product integration:** preserve both Classic/top-down and isometric modes with one entry. The current browser Classic map ports still use an isometric renderer. Finish the actual mode selection and validate faction/campaign coverage without assuming every indexed upstream mission is playable.

## Local commands

```powershell
Set-Location C:/Users/Admin/Code/hq/games/RTSAI-WebGame/web
npm ci
npm run build
Set-Location ..
node tools/multiplayer-test.mjs
node server/serve.mjs
# Default local browser address: http://127.0.0.1:3490/

Set-Location C:/Users/Admin/Code/hq/games/RTSAI-Mod
& C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe tools/test-earth-battlefield.py
./make.cmd all
./make.cmd test
./launch-game.cmd
```

Read each repository's AGENTS.md and current product-direction/roadmap documents before continuing. Implement directly in application code, keep hosted CI out of this workspace, avoid force pushes and history rewriting, and obtain a deployment request for future publication.
