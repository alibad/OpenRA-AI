# OpenRA AI

OpenRA AI adds two native experiences to OpenRA:

- an interruptible battlefield companion that notices useful changes, answers
  questions, and can speak without taking control away from the player;
- an Earth-to-battlefield workbench that turns a selected real-world location
  into an editable, playable OpenRA skirmish.

The project is independent and is not affiliated with or endorsed by the
OpenRA project or Electronic Arts.

## Download and play

### Supported builds

| Platform | Status | Download |
| --- | --- | --- |
| Windows 10/11 x64 | Playable alpha | [Download `v0.1.0-alpha.8`](https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.8/OpenRA-AI-0.1.0-alpha.8-windows-x64.zip) |
| macOS | Not packaged yet | Planned after a signed and notarized build is ready |

[See every release and its checksum](https://github.com/alibad/OpenRA-AI/releases).

### Start a match on Windows

1. Download the Windows ZIP and extract the entire folder.
2. Double-click `Play-OpenRAAI.cmd`.
3. Allow the first launch to download OpenRA's checksum-verified Red Alert
   quick-install content from OpenRA's official mirror list.
4. Start or load a match. The AI companion and Earth Mission Studio are built
   into the game menus.

Keep the extracted files together. Windows may show a security prompt because
this early alpha is not code-signed yet. The release does not contain the
original Red Alert game data; OpenRA installs its supported freeware content on
first launch.

### AI availability

The game, native map tools, and deterministic battlefield alerts work without
a model provider. Model-written answers, transcription, speech, and terrain
vision currently require an OpenAI-compatible AI layer running locally at
`http://127.0.0.1:4000`.

The game never stores a provider API key. Open **Settings > AI** to select
named model routes, control voice and notification priority, test the full
connection, and see an estimated session cost. If the AI layer is unavailable,
OpenRA keeps running normally.

### In-game controls

- Hold `Ctrl+Space`, ask a question, and release to submit it.
- Click `VOICE: ON`, or press `Ctrl+Shift+M`, to switch spoken audio off or on.
- Press `Ctrl+Shift+A` to disable or enable the companion.
- Drag any generated `.oramap` file onto `Play-OpenRAAI.cmd` to play it.

Routine observations remain text-only. Important or critical events can use
voice according to the player's settings, and speech stops immediately when
interrupted.

## Earth Mission Studio

From the OpenRA main menu, choose **World Tools > Earth Mission Studio** to:

1. search for or pin any location on Earth;
2. inspect the source imagery and detected terrain;
3. choose the battlefield scale and mission shape;
4. generate and validate a playable `.oramap`;
5. play it immediately or continue editing it in OpenRA's native map editor.

OpenRA AI interprets geographic evidence, configures OpenRA's native map
generator, and verifies tracked-unit connectivity. The result is an ordinary
OpenRA map package that remains editable by hand.

See [Earth mission generation](docs/earth-missions.md).

## Build from source

The source build currently targets Windows. Install Git, Python, Node.js 22 or
newer, and a compatible .NET SDK, then run:

```powershell
git clone --recurse-submodules https://github.com/alibad/OpenRA-AI.git
cd OpenRA-AI
./scripts/setup.ps1
./Play-OpenRAAI.cmd
```

Generate and validate a specific Earth map:

```powershell
./.venv/Scripts/openra-ai-worldgen.exe generate --lat 24.7136 --lon 46.6753 --title "Riyadh Crossing" --imagery satellite --mode playability-first --seed 42
./apps/launcher/Start-OpenRAAI.ps1 -Map ./generated/missions/riyadh-crossing-42.oramap
```

If a submodule was omitted during cloning, repair it with:

```powershell
git submodule update --init --recursive
```

See [Local development](docs/development.md) and
[Architecture](docs/architecture.md).

## Web app

The public web app lives in `apps/web`. It provides the marketing site, a
browser mission studio, and direct links to the tested game packages published
through GitHub Releases.

```powershell
cd apps/web
npm install
npm run dev
```

The web app is isolated from the engine and can be moved into its own
repository and deployment without changing the game. Release binaries should
remain versioned assets in GitHub Releases (or equivalent object storage); the
website should present their platform, version, size, checksum, and support
status instead of committing binaries to its source repository.

## Models and privacy

OpenRA AI calls named capabilities through the AI layer rather than embedding
provider credentials in the game:

| Capability | Default route | Purpose |
| --- | --- | --- |
| battlefield language | `gpt-5.5` | Short, fog-respecting tactical responses |
| terrain vision | `gpt-5.5` | Interprets selected Earth imagery for map generation |
| voice input | `openai-transcribe` | Push-to-talk transcription |
| spoken response | `openai-tts` | Interruptible speech |

The route names are configurable and can point to cloud or local models. See
[Model routing](docs/models.md) for the data boundary and local-model migration.

## Repository layout

```text
apps/
  launcher/          Windows launcher and local game manager
  web/               Product site, browser mission studio, and downloads
engine/
  openra/            Pinned OpenRA engine fork
packages/
  contracts/         Versioned messages shared across components
  openra-adapter/    OpenRA observations, events, and map packaging
services/
  companion/         Insight selection, conversation, voice, and AI routing
  worldgen/          Geographic terrain and mission generation
scripts/             Local development, validation, build, and release tools
docs/                Product and architecture decisions
```

## Development and releases

All validation, packaging, and releases run locally. This repository does not
use GitHub Actions or other hosted workflow configuration.

```powershell
./scripts/check.ps1
```

Add `-FullEngine` to validate every Red Alert rule and bundled map. Build and
smoke-test the portable Windows ZIP locally with:

```powershell
./scripts/package-windows.ps1
./scripts/smoke-windows-package.ps1
```

See [Contributing](CONTRIBUTING.md) before changing the engine submodule or
publishing a release.

## Related projects

- [OpenRA](https://github.com/OpenRA/OpenRA) is the GPL-3.0 RTS engine.
- [OpenRA-RL](https://github.com/yxc20089/OpenRA-RL) provides useful engine
  observations, actions, and agent-environment foundations.
- [alibad/OpenRA](https://github.com/alibad/OpenRA) is the engine fork used by
  this project.
- [alibad/OpenRA-RL](https://github.com/alibad/OpenRA-RL) remains the research
  platform fork and reference implementation.

## License

OpenRA AI is licensed under GPL-3.0. Third-party datasets, game assets, and
dependencies retain their own licenses and attribution requirements.
