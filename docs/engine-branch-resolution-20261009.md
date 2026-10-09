# Engine and historical branch resolution — 9 October 2026

The downloadable and browser products now use the same engine revision:
`aed51fe4b1c699b487b9f9683dbc79215f3a96be`, published on `alibad/OpenRA:rtsai/engine`.
The browser engine was a direct descendant of the native engine. Fast-forwarding
the shared branch preserves every native fix and the four embedded-host commits.
RTSAI-Mod pins that revision; RTSAI-WebGame reads OpenRA-wt-rtsai-engine.

## The nine browser-specific source differences

| Source | Resolution |
| --- | --- |
| GameRules/Ruleset.cs | Browser skips background loading tasks; desktop keeps them. |
| Map/MapCache.cs | Browser skips unsupported filesystem watchers; desktop keeps them. |
| ObjectCreator.cs | Embedded assembly loading requires browser runtime or explicit opt-in. |
| Support/Log.cs | Browser writes synchronously; desktop retains its logging thread. |
| Graphics/SpriteCache.cs | Optional sprite-cache and packing hooks default to null. |
| Graphics/SheetBuilder.cs | Additional sheet API serves the optional packing hook. |
| Graphics/SpriteRenderable.cs | Read-only accessors expose sprite placement to the web renderer. |
| Sound/Sound.cs | Optional readiness hook defaults to null; deferred network audio affects presentation. |
| OpenRA.Game.csproj | Friend assembly permits the existing embedded simulation host. |

These are intentional runtime adaptations, now included in one shared engine.
No replacement of desktop networking, native bots or native rendering is required.

## Historical OpenRA main

OpenRA main is the retained older Classic implementation. It has a different
rendering API (`float2`/`float3`) and additional legacy mod/companion code; the
shipping standalone Classic mode is RTSAI-Mod's rectangular profile. Replacing
that entire historical tree with the slim engine would lose an independently
useful reference implementation and reintroducing its stock content into the
standalone game would contradict the owner's original-content requirement.

Compatible engine fixes were ported to OpenRA main: world-unit missile lookahead,
ramp clearance, near-equal rotation interpolation, its upstream trigonometry
prerequisite, camera-consistent model offset depth, 1,024 headless placeholder
frames, and safe disposal/rendering when a headless shroud layer was not loaded.
Model depth uses the older vector types, retaining the same tested math.
Player-palette annotation and missile interception ammo/cooldown behavior were
already present and were not duplicated.

`codex/upstream-sync`'s two local headless fixes are now ported. Its remaining
upstream Vector2/Vector3 migration is already incorporated in the shared product
engine. It is deliberately not a wholesale replacement of historical Classic's
ABI. Its source and validation artifacts remain in Git and verified snapshots.
`bleed` is an upstream reference, not unfinished product work. Both refs remain
available; their non-ancestor relationship to legacy main is intentional.

The ten sprites on `codex/art-audit-baseline` retain their newer reviewed main
versions. The original baseline is now reachable through merged Git ancestry;
`resources/history/branch-resolution-20261009/art-baseline.json` records both
sets of SHA-256 hashes. No old sprite silently replaces reviewed art.

## Six companion/faction branches

These features were previously integrated under different commit IDs. Normal
merges now reconcile their original ancestry while retaining subsequent main
revisions. They add no new runtime features. Patch comparisons are committed in
`resources/history/branch-resolution-20261009`.

| Historical implementation | Existing integration |
| --- | --- |
| c9294e6 air-warfare validation | 32eb927 |
| e248191 infantry and experience authoring | 4b2632e |
| d87a985 / 845d000 China | 4ea0002 / 6ee756b |
| a12d020 Iran | 89b3e05 |
| b1bb96d local runtime | afee1f8 (identical patch) |
| 7155671 modular profile validation | 1ad1be1 |
| ad017d6 Mandab campaign | 7318f30 |
| 78d0801 Turkey | 96401da |

The installer branch's f345c7f changes only its historical engine gitlink;
extensible faction loading is already present on canonical main. Old engine pins
are not restored. The removed China-only flag builder was replaced by the
combined faction flag builder. Three missing older Iran evidence images remain
in the hash-verified historical archive, preserving their historical context.
Current voice generation, asset remaps, mission inventory, model configuration
and standalone packaging take precedence over the older implementations.
All 182 original archive entries were verified before reconciliation.

## Verification and retirement gate

Local evidence is under `artifacts/consolidation-20261009` in the workspace:

- OpenRA engine: 609 passed, two existing PNG tests skipped; complete Release build, zero warnings/errors.
- Shared product engine: 518 passed, two existing PNG tests skipped.
- OpenRA-AI: 398 companion tests (three skips), 73 worldgen tests and 31 gameplay evals passed.
- RTSAI-Mod: shared-engine Release build and full native content/standalone/audio checks passed.
- Both standalone native modes ran rendered skirmishes for 40 seconds, with recorded replays and no early exits. All 5,104 preserved entries and 4,019 installed resources verify.
- RTSAI-WebGame: builds against the shared engine; recorded browser orders produce 500 matching native/AOT hashes. Interpreter replay also matches 500 hashes.

Bots choose orders independently in a non-replay fidelity run, so that run is not
a cross-runtime replay comparison. The initial interpreter run without replay
diverged at frame 72; the replay comparison checks the same recorded orders.
Peer lockstep remains tested separately. This report does not claim independent
bot sessions necessarily choose identical orders across different runtimes.

No remaining checkout is retired until canonical integration, current tests,
clean checkout state, a verified recovery snapshot, absence of unique commits
relative to its replacement target, and absence of directory links are checked.
The shared engine worktree remains a required input. Frozen public mod content,
art preview and generator-history inputs remain until their consumers are ported.

The duplicate `OpenRA-wt-web` checkout was subsequently retired only after the
exact canonical main trees were validated and clean. Its source ZIP, checksum,
replacement revision, source bundles and tested-tree evidence are saved under
`D:/rtsai-consolidation/engine-resolution-20261009`. It contained no unique
commits, untracked source files or directory links. Twelve checkouts remain:
eight primary repositories and four required source/build inputs.
