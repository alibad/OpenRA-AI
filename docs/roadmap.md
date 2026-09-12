# OpenRA AI roadmap

Updated 12 September 2026. This is the handoff roadmap for the next build cycle.

## Current position

- Native OpenRA `main` supports the Classic (`ra`) and integrated Red Alert 2 (`ra2`) launch paths.
- Windows packaging includes the self-contained engine, companion, local AI option, and owned-RA2 import path.
- The web app now has a shared, validated faction catalog and player flow: faction → signature unit → mode → install guidance.
- Classic contains the five modern faction identities; the current RA2 overlay contains China, Iran and Türkiye.
- Public alpha.13 remains the only release advertised by the website. The newer dual-mode Windows build is local and unpromoted.

## Next milestone — first public dual-mode release

1. Finish the catalog integration: add full roster coverage incrementally, expose the catalog in the installed companion/game surfaces, and keep engine rules authoritative for balance and mechanics.
2. Complete the faction experience: add accurate RA2 captures, improve portraits and story art, verify licensing/provenance, and add missions, counterplay and AI behavior per faction.
3. Finish installer acceptance: clean-machine install without Python/.NET, Classic first run, owned RA2 import, missing-content/retry flows, secondary Steam library, offline local AI, explicit external provider, upgrade, uninstall, saves and settings preservation.
4. Produce release evidence: exact product/engine commits, artifact sizes and SHA-256 digests, Windows Authenticode result, and independent macOS signing/notarization/stapling evidence.
5. Promote only after all evidence checks pass. Update per-platform release coverage separately; never infer Mac or RA2 availability from another platform or from a local build.
6. Publish the game release and update the committed web manifest only with explicit approval. Deploy the web app only after the public links and clean-install walkthrough are verified.

## Later milestones

- Add Saudi Arabia and Yemen to the RA2 overlay when their rules, art, AI and balance are actually complete.
- Render the shared faction/unit catalog inside the native game and companion, with mode-aware details and deep links back to the web.
- Add replay-backed faction balance tests, headless AI match evaluation, and deterministic mission acceptance.
- Establish a polished media pipeline for original concept art, UI portraits, sprites, live captures, audio and accessibility review.
- Add release update, rollback, repair and uninstall diagnostics for installed users.

## Guardrails

Commercial Red Alert 2 data is never bundled. A source path is not a redistribution
license. “Implemented,” “verified in development,” and “in the public release” are
separate states. No hosted CI workflow is required, and pushing web `main` deploys
Vercel, so release and deployment remain deliberate actions.

See [faction-install-milestone.md](faction-install-milestone.md) for the detailed
acceptance checklist and [upstream-reuse/roadmap.json](upstream-reuse/roadmap.json)
for the component-level reuse inventory.
