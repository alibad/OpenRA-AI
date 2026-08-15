# Local scripts

All repository-wide validation, build, packaging, signing, and release commands
live here. These scripts are the replacement for hosted workflows.

- `release.py` is the stable release entry point on both Windows and macOS. It
  validates the host, invokes the platform packager and smoke tests, and writes
  one checksummed release index. See `docs/releasing.md`.
- `ai_pack.py` validates, fetches, and assembles the platform-neutral local AI
  model pack from `packaging/ai-pack.lock.json`. Every input has a pinned source
  revision, byte length, and SHA-256.
- `setup.ps1` installs local dependencies and builds the pinned engine.
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
