# Repeatable releases

`scripts/release.py` is the stable release entry point. Platform-specific
details live in `packaging/release-plan.json`, model inputs live in
`packaging/ai-pack.lock.json`, and the existing Windows and macOS packagers do
the native work. This keeps a release repeatable when game features, model
versions, or installer contents change.

## Before building

Use the same committed product and engine-submodule revisions on every host.
Release builds reject a dirty worktree by default. `--allow-dirty` exists for
local packaging experiments and should not be used for a public release.

Inspect the native plan without creating artifacts:

```powershell
python scripts/release.py plan --version 0.1.0-alpha.11 --target windows-x64
```

Validate the model lock without downloading its approximately 1.7 GiB payload:

```powershell
python scripts/ai_pack.py validate
```

## Windows release

Run on Windows 10/11 x64 with the repository prerequisites and NSIS installed:

```powershell
python scripts/release.py build --version 0.1.0-alpha.11 --target windows-x64
```

This runs the full checks, creates the portable ZIP and setup executable, smoke
tests both, and writes `artifacts/releases/OpenRA-AI-0.1.0-alpha.11-release-index.json`.

The Windows target builds its local AI pack by default because the guided
installer offers Local AI as its recommended option. The target-specific pack
contains both the pinned models and the pinned Windows inference executables.
Downloads are cached by SHA-256 under `artifacts/download-cache/ai-pack`, so
subsequent builds reuse identical inputs. `--include-ai-pack` remains available
for targets that do not opt in through the release plan.

## macOS release

The final Mac artifact cannot be produced on Windows. The packager compiles
AppKit launchers, creates an `.app` and DMG with `iconutil` and `hdiutil`, runs
`codesign`, submits with `xcrun notarytool`, and staples the result. PyInstaller
also creates executables only for its host operating system.

Use an Apple Silicon Mac for the release host. Clone the same commit including
submodules, run the local setup, then set Apple credentials outside the
repository:

```bash
export MACOS_DEVELOPER_IDENTITY="Developer ID Application: Example (TEAMID)"
export MACOS_DEVELOPER_TEAM_ID="TEAMID"
export MACOS_DEVELOPER_USERNAME="release@example.com"
export MACOS_DEVELOPER_PASSWORD="@keychain:OPENRA_AI_NOTARY"
python3 scripts/release.py build --version 0.1.0-alpha.11 --target macos-arm64
```

Without those variables, the same command produces an ad-hoc-signed DMG for
local testing. A public download should always be Developer-ID signed,
notarized, stapled, and tested on a second Mac.

After copying the Windows and macOS artifacts into the same release directory,
regenerate and verify the combined index:

```bash
python3 scripts/release.py index --version 0.1.0-alpha.11
python3 scripts/release.py verify --version 0.1.0-alpha.11
```

## Updating the AI pack

Change an AI component only by updating all of its locked fields: upstream
revision, HTTPS URL, exact byte length, SHA-256, destination, and license. Then:

```powershell
python scripts/ai_pack.py validate
python scripts/ai_pack.py fetch
python scripts/ai_pack.py build --release-version 0.1.0-alpha.11 --target windows-x64
```

The output is
`OpenRA-AI-AI-Pack-<version>-<target>.zip`. Model inputs are locked in
`packaging/ai-pack.lock.json`; platform runtime archives are locked separately
in `packaging/ai-runtime.lock.json` so a runtime update cannot silently change
the model payload or another target.

Never replace a file at an existing pinned URL without changing the pack
version. Keep model notices with the pack and audit new voice data separately
from the inference code license.
