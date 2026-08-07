# Local launcher

The first product launcher is deliberately small and auditable. It installs an
optional `.oramap`, starts the observation-only spoken companion in the
background, enables the engine bridge, and launches Red Alert:

```powershell
./scripts/setup.ps1
./apps/launcher/Start-OpenRAAI.ps1 -Map ./generated/missions/riyadh-crossing-42.oramap
```

Use `-NoSpeech` for text-only companion logs. During a match, a separate shell
can run `openra-ai-companion voice` for a four-second voice question. The
watcher exits when OpenRA exits.

OpenRA will offer its normal content installer on first launch. The launcher
does not redistribute proprietary Red Alert game assets. A signed Windows UI
and notarized macOS wrapper can replace this script later without changing the
worldgen, companion, or engine contracts.
