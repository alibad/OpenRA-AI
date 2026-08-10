# Local scripts

All repository-wide validation, build, packaging, signing, and release commands
live here. These scripts are the replacement for hosted workflows.

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
  DMG. Set `MACOS_DEVELOPER_IDENTITY`, `MACOS_DEVELOPER_TEAM_ID`,
  `MACOS_DEVELOPER_USERNAME`, and `MACOS_DEVELOPER_PASSWORD` locally to sign,
  notarize, and staple the DMG; otherwise it creates an ad-hoc-signed test build.
- `smoke-windows-package.ps1 -RequireAI` unpacks that ZIP, starts a real
  headless match using only bundled executables, verifies the live bridge and
  AI response, and cleans up its processes.
