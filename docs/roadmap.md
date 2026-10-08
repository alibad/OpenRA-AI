# RTS AI roadmap

## Owner clarification — 9 October 2026

RTS AI must require no owned Red Alert or Red Alert 2 installation. Keep both Classic/top-down and RA2/isometric gameplay, with one product entry and an in-game mode choice. The canonical mod is `RTSAI-Mod`; consolidate its original-content standalone work there and preserve custom resources, models, generators, maps, audio and provenance from the older repositories before any cleanup. See `../RTSAI-Mod/docs/product-direction.md` and `../RTSAI-Mod/resources/resource-transition.json`.

The sections below record earlier decisions and verification. Their RA2 ownership requirement, RA2-only scope and parked-Classic status are superseded. The default mod now uses standalone original content; Classic mode and the combined chooser still require a port. Do not claim the old owned-RA2 add-on is that dependency-free Classic mode.

Updated 2 October 2026. Approved by the owner. This replaces the 12 September dual-mode roadmap.

## Status, 6 October 2026

**Every known issue from 5 October is fixed in the preview copy** (`RTSAI-Mod-wt-art-preview`, branch `rtsai/art-preview`). It is verified locally and awaits the owner's review. None of it is in `RTSAI-Mod` main, and nothing is pushed.

Art:

- **69 vehicles, ships and aircraft** are now prerendered sprites made straight from their 3D models. The voxel conversion flattened them, so the voxel route is kept only as a fallback.
  - They pass the stock-family gate, with lit-RGB checks for sprites, and a fragment gate.
  - Spinning radars, rotors and propellers, recoil, and the reload cue on the two rocket trucks all work.
  - Muzzles sit within 0.24 px of the drawn barrel tip, down from about 9 px.
- **28 infantry** wear faction uniforms with each faction's accent colour, at stock brightness, with a smaller team-colour share.
- **25 buildings** carry a faction panel.
- **All 122 cameos** match their units, carry stock-style name bars (CC0 pixel font) and pass the stock gate on the picture area, 122 of 122.

Engine, on `rtsai/engine` (local):

- Missiles now track ramp surfaces and hit at 160 of 160 sites, with stock units unchanged.
- A latent upstream divide-by-zero in `WRot.SLerp` that crashed games on adjacent ramps is fixed.

Gameplay:

- All 191 armament tests pass. The explosive boats can now reach ships.
- **Balance round 4:** 15 of 16 targets are met. The miss, China against the modern factions at 33%, is within noise.
- **Bot fixes for all factions:** no shipyard unless ships can reach the enemy, one airfield jet of each type at a time, and Israel's and Hezbollah's types are added to the bot lists.

Audio:

- The naval sound effects' provenance is proven.
- Israel (Hebrew) and Hezbollah (Lebanese Arabic) have their own voices and announcers.
- Call signs are fixed.
- 74 non-English lines are machine-checked, with the wrong ones regenerated.

Studio and app:

- The local app at `http://127.0.0.1:3450` starts at login.
- The Studio previews recoil and muzzle flashes, plays spins and draws the sprite vehicles.
- Its renderer matches the engine to the pixel.

**Owner gates, in order:**

1. Decide the 122 units in the Studio.
2. Native-speaker sign-off of `docs/voice-review.csv`. It has 28 flagged lines, plus the hand-pointed Hebrew.
3. Approve publishing:
   - the engine fixes (`rtsai/engine`);
   - the promotion of the preview into `RTSAI-Mod` main, with the engine pin;
   - the release;
   - one web deploy.
4. Hosted AI setup: Vercel environment variables, the Firestore TTL and rules, and the Anthropic workspace limit.
5. Buy a code-signing certificate.
6. Doctrine call: China's army is about 38% tanks and rocket artillery at about 0.7 value per credit. A smaller tank share would lift it against the modern factions but change its identity.

**Remaining work after those gates:**

- Promote the approved preview into main.
- Real Haiku smoke calls.
- Clean-machine acceptance, the trailer and the release (Phase 4).
- RA2 missions.

**Known structural limits** (recorded in `docs/balance.md`, not fixable with numbers):

- Stock Cloning Vats and armed War Miners favour the Soviet side.
- The naval map is reported, not tuned.

## Owner-requested local expansion — 4 October 2026

The owner requested Israel and Hezbollah as complete faction packs in both modes. These are local development packs: original authored art, infantry, armor/support vehicles, aircraft, naval roles, three defenses and two support buildings per faction, integrated production and bot composition. They use fictional gameplay abstractions; no real-world effectiveness is claimed. RA2 remains the canonical product. Classic contains the new packs in the World War III experience; the existing public alpha is unchanged.

The owner also requested full-roster website dossiers, a live map Workshop and browser/native behavior evaluations. Those local tools now cover both factions. Keep release coverage and production deployment separate: new faction art, broad balance and owner approval remain open gates. No publishing or paid generation is approved by this expansion request.

