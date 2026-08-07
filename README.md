# OpenRA AI

OpenRA AI explores a smooth, interruptible AI companion for OpenRA and a new
way to turn places on Earth into playable RTS maps, skirmishes, and missions.

The project is independent and is not affiliated with or endorsed by the
OpenRA project or Electronic Arts.

## Product direction

The AI belongs in the rhythm of the game:

- it notices a genuinely useful battlefield detail and says it briefly;
- the player can hold a key and ask about the current match;
- speech stops immediately when the player interrupts, mutes, or disables it;
- no modal dialogs, chat dashboards, or configuration modes interrupt play.

The first version is talk-only. It observes and responds, but does not control
units. Game commands can be explored after the companion experience is useful,
trustworthy, and fast.

## Earth missions

A player will be able to choose a location, scale, game style, and optional
story seed. OpenRA AI will convert geographic features into stylized OpenRA
terrain, validate playability, and generate a skirmish or Lua-scripted mission.

The generated result is an ordinary OpenRA map package that can be opened in
OpenRA's map editor and changed by hand.

See [Earth mission generation](docs/earth-missions.md).

## Repository layout

```text
apps/
  launcher/          Installed Windows/macOS launcher and game manager
  web/               Map picker, mission creator, downloads, and deep links
engine/
  openra/            Pinned OpenRA engine fork
packages/
  contracts/         Versioned messages shared across every component
  openra-adapter/    OpenRA observations, events, and map packaging
services/
  companion/         Insight selection, conversation, voice, and AI routing
  worldgen/          Geographic terrain and mission generation
scripts/             Local development, validation, build, and release tools
docs/                Product and architecture decisions
```

## Related projects

- [OpenRA](https://github.com/OpenRA/OpenRA) is the GPL-3.0 RTS engine.
- [OpenRA-RL](https://github.com/yxc20089/OpenRA-RL) provides useful engine
  observations, actions, and agent-environment foundations.
- [alibad/OpenRA](https://github.com/alibad/OpenRA) is the engine fork used by
  this project.
- [alibad/OpenRA-RL](https://github.com/alibad/OpenRA-RL) remains the research
  platform fork and reference implementation.

OpenRA AI is a separate product repository so its launcher, web application,
companion, and world-generation pipeline can evolve without treating
OpenRA-RL as the product boundary.

## Play the Windows alpha

Download the latest Windows ZIP from the project releases, extract it, and
double-click `Play-OpenRAAI.cmd`. The bundle contains the pinned OpenRA engine,
the AI companion, and a generated Riyadh skirmish. On first launch it downloads
OpenRA's checksum-verified Red Alert quick-install content from OpenRA's
official mirror list.

During the match:

- hold `F8`, ask a question, and release it to hear a short answer;
- tap `F9` to mute or unmute the companion;
- tap `F10` to disable or enable the companion;
- drag any generated `.oramap` onto `Play-OpenRAAI.cmd` to play that map.

The companion expects an OpenAI-compatible AI layer on
`http://127.0.0.1:4000`. Provider credentials stay in that layer. If it is
offline, the game still runs and deterministic battlefield alerts remain
available in the companion log.

## Build it locally

On Windows, install the local dependencies and build the pinned engine fork:

```powershell
./scripts/setup.ps1
```

Generate and validate a playable Earth map:

```powershell
./.venv/Scripts/openra-ai-worldgen.exe generate --lat 24.7136 --lon 46.6753 --title "Riyadh Crossing" --seed 42
./apps/launcher/Start-OpenRAAI.ps1 -Map ./generated/missions/riyadh-crossing-42.oramap
```

The launcher installs OpenRA's supported 2008 freeware Red Alert package on
first launch after checking its published checksum. The game data is not stored
in this repository or bundled in the release ZIP.

Start the product site and browser mission studio:

```powershell
cd apps/web
npm run dev
```

## Models

The game never reads an OpenAI key. It calls named capabilities through a
private AI layer:

| Capability | AI-layer route | Initial backend |
| --- | --- | --- |
| short battlefield language | `gpt-5.5` | OpenAI GPT-5.5 |
| voice input | `openai-transcribe` | OpenAI transcription |
| spoken response | `openai-tts` | OpenAI text-to-speech |

See [Model routing](docs/models.md) for the boundary and local-model migration.

## Development

All validation, builds, packaging, and releases are intentionally local.
This repository does not use GitHub Actions.

Run the repository checks from PowerShell:

```powershell
./scripts/check.ps1
```

Add `-FullEngine` to lint every Red Alert rule and bundled map. All validation,
builds, packaging, and releases are local; this repository intentionally has
no GitHub workflow configuration.

Build and smoke-test the portable Windows ZIP locally:

```powershell
./scripts/package-windows.ps1
./scripts/smoke-windows-package.ps1
```

See [Local development](docs/development.md) and
[Architecture](docs/architecture.md).

## License

OpenRA AI is licensed under GPL-3.0. Third-party datasets, game assets, and
dependencies retain their own licenses and attribution requirements.
