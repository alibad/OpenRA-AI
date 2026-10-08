# Local scripts

All repository-wide validation, build, packaging, signing, and release commands
live here. These scripts are the replacement for hosted workflows.

- `release.py` is the stable release entry point on both Windows and macOS. It
  validates the host, invokes the platform packager and smoke tests, and writes
  one checksummed release index. See `docs/releasing.md`.
- `ai_pack.py` validates, fetches, and assembles the platform-neutral local AI
  model pack from `packaging/ai-pack.lock.json`. Every input has a pinned source
  revision, byte length, and SHA-256. Its `prepare-runtime` command also stages
  pinned platform inference binaries; the Mac target builds whisper.cpp from
  its checksum-pinned source release because upstream does not publish a Mac
  server executable.
- `setup.ps1` installs local dependencies and builds the pinned engine.
- `content_catalog.py` validates the shared faction catalog (structure, rules
  paths, public deep links) and stages it byte-identically into packages.
- `validate-faction-catalog.py` checks the catalog against each mode's merged
  engine rules (Classic and a data-only integrated RA2) with the engine's
  `--check-faction-catalog` utility. `verify-catalog-package-layout.py` proves
  staged Windows and macOS layouts resolve the catalog for the game and the
  companion. See `docs/in-game-catalog.md`.
- `check.ps1 -FullEngine` runs product tests, web checks, engine tests, and map
  validation.
- `package-windows.ps1` creates both the portable Windows x64 ZIP and the
  branded per-user setup executable, with checksums for each. Pass
  `-SkipInstaller` only when intentionally building the portable archive alone.
- `smoke-windows-installer.ps1` silently installs the setup executable into a
  temporary directory, verifies its game, companion, launcher, and icon, then
  uninstalls it.
- `package-macos.sh` runs locally on macOS to produce the branded `.app` and
  DMG. Set `MACOS_DEVELOPER_IDENTITY` and `MACOS_NOTARY_PROFILE` locally to
  sign, notarize, and staple the DMG using a validated `notarytool` Keychain
  profile; otherwise it creates an ad-hoc-signed test build. Legacy Apple ID
  environment variables remain supported for existing local setups.
- `smoke-macos-package.sh` mounts the DMG read-only, verifies its checksum,
  required payload, and code signature, then detaches it.
- `smoke-windows-package.ps1 -RequireAI` unpacks that ZIP, starts a real
  headless match using only bundled executables, verifies the live bridge and
  AI response, and cleans up its processes.
- `balance_harness.py` runs seeded, parallel, headless bot-vs-bot campaigns
  from `balance_campaigns.json` and writes replays, per-match telemetry,
  `summary.json` and `report.md`. It changes only disposable map copies and a
  private manifest copy (unthrottled simulation); see its module docstring and
  `docs/balance-baseline-2026-09.md`.
- `native_fixture.py` holds the shared game-time budgets, exact-destination
  movement checks and Windows-safe paths/links used by the RA2 validators.
- `build-usa-concept-board.py` renders the United States (`usa`) Checkpoint B
  concept and silhouette boards from original low-poly geometry in
  `usa_concept_actors.py` (renderer in `usa_concept_models.py`, OpenRA
  player-colour remap port in `usa_concept_render.py`). It needs a built engine
  checkout and a read-only directory containing owned Red Alert content
  (`Content/ra/v2`) for palettes, terrain statistics and stock scale
  references; boards and a checksummed `manifest.json` are written to the
  engine's `docs/concept/usa/`. Concept art only - it produces no SHP, rules
  or sequences.