## The product

**RTS AI is a Red Alert 2 mod for OpenRA: modern factions, commanded with an AI co-commander that works from the first launch.**

- The player owns Red Alert 2 (Steam, EA app/Origin or disc), and the mod imports it. Commercial RA2 data is never bundled.
- The seven modern factions are China, Iran, Türkiye, Saudi Arabia, Yemen, Israel and Hezbollah. One catalog (`catalog/factions.json`) is the source for the game, the companion and rtsai.net.
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

**Status, 3 October 2026:** all five nations are playable in `alibad/RTSAI-Mod`. Done:

- Doctrine bots with per-faction squad sizes.
- Licensed voices and a per-faction announcer (`docs/audio-provenance.md` in the mod).
- 87 painted, traceable cameos (`docs/art-provenance.md`).
- Zero lint warnings.
- A balance harness with evidence (`docs/balance.md`). The modern nations sit at 33–57% among themselves.

Still open: China, Türkiye and Iran trail America and Russia in bot play; RA2 missions; a native-speaker review of the non-English lines.

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

**Status, 3 October 2026:** built. The installer defaults to hosted AI with local voice, and the mod starts the companion.

- Built: the hosted Claude Haiku 4.5 proxy, privacy-policy coverage and spend alerts. All verified against a mocked API.
- Multiplayer: the AI co-commander is a lobby option that every player sees, off by default with 2+ humans.
- Waiting on the owner: Vercel environment variables, Firestore setup and the Anthropic workspace limit (`RTSAI-Web/docs/launch-checklist.md`). Then real smoke calls.

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

## Phase 5 — Red Alert 4 on the web (later, owner direction 5 October 2026)

**Owner direction, 9 October 2026:** execute contextual in-match strategy choices and persistent confirmed-action goals in `RTSAI-WebGame` locally. Preserve all five browser AI opportunities in [the browser AI roadmap](../../RTSAI-WebGame/docs/AI-ROADMAP.md): (1) contextual strategies/persistent goals, (2) battlefield communication, (3) replay coaching/practice, (4) adaptive opponent personalities (lower priority), and (5) conversational scenario creation. This adds a local browser workstream; it does not authorize publication or deployment. Detailed implementation scope and acceptance criteria live in that roadmap.

The owner wants to eventually build a "Red Alert 4" in the browser with the best web graphics technology. It starts from the installable local app and reuses the factions catalog, the 122 authored 3D models, the rules facts and the hosted AI co-commander. This revises the 2 October "no web game" decision, but only for the period after the mod ships. Phases 2–4 come first.

First step when it starts: a technology spike and a one-map, two-faction vertical slice. Choose the renderer, the simulation and the netcode from current evidence at that time, not from this note.

## Open branches (inventory, 2 October 2026)

None of these branches has been pushed; their commits exist only in the local worktrees. No worktree is both fully merged and clean, so none has been removed.

| Branch (repo) | State | Decision |
|---|---|---|
| `codex/ra2-red-sea` (product) | 4 commits + uncommitted roster/voice edits and `validate-ra2-red-sea.py` | Phase 2: finish, validate, merge |
| `codex/in-game-catalog` (engine 5, product 6) | Clean | Phase 2: port into `OpenRA.Mods.RTSAI` after the Phase 1 decision |
| `codex/nl-orders` (product) | 6 commits + 1 untracked doc | Phase 3: single-call voice orders |
| `codex/harness` (product) | 4 commits + uncommitted docs | Phase 2 balance tooling (internal only) |
| `codex/upstream-sync` (engine) | 182 commits, clean | Phase 1 input for the slim engine branch |
| `codex/integrator-fixes` (engine 1, product 1) | Clean; Classic mission fixes | Parked with Classic |
| `codex/usa-concept` (engine 2, product 2) | Clean; a sixth nation | Parked: not in the five-nation scope |
| `codex/art-audit` (engine, product) + detached baseline | No commits; ~190 uncommitted Classic sprite/script changes | Parked with Classic. The owner decides whether to commit it as WIP or discard it |

## Guardrails

**Owner-requested local tooling, 4 October 2026:** Workshop now includes a Campaign Studio for both catalogs, with editable chapters, cast, storyboards, objective playtests, branching consequences and custom map attachments. The starter is explicitly fictional civilian storytelling. Intro export produces original silent animated briefings and captions in the browser. This does not deliver native campaign scripts or paid AI cinema; those remain separate work. Details: `../RTSAI-Web/docs/campaign-studio.md`.

- Commercial Red Alert 2 data is never bundled. A source path is not a redistribution license.
- "Implemented", "verified in development" and "in the public release" are separate states.
- No hosted CI workflows.
- Pushing web `main` deploys Vercel, so releases and deployments remain deliberate actions.
