# Local development

## Policy

Development, validation, packaging, and releases run locally. Do not add
`.github/workflows` or another hosted CI configuration.

The root validation script is the stable entry point:

```powershell
./scripts/check.ps1
```

As components become executable, that script will call their own checks while
preserving a single local command for contributors.

## Secrets

Do not store model-provider or geographic-data credentials in the repository.
The companion will call named capabilities through the private AI layer. OpenAI can be the
initial backend while the game-facing contracts remain compatible with a local
model later.

## Releases

The cross-platform release entry point is:

```powershell
python scripts/release.py build --version 0.1.0-alpha.11 --target windows-x64
```

On an Apple Silicon Mac, the corresponding command is:

```bash
python3 scripts/release.py build --version 0.1.0-alpha.11 --target macos-arm64
```

Release tooling will:

1. verify a clean worktree and pinned submodules;
2. run local tests;
3. build and smoke-test the Windows package;
4. require Authenticode signing for official Windows artifacts and Developer ID
   signing plus notarization for official macOS artifacts;
5. generate checksums and a release manifest;
6. upload an explicit versioned GitHub release from the local machine.

No release occurs implicitly after a push.
