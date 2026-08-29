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
python scripts/release.py plan --version 0.1.0-alpha.14 --target windows-x64
```

Validate the model lock without downloading its approximately 1.7 GiB payload:

```powershell
python scripts/ai_pack.py validate
```

## Windows release

Run on Windows 10/11 x64 with the repository prerequisites and NSIS installed:

```powershell
python scripts/release.py build --version 0.1.0-alpha.14 --target windows-x64 --official
```

This runs the full checks, creates the portable ZIP and setup executable, smoke
tests both, and writes `artifacts/releases/OpenRA-AI-0.1.0-alpha.14-release-index.json`.
`--official` also makes the release fail unless every shipped OpenRA AI
executable and the final NSIS setup have a valid, timestamped Authenticode
signature. Omit `--official` only for local development packages.

Official signing uses `signtool.exe` from the Windows 10/11 SDK, NSIS 3.08 or
newer, and a code-signing certificate whose private key is already protected by
the Windows certificate store, a hardware token, or a provider KSP. Configure only
non-secret selectors in the release shell:

```powershell
$env:WINDOWS_SIGNING_CERTIFICATE_THUMBPRINT = "40_CHARACTER_SHA1_THUMBPRINT"
$env:WINDOWS_SIGNING_CERTIFICATE_STORE = "CurrentUser" # or LocalMachine
$env:WINDOWS_SIGNING_TIMESTAMP_URL = "https://timestamp.digicert.com"
python scripts/release.py build --version 0.1.0-alpha.14 --target windows-x64 --official
```

The certificate must be present under `Cert:\CurrentUser\My` (or
`Cert:\LocalMachine\My`) with an accessible private key and a publicly trusted
code-signing chain. The shipped companion, local runtime, game, server,
utility, product launcher, NSIS-generated uninstaller, and final setup
executable are all signed and timestamped. The scripts intentionally do not
accept PFX files or passwords.
`WINDOWS_SIGNTOOL_PATH` may select an SDK `signtool.exe` when it is
not on `PATH`; never put certificates, private keys, passwords, provider tokens,
or timestamp credentials in this repository.

No Windows certificate/provider is configured on the current Mac release host.
Before another official Windows installer can be published, obtain an OV/EV
Authenticode certificate or managed signing provider that exposes its key
through the Windows certificate store/KSP, provision it on the Windows release
host, and pass the official smoke tests. The published alpha.13 Windows setup
is checksum-valid but unsigned and must not be described as Authenticode-signed.

The Windows target builds its local AI pack by default because the guided
installer offers Local AI as its recommended option. The target-specific pack
contains both the pinned models and the pinned Windows inference executables.
Downloads are cached by SHA-256 under `artifacts/download-cache/ai-pack`, so
subsequent builds reuse identical inputs. `--include-ai-pack` remains available
for targets that do not opt in through the release plan.

## macOS release

The final Mac artifact cannot be produced on Windows. The packager compiles
AppKit launchers, gives the managed .NET apphost only the JIT entitlement
required by the hardened runtime, creates an `.app` and DMG with `iconutil` and
`hdiutil`, signs the companion, app, embedded runtime, and DMG with `codesign`,
submits with `xcrun notarytool`, and staples the result. PyInstaller also creates
executables only for its host operating system. If the host uses Homebrew's
.NET build, the packager bundles its Brotli dependency, rewrites it to an
app-relative path, and rejects any other package-manager dependencies.

Use an Apple Silicon Mac for the release host. Clone the same commit including
submodules, run the local setup, then store notarization credentials in the
login Keychain and set only the certificate identity and Keychain profile
outside the repository:

```bash
xcrun notarytool store-credentials OPENRA_AI_NOTARY \
  --apple-id "release@example.com" \
  --team-id "TEAMID" \
  --keychain "$HOME/Library/Keychains/login.keychain-db"
export MACOS_DEVELOPER_IDENTITY="Developer ID Application: Example (TEAMID)"
export MACOS_NOTARY_PROFILE="OPENRA_AI_NOTARY"
export MACOS_NOTARY_KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"
python3 scripts/release.py build --version 0.1.0-alpha.14 --target macos-arm64
```

The packager also accepts `MACOS_DEVELOPER_TEAM_ID`,
`MACOS_DEVELOPER_USERNAME`, and `MACOS_DEVELOPER_PASSWORD` for legacy local
setups, but the Keychain profile avoids exposing the app-specific password to
the shell environment.

Without those variables, the same command produces an ad-hoc-signed DMG for
local testing. A public download should always be Developer-ID signed,
notarized, stapled, and tested on a second Mac.

After copying the Windows and macOS artifacts into the same release directory,
regenerate and verify the combined index:

```bash
python3 scripts/release.py index --version 0.1.0-alpha.14
python3 scripts/release.py verify --version 0.1.0-alpha.14
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
