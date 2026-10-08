# First public dual-mode release — acceptance checklist

Updated 28 September 2026. This is the detailed checklist behind the
[roadmap](roadmap.md) milestone "first public dual-mode release": one OpenRA AI
package per platform that ships World War III (Classic, `ra`) and integrated
Red Alert 2 (`ra2`) with the shared AI companion and the modern factions.

The release is promoted only when every **blocking** item below is `PASS` on
the exact artifacts being published. Evidence from a development checkout, an
earlier package, another platform or a unit test does not satisfy an item that
names a packaged or clean-machine check; record it as `PARTIAL` and say what is
missing. "Implemented", "verified in development" and "in the public release"
are separate states ([roadmap guardrails](roadmap.md#guardrails)).

## How to use this checklist

- **Status** is one of `PASS` (criterion met on the release candidate, with
  evidence), `PARTIAL` (supporting evidence exists but the exact criterion has
  not been met), `NOT RUN`, `BLOCKED` (cannot be run until an external
  prerequisite exists) or `FAIL`.
- Record evidence as the dated todo entry plus local artifact paths
  (`artifacts/` is untracked; keep the files on the release host). Never
  replace a failed result: keep it beside the rerun and explain the difference.
- `V` is the release version (for example `0.1.0-alpha.19`). Commands run from
  the product repository root with the pinned engine submodule unless noted.
- Clean-machine items use a disposable Windows 10/11 x64 VM or Windows
  Sandbox with no Python, no .NET SDK/runtime and no prior OpenRA/OpenRA AI
  data, and an Apple Silicon Mac that is not the build host. Record the OS build.
- Owned Red Alert 2 data is never bundled. Items that need it use the tester's
  own installation.

## Status at a glance (28 September 2026)

| Area | Items | PASS | PARTIAL | NOT RUN | BLOCKED | FAIL |
|---|---:|---:|---:|---:|---:|---:|
| A. Release identity and automated gates | 6 | 0 | 5 | 1 | 0 | 0 |
| B. Windows install and first run | 9 | 0 | 6 | 3 | 0 | 0 |
| C. AI companion modes | 4 | 0 | 3 | 1 | 0 | 0 |
| D. Upgrade, uninstall, data preservation | 4 | 0 | 0 | 4 | 0 | 0 |
| E. Signing and artifact evidence | 6 | 0 | 2 | 3 | 1 | 0 |
| F. Faction and gameplay gates | 10 | 3 | 5 | 1 | 0 | 1 |
| G. Promotion | 3 | 0 | 0 | 3 | 0 | 0 |

All items are blocking except F8 (informational) and F9 (a later milestone).

No release candidate for the dual-mode release has been built yet. The newest
artifacts are the local, unpromoted Windows `0.1.0-windows-dual.3` build
([windows-dual-game-verification.md](windows-dual-game-verification.md)) and
the signed Mac `0.1.0-alpha.18-ra2-preview.17`
([todo/2026-09-21.md](../todo/2026-09-21.md)). The website still advertises
alpha.13 ([apps/web/lib/release.ts](../apps/web/lib/release.ts)).

## A. Release identity and automated gates

| ID | Check | How | Pass criterion | Platform | Status and evidence |
|---|---|---|---|---|---|
| A1 | Identical, clean source on every release host | `git status --porcelain` (product and `engine/openra`); `python scripts/release.py plan --version V --target <target>`; build without `--allow-dirty` | Both trees clean; the product commit and submodule commit are identical on the Windows and Mac hosts; `apps/installer/ra2/upstream.json` `engine_commit` equals the submodule (`test_release_compatibility_lock_matches_checked_out_engine`) | Both | NOT RUN for a dual-mode candidate. Preview.17 was built from clean `076235c` / engine `5ddc34cb91` ([todo/2026-09-21.md](../todo/2026-09-21.md)) but not through `release.py`. |
| A2 | Full product check | `scripts/check.ps1 -FullEngine` (Windows); `package-macos.sh` runs the Mac validation | Exit 0: companion, worldgen and eval tests pass; web checks pass; engine Release build has zero warnings and zero errors; engine tests 544 passed / 2 skipped (PNG parser); branded launcher bootstrap passes | Both | PARTIAL. Parts run separately: 291 companion tests pass, 3 skipped (Windows, 28 Sep, this checklist's branch); engine 544/2 and zero-warning build ([todo/2026-09-21.md](../todo/2026-09-21.md)). No single `check.ps1 -FullEngine` run on a candidate recorded. |
| A3 | Rules lint baselines unchanged | `OpenRA.Utility.exe ra --check-yaml` with `OPENRA_UTILITY_EXPERIENCE_PROFILE=world-war-iii`, again with the AI Assistant Only profile; RA2 all-map lint (`OpenRA.Utility ra2 --check-yaml` per map, as in `scripts/validate-ra2-experiences.py`) | Zero errors. Warning multisets identical to the baselines: World War III 11,543; classic/AI Assistant Only 191; RA2 all maps 793. Any change is explained, never waved through by count alone | Both | PARTIAL. Baselines recorded on the preview.10 payload ([todo/2026-09-05.md](../todo/2026-09-05.md)); not yet re-run on a dual-mode candidate. |
| A4 | Version identity | Start the packaged game and companion; open the main menu, pause menu, AI transmission panel and `/health` | The exact `V` is shown in all four places and in `RA2-BUILD.json` | Both | PARTIAL. Verified for preview builds ([todo/2026-08-28.md](../todo/2026-08-28.md), [todo/2026-09-05.md](../todo/2026-09-05.md)); not for `V`. |
| A5 | No proprietary RA2 content in any artifact | Packaging check in `scripts/prepare-ra2.py` (refuses `*.mix`); list the ZIP/installer/DMG payload | No `.mix`, `.bag`, `.idx` or other Westwood archive in any artifact; `RA2-BUILD.json` has `"proprietary_content_bundled": false` | Both | PARTIAL. Enforced by the packager and confirmed for preview.10 ([todo/2026-09-05.md](../todo/2026-09-05.md)); re-check the candidate. |
| A6 | Local AI pack lock is valid | `python scripts/ai_pack.py validate` | Every model and runtime entry has pinned revision, URL, byte length, SHA-256 and license | Both | PARTIAL. Used for dual.3 and preview packages; re-run for `V`. |

## B. Windows install and first run

| ID | Check | How | Pass criterion | Platform | Status and evidence |
|---|---|---|---|---|---|
| B1 | Package build | `python scripts/release.py build --version V --target windows-x64 --official` (runs `package-windows.ps1`, both smoke tests and the release index) | Portable ZIP, setup EXE and AI-pack ZIP produced with `.sha256` files; both smoke tests pass | Windows | PARTIAL. Unsigned local `0.1.0-windows-dual.3`: 2.04 GB portable, 240,509,979-byte setup, 1,761,038,160-byte AI pack ([windows-dual-game-verification.md](windows-dual-game-verification.md)). Not built with `--official`. |
| B2 | Portable package smoke | `scripts/smoke-windows-package.ps1 -Version V -RequireAI` | Checksum matches; bundled executables start a headless match; `verify-live-match.py` sees a live bridge and an AI-layer answer; every started process exits | Windows | PARTIAL. Portable dual.3 imported Steam RA2, downloaded classic content and passed text/speech diagnostics on the dev host (same doc). The scripted smoke is not recorded for dual.3. Note the smoke uses the repository venv to verify, so it is not a clean-machine check. |
| B3 | Installer smoke | `scripts/smoke-windows-installer.ps1 -Version V -RequireSignatures` | Silent install to a temp dir; required files, Desktop/Start Menu shortcuts, icon and uninstall registration present; silent uninstall exits 0; pre-existing shortcuts/registration restored | Windows | NOT RUN for a dual-mode setup. |
| B4 | Clean-machine install without Python or .NET | Copy the setup EXE and matching AI-pack ZIP to a clean VM/Sandbox; run setup interactively with **Local AI (recommended)**; then start from the Start Menu | Setup completes without downloading Python, .NET or build tools; the adjacent AI pack is verified and used offline; the game and companion start; `where python`/`dotnet --info` still report nothing installed afterwards | Windows | NOT RUN ([windows-dual-game-verification.md](windows-dual-game-verification.md) lists it as a separate acceptance check). |
| B5 | Classic first run | On the clean machine start World War III for the first time | `Install-OpenRAContent.ps1` quick-install downloads the SHA-1-verified freeware content into `%APPDATA%\OpenRA\Content\ra\v2`; main menu shows World War III with the five modern factions; a skirmish vs a bot starts; AUTO deploys and builds | Windows | PARTIAL. Dev-host portable run downloaded classic content and played a China skirmish (same doc). Clean machine not run. |
| B6 | Owned RA2 import from Steam | On a machine with RA2 installed via Steam in the default library, choose Red Alert 2 | Content is discovered and imported to the support directory without modifying the Steam install; RA2 main menu and a skirmish start | Windows | PARTIAL. Dual.3's own companion imported Steam RA2 into an empty support directory (same doc). Not on a clean machine or with a candidate. |
| B7 | Owned RA2 import from a secondary Steam library | Install RA2 into a Steam library on a second drive (registered in `libraryfolders.vdf`); repeat B6 | The secondary library is found; manifest paths cannot escape the library | Windows | PARTIAL. Unit tests `test_discovers_owned_game_in_registered_secondary_library`, `test_manifest_cannot_escape_steam_library` ([test_windows_game_setup.py](../services/companion/tests/test_windows_game_setup.py)); no real secondary-drive run. |
| B8 | Missing content and retry | On a machine without RA2, choose Red Alert 2; then install RA2 and retry without restarting the product; also interrupt the classic download once | The game explains the owned-content prerequisite (no purchase or bundling offered); no dummy archives are created; retry succeeds after installation; an interrupted download leaves no partial content and resumes/retries cleanly | Windows | PARTIAL. Unit tests `test_missing_content_is_actionable_and_does_not_create_dummy_archives`, `test_failed_import_removes_staging_file`, `test_missing_or_truncated_language_archive_does_not_import_base`. The live UI flow is not recorded. |
| B9 | Both games in one package | From the main menu switch World War III → Red Alert 2 → World War III | Both modes available from one install; the choice is remembered; the companion stays connected across the switch | Windows | NOT RUN on a package; done on the canonical dev checkout with native computer use ([windows-dual-game-verification.md](windows-dual-game-verification.md)). |

## C. AI companion modes

| ID | Check | How | Pass criterion | Platform | Status and evidence |
|---|---|---|---|---|---|
| C1 | Offline local AI | Install with Local AI; disconnect the network; start a match; ask a question by text and by Hold to Ask (Ctrl+Space Windows, Option+Space Mac) | Answer and spoken reply are produced locally; no request leaves loopback; free ports are chosen and an unrelated service on port 4000 is untouched | Both | PARTIAL. Windows dev host: local explanation 2.9 s, text ~0.4 s, speech ~5.1 s, transcription round trip ([windows-dual-game-verification.md](windows-dual-game-verification.md)); Mac preview.17 captured live microphone audio and answered locally ([todo/2026-09-21.md](../todo/2026-09-21.md)). Not with the network disconnected; Windows microphone capture not claimed. |
| C2 | Explicit external provider | Run setup choosing **External or existing OpenAI-compatible provider** with a real endpoint/key/model; also change provider later in settings | Provider stored only in the user's OpenRA AI config; the installer INI is consumed and no plaintext key remains; answers come from the chosen provider; switching back to local works | Both | PARTIAL. Unit tests `test_configure_writes_provider_and_companion_settings`, `test_installer_ini_is_consumed_without_leaving_plaintext_key`, `test_external_gateway_forwards_provider_key` ([test_local_runtime.py](../services/companion/tests/test_local_runtime.py)). No live provider run on a package. |
| C3 | AI independent of models | Start without any model pack or provider | Native AUTO, deterministic alerts and bots work; Hold to Ask shows the install invitation instead of failing | Both | PARTIAL. Mac setup flow ([todo/2026-08-31.md](../todo/2026-08-31.md)); not re-run on a dual-mode candidate. |
| C4 | Natural-language order reliability | `nl-orders` acceptance suite (owned by that workstream) | Its own pass bar; spoken/text commands never execute unconfirmed forbidden actions | Both | NOT RUN (open issue in [ra2-mac-preview-validation.md](ra2-mac-preview-validation.md)). |

## D. Upgrade, uninstall and data preservation

| ID | Check | How | Pass criterion | Platform | Status and evidence |
|---|---|---|---|---|---|
| D1 | Upgrade from the previous public release | On a clean VM install public alpha.13, play once (settings, a save, a replay, imported content, provider choice), then run the `V` setup over it | Setup upgrades in place (same `%LOCALAPPDATA%\Programs\OpenRA AI`); shortcuts and uninstall entry point to `V`; everything in D3 is preserved; no stale alpha.13 binaries remain | Windows | NOT RUN. |
| D2 | Mac upgrade | Replace the previous app in `/Applications` with the `V` app from the DMG | App launches; settings, saves, owned RA2 content and model data under the user's support directories are unchanged | Mac | NOT RUN for `V`. Preview.12 replacement preserved settings, saves, RA2 content and models ([todo/2026-09-21.md](../todo/2026-09-21.md)). |
| D3 | Saves and settings preservation | Before D1/D4 hash `%APPDATA%\OpenRA` (settings.yaml, Saves, Replays, Content, maps) and the OpenRA AI config dir; compare afterwards | Byte-identical except for files the game is documented to update | Windows | NOT RUN. The installer uses per-user `%LOCALAPPDATA%\Programs\OpenRA AI` and the game uses `%APPDATA%\OpenRA`, but no automated check compares them. |
| D4 | Uninstall | Uninstall from Settings > Apps and from the Start Menu entry | Program files, shortcuts and HKCU uninstall key removed; `%APPDATA%\OpenRA` user data and imported RA2 content kept; a later reinstall finds them | Windows | NOT RUN. `smoke-windows-installer.ps1` exercises silent uninstall of a temporary install but does not check data preservation. |

## E. Signing and artifact evidence

| ID | Check | How | Pass criterion | Platform | Status and evidence |
|---|---|---|---|---|---|
| E1 | Windows Authenticode | `release.py build ... --official` with `WINDOWS_SIGNING_CERTIFICATE_THUMBPRINT` / store / timestamp URL configured ([releasing.md](releasing.md)) | Companion, local runtime, game, server, utility, product launcher, NSIS uninstaller and setup all carry valid, timestamped signatures chaining to a public root (`sign-windows-artifacts.ps1 -RequireSignatures -VerifyOnly`); SmartScreen shows the publisher | Windows | BLOCKED: no OV/EV certificate or signing provider is provisioned. Published alpha.13 is unsigned and must not be described as signed. |
| E2 | Mac Developer ID signing and notarization | `release.py build --version V --target macos-arm64` with `MACOS_DEVELOPER_IDENTITY`/`MACOS_NOTARY_PROFILE`; `scripts/smoke-macos-package.sh V` | `codesign --verify --deep --strict` passes; notarytool submission Accepted with no issues; ticket stapled to the DMG and validates; Gatekeeper reports Notarized Developer ID for app and DMG; apphost keeps JIT entitlement; app and companion keep microphone entitlement | Mac | PARTIAL. Preview.17: submission `9f2b47f7-1aba-443c-b001-9a2bc03b9d20` Accepted; strict nested signatures, Gatekeeper, entitlements, stapling and mounted-DMG smoke pass ([todo/2026-09-21.md](../todo/2026-09-21.md)). Repeat for `V`. |
| E3 | Second-Mac verification | Download the DMG to a different Apple Silicon Mac; open with quarantine intact | Gatekeeper opens it without warnings; first run, RA2 import and local AI work | Mac | NOT RUN ([releasing.md](releasing.md) requires it). |
| E4 | Artifact digests and sizes | `release.py build` writes `artifacts/releases/OpenRA-AI-V-release-index.json`; after copying the other platform's artifacts: `python scripts/release.py index --version V` then `python scripts/release.py verify --version V` | Index lists every artifact (ZIP, setup EXE, AI pack, DMG) with bytes and SHA-256, the product and engine commits, and `worktree_dirty: false`; `verify` passes; each `.sha256` matches | Both | NOT RUN for `V`. Individual digests exist for previews (preview.17 DMG `a0c92f94…70cf`). |
| E5 | Mac payload integrity | `smoke-macos-package.sh` | DMG checksum, required payload, no release-host library dependencies or RPATHs | Mac | PARTIAL (preview.17). |
| E6 | Download-side verification | Download each published artifact from the GitHub release on a clean machine | Downloaded bytes match the release index; links in `apps/web/lib/release.ts` resolve | Both | NOT RUN (nothing published). |

## F. Faction and gameplay gates

| ID | Check | How | Pass criterion | Platform | Status and evidence |
|---|---|---|---|---|---|
| F1 | Classic modern factions playable | Native AUTO skirmish per faction (China, Iran, Saudi Arabia, Yemen, Türkiye) from an MCV start; faction live validators (`scripts/verify-china-live.py`, `validate-iran-live.py`, `validate-turkey-live.py`, `validate-mandab-mission.py`) | Each faction builds economy/production, recruits its own units and fights without foreign units or crashes | Both | PARTIAL. Per-faction validations in earlier cycles; balance baseline campaigns ran all five against every original country headless ([balance-baseline-2026-09.md](balance-baseline-2026-09.md)). Re-run on the candidate payload. |
| F2 | RA2 modern rosters | `scripts/validate-ra2-{china,iran,turkey}.py --resources <payload> --binaries <payload>/bin --content <Content> --output <dir>` | China: 17 units + 3 defenses, 3 cargo round-trips, 6 exact water movers; Iran: 14 + 3, 2 water movers; Türkiye: 16 + 3, cargo, 4 water movers; each passes within its game-time budget | Both | PASS on the development build: 12/12 China, 10/10 Türkiye, 10/10 Iran consecutive runs with four fixtures in parallel after the determinism fix (todo/2026-09-28.md). Re-run on the candidate payload. |
| F3 | RA2 combat and ranges | `validate-ra2-china-combat.py`, `validate-ra2-turkey-combat.py`, `validate-ra2-iran.py --mode combat` and `--mode edges` | Every armed entry damages its paired target; bonuses and ranges meet the recorded criteria | Both | PARTIAL. Passed on preview.10 payload ([todo/2026-09-05.md](../todo/2026-09-05.md)). |
| F4 | RA2 AI composition | `validate-ra2-ai-composition.py` | All six roles recruited by native AUTO, no foreign units, caps respected | Both | PARTIAL. Preview.10 payload ([todo/2026-09-05.md](../todo/2026-09-05.md)). |
| F5 | RA2 experiences and originals preserved | `validate-ra2-experiences.py` | All 16 pack/doctrine combinations pass; nine original countries present in each | Both | PARTIAL. Preview.10 payload. |
| F6 | RA2 startup on every map | `validate-ra2.py` (all maps, faction and movement options) | All playable maps start and AUTO deploys | Both | PARTIAL. 27/27 maps on preview packages ([ra2-mac-preview-validation.md](ra2-mac-preview-validation.md), [todo/2026-09-03.md](../todo/2026-09-03.md)). |
| F7 | RA2 spectator and replay view | Headless bot-vs-bot RA2 match (`scripts/balance_harness.py run --campaign smoke`) and playback of a saved RA2 replay | Observer UI loads; match completes; replay plays | Both | PASS on the development build after the observer-chrome fix (todo/2026-09-28.md); previously every RA2 spectator view crashed on its first frame. |
| F8 | Balance baseline recorded | `python scripts/balance_harness.py run --campaign baseline-2026-09 ...` | Campaign completes with zero crashes/hangs; report reviewed; any faction outside its confidence band has an owner and a tuning plan. Informational, not a win-rate threshold | Both | PASS for the baseline itself ([balance-baseline-2026-09.md](balance-baseline-2026-09.md)); tuning is a later milestone. |
| F9 | Saudi Arabia and Yemen in RA2 | Only when their RA2 packs land | Their own F2–F5 checks pass; catalog RA2 availability updated | Both | NOT RUN (later milestone; Classic availability is unaffected). |
| F10 | Classic replay playback | `python scripts/balance_harness.py run --campaign replay-probe ...` then `replay` with the same arguments; or save any Classic skirmish replay and open it from the replay browser | The replay plays to its end without "out of sync" and reproduces the recorded telemetry exactly | Both | FAIL. Every headless Classic bot-vs-bot replay tried (World War III and AI Assistant Only profiles, stock map, with and without the telemetry script, normal speed and unmodified manifests) goes out of sync on playback frame 2; RA2 replays recorded the same way reproduce exactly (todo/2026-09-28.md). Human-hosted Classic replays have not been checked. |

## G. Promotion

| ID | Check | How | Pass criterion | Platform | Status and evidence |
|---|---|---|---|---|---|
| G1 | Per-platform coverage | Review A–F per platform | Windows and Mac are promoted independently; neither is inferred from the other or from a development build | Both | NOT RUN. |
| G2 | Release publication | Create the GitHub release and upload exactly the indexed artifacts — only with explicit approval | Uploaded digests equal the index | Both | NOT RUN. |
| G3 | Website manifest | Update `apps/web/lib/release.ts` and deploy — only with explicit approval, after G2 and the clean-install walkthrough | Download page links resolve to the verified artifacts; no hosted CI is added | Web | NOT RUN (website still on alpha.13). |
