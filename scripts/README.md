# Local scripts

All repository-wide validation, build, packaging, signing, and release commands
live here. These scripts are the replacement for hosted workflows.

- `setup.ps1` installs local dependencies and builds the pinned engine.
- `check.ps1 -FullEngine` runs product tests, web checks, engine tests, and map
  validation.
- `package-windows.ps1` creates the portable Windows x64 ZIP and checksum.
- `smoke-windows-package.ps1 -RequireAI` unpacks that ZIP, starts a real
  headless match using only bundled executables, verifies the live bridge and
  AI response, and cleans up its processes.
