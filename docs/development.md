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
The companion will call named capabilities through BeTenshi. OpenAI can be the
initial backend while the game-facing contracts remain compatible with a local
model later.

## Releases

Release tooling will:

1. verify a clean worktree and pinned submodules;
2. run local tests;
3. build Windows and macOS packages;
4. sign and notarize where applicable;
5. generate checksums and a release manifest;
6. require explicit confirmation before uploading a GitHub release.

No release occurs implicitly after a push.
