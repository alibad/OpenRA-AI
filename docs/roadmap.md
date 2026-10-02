# RTS AI roadmap

Updated 2 October 2026. Approved by the owner. This replaces the 12 September dual-mode roadmap.

## The product

**RTS AI is a Red Alert 2 mod for OpenRA: five modern nations, commanded with an AI co-commander that works from the first launch.**

- The player owns Red Alert 2 (Steam, EA app/Origin or disc), and the mod imports it. Commercial RA2 data is never bundled.
- The five nations are China, Iran, Türkiye, Saudi Arabia and Yemen. One catalog (`catalog/factions.json`) is the source for the game, the companion and rtsai.net.
- The AI default is a hosted model for the thinking and local voice: Whisper for speech-in and Kokoro for speech-out. It falls back gracefully when offline or over the daily allowance.
- Windows ships first. macOS follows the first public mod release.

Judge every change by one question: does it make the RA2 mod, its factions or the out-of-box AI better? Anything else waits.

## Parked

These stay in git but leave the product story, the website navigation and the release scope:

- Classic (`ra`) mode and its faction packs. The shipped alpha.13 remains downloadable as is.
- Earth-to-battlefield studio.
- Capability Atlas, build archive and platform-plan pages.
- Autonomous agent research (RL, headless commander). It is kept only as internal tooling for balance testing.
- Faction cursor effects.
- macOS releases, until Windows ships.
- The full local LLM as the default. It becomes an optional download.

## Phase 0 — Cut and align

- Website shrinks to Home, Factions and Download.
- The catalog is the single naming source:
  - Per-mode `name` and `role` for every unit, and `engineFactionId` and `name` for every faction mode.
  - `scripts/content_catalog.py` fails when a catalog name differs from the in-game Fluent string.
  - RA2 names are canonical.
- The web snapshot sync check runs in the web test suite.
- Consolidate the open `codex/*` worktrees: merge what is validated and in scope, and archive the rest.

## Phase 1 — Become an OpenRA mod

- Start with a technical test build in `../RTSAI-Mod`, a Mod SDK structure that pins an `alibad/OpenRA` engine commit. Decide go or no-go before migrating.
- Target layout:
  - `mods/rtsai`: the RA2 rules, chrome and maps.
  - `mods/rtsai-content`: a content installer for Steam, Origin/EA and disc, modelled on Romanov's Vengeance.
  - `OpenRA.Mods.RA2`: the net10 port.
  - `OpenRA.Mods.RTSAI`: the companion bridge, faction logic and widgets.
  - The Python companion as a bundled sidecar.
- Slim pinned engine branch: Arabic/right-to-left text, plus the screenshot and push-to-talk hooks if they cannot live in the mod. With RA2 as the only mode, the Experience file-selection system is not needed. The RL/headless engine work moves to its own branch.
- Done when the mod installs, imports owned RA2, plays a skirmish and the companion speaks.

## Phase 2 — Five complete factions (parallel with Phase 3)

- Saudi Arabia and Yemen in RA2: review and merge `codex/ra2-red-sea`, add per-country validators, and flip the catalog entries.
- What "complete" means for each faction:
  - The full roster in the catalog, including structures and defenses.
  - Painted cameos, replacing the model-render placeholders.
  - RA2 voice lines with variety, plus a faction announcer (EVA).
  - Its own bot doctrine.
  - Real RA2 captures for the website.
- The catalog is rendered in-game (`codex/in-game-catalog`). The companion knows each faction's doctrine and units.
- Balance through automated AI-vs-AI matches; clear the RA2 rules lint warnings.

## Phase 3 — AI that works out of the box

- Hosted proxy on rtsai.net:
  - The key stays server-side.
  - A per-account daily allowance, a model allowlist, a `max_tokens` clamp and an image-size limit.
  - A global spend cap and a kill switch.
  - Zero-click anonymous allowance on first launch; linking an account raises it.
- Gateway "hosted" mode: the thinking goes to the proxy and voice stays local. It falls back to fixed alert lines when offline or over the allowance.
- Installer default is "Hosted + local voice (~280 MB)" instead of the 1.76 GB pack.
- Fix External mode never starting the gateway in installed builds.
- Cost guardrails:
  - Downscale screenshots.
  - Single-call voice orders (`codex/nl-orders`).
  - No AUTO mission planner on the hosted model.
- Target first run: install, launch, RA2 detected, play, companion speaks.

## Phase 4 — Ship

- Clean-machine Windows acceptance and a signed release.
- Site relaunch with a 60-second trailer cut from real gameplay. The download page states the RA2 ownership requirement up front.
- Then macOS, RA2 missions (starting with the Red Sea theatre) and a mod-directory listing.

## Guardrails

- Commercial Red Alert 2 data is never bundled. A source path is not a redistribution license.
- "Implemented", "verified in development" and "in the public release" are separate states.
- No hosted CI workflows.
- Pushing web `main` deploys Vercel, so releases and deployments remain deliberate actions.
