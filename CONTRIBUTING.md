# Contributing

OpenRA AI is early-stage. Keep changes small, explain product consequences,
and validate them locally before committing.

## Ground rules

- Do not add GitHub Actions or other hosted CI workflows.
- Do not commit API keys, downloaded game assets, geographic caches, generated
  maps, or packaged releases.
- Keep OpenRA engine changes in the `engine/openra` submodule.
- Keep model-provider details behind the companion service boundary.
- Preserve fog of war and never expose information unavailable to the player.
- Prefer deterministic, seeded world generation and record source attribution.

## Local checks

```powershell
./scripts/check.ps1
```
Component-specific checks will be added beside each application or service.
