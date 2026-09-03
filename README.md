# OpenRA AI

OpenRA AI adds two native experiences to OpenRA:

- an interruptible battlefield companion that notices useful changes, answers
  questions, and can speak without taking control away from the player;
- an Earth-to-battlefield workbench that turns a selected real-world location
  into an editable, playable OpenRA skirmish.

The project is independent and is not affiliated with or endorsed by the
OpenRA project or Electronic Arts.

## Download and play

### Integrated Red Alert 2 on Mac (development)

The Mac package now includes a **World War III / Red Alert 2** selector with
shared AI settings, AUTO, voice controls and the local model library. In RA2,
choose **Singleplayer → Skirmish** and one of its nine countries. The HUD shows
the configured Ask shortcut (Option+Space by default on Mac).

Your existing custom factions and capabilities remain in World War III;
they have not yet been ported to RA2. Original campaigns and Yuri's Revenge
are not included. This is an early OpenRA recreation, not the original RA2
executable or a feature-complete release. Existing website downloads do not
gain this integration until a new package is explicitly published.

The normal `scripts/package-macos.sh VERSION` command prepares the pinned
RA2 source before signing. It requires a clean, pinned engine and never bundles
proprietary RA2 archives. The in-app import uses your previously downloaded
Steam base/English depots or the private preview content library.

### Standalone RA2 preview for developers

RA2 is now available as a separate, locally built Apple Silicon preview using
the [OpenRA RA2 mod](https://github.com/OpenRA/ra2) and your own original game files.
It is **not** the RA2-inspired Experience Builder pack, and it does not require
CrossOver, Wine, or a Windows virtual machine.

With Python 3.11+, .NET 10 and the pinned engine checkout, run:

```sh
python3 scripts/build-ra2-preview.py --install --launch
```

This detects the already-downloaded Steam RA2 base/English depots on macOS.
For another legitimate installation, supply `--base-content /path/to/base`
and `--language-content /path/to/english`. The importer requires `ra2.mix`
and `language.mix`, verifies the copies, and never overwrites different
existing content. Proprietary game files stay in your private Application
Support folder, outside the app bundle and Git.

Open **Red Alert 2 Preview** in Applications, choose **Singleplayer → Skirmish**,
pick your country, then start. Select your MCV and press **F** to deploy.
The version is `0.1.0-ra2-preview.1`; the app has separate settings/saves and
does not replace OpenRA AI. Move an older preview aside before reinstalling.

This is an early OpenRA recreation, not the original executable or a
feature-complete RA2 release. AI companion/voice/AUTO, original campaigns,
and Yuri’s Revenge are not included in this preview. The app is locally
ad-hoc signed, not notarized or published on the download website.

### Supported builds

| Platform | Status | Download |
| --- | --- | --- |
| Windows 10/11 x64 | Playable alpha | [Installer](https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-0.1.0-alpha.13-windows-x64-setup.exe) · [Portable ZIP](https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-0.1.0-alpha.13-windows-x64.zip) |
| macOS 10.15+ on Apple Silicon | Playable alpha | [Signed and notarized DMG](https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-0.1.0-alpha.13-macos-arm64.dmg) · [SHA-256](https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-0.1.0-alpha.13-macos-arm64.dmg.sha256) |

[See every release and its checksum](https://github.com/alibad/OpenRA-AI/releases).
The guided installer downloads the matching
[local AI pack](https://github.com/alibad/OpenRA-AI/releases/download/v0.1.0-alpha.13/OpenRA-AI-AI-Pack-0.1.0-alpha.13-windows-x64.zip)
by default. It contains the pinned models and Windows CPU runtimes; choose an
external OpenAI-compatible provider during setup to skip it.

### Start a match on macOS

1. Open the DMG and copy **OpenRA AI.app** to Applications.
2. Launch OpenRA AI. The Developer ID-signed, notarized, and stapled package
   opens the main menu by default.
3. Allow the first launch to download OpenRA's checksum-verified Red Alert
   quick-install content from OpenRA's official mirror list.
4. Start or load a match. The AI companion and Earth Mission Studio are built
   into the game menus.

The published alpha.13 Mac build predates in-app model setup. Current builds
show the configured Hold to Ask shortcut under **Settings > AI > Voice** and
offer **Install 1.8 GB Pack** under **Settings > AI > Models**. The app verifies
every pinned model before starting its bundled Apple Silicon runtime. The game,
native AI, map tools, and deterministic alerts remain available while the pack
is not installed.

### Start a match on Windows

1. Run the Windows installer, or download and extract the entire portable ZIP.
2. Launch OpenRA AI from the Start menu, or double-click `Play-OpenRAAI.cmd`
   inside the portable package.
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
a model provider. The guided Windows installer selects **Local AI
(recommended)** by default. On macOS, install the same capability set from
**Settings > AI > Models**. Both paths download checksum-verified text/vision,
speech-recognition, and speech-synthesis models and use a signed,
platform-specific local runtime. No API key or provider usage fee is required.
The download is about 1.8 GB and needs 8 GB RAM and 5 GB free disk; 16 GB RAM is
recommended. Apple Silicon uses Metal, while the Windows runtime can run
CPU-only on an AVX2 x64 processor. Local AI on Mac requires macOS 13.3 or
newer; the base game remains available on the broader supported Mac range.

During setup, users can instead choose **External or existing
OpenAI-compatible provider**, then enter an endpoint, model name, and optional
API key. This supports hosted providers as well as local servers such as LM
Studio or Ollama. Windows protects a supplied key for the current user with
DPAPI; it is never written to the repository or game settings in plaintext.

Portable users can extract the matching target AI pack into the package's
`ai` folder. To use an external provider, save its key in a temporary text file
and run:

```powershell
.\bin\openra-ai-runtime.exe configure --mode external --endpoint https://api.openai.com/v1 --text-model gpt-4.1-mini --key-file .\provider-key.txt
```

The configuration command encrypts the key and deletes the temporary key file.
Open **Settings > AI** to control voice and notification priority and test the
connection. If the local runtime or external provider is unavailable, OpenRA
keeps running normally.

### In-game controls

- Hold `Ctrl+Space` on Windows or `Option+Space` on macOS, ask a question,
  and release to submit it.
- Ask `What strategy are we using?` or `What does turtle strategy do?` for a
  concise doctrine and its next major phases.
- Ask `What's next?`, `How are we doing?`, or `What's remaining in this game?`
  for a zero-latency live briefing. It reports the next objective, the evidence,
  and what remains to win; with AUTO off it also opens the matching `ACCEPT`
  proposal when a safe concrete step is available.
- Say `Play aggressive strategy`, `Switch to defensive strategy`, `Use naval
  strategy`, or `Use adaptive strategy` to change the delegated doctrine live.
- Click `AUTO: ON` to delegate real-time play to OpenRA's complete native bot
  stack. The companion remains the strategy and explanation layer; turning
  AUTO off immediately returns control to the player.
- Ask for a supported action, then press `Ctrl+Enter` to accept it or
  `Ctrl+Backspace` to reject it. Voice `confirm` and `cancel` still work.
- The companion can also suggest a relevant safe action when it detects low
  power, a missing harvester, critical building damage, or a nearby attack.
- Click the center AI message or its `LOG` button to open the tactical feed.
  It preserves the latest transmission plus up to 80 timestamped advice,
  alert, transcript, pending-order, and execution entries for the match.
  Contextual suggestions still require `confirm`.
- Click `VOICE: ON`, or press `Ctrl+Shift+M`, to switch spoken audio off or on.
- Press `Ctrl+Shift+A` to toggle AUTO delegation.
- Remap every AI shortcut under **Settings > Hotkeys > AI Assistant**. Every
  visible in-game instruction follows the configured binding. Companion,
  voice, model, and usage controls are grouped under four tabs in **Settings > AI**.
- Drag any generated `.oramap` file onto `Play-OpenRAAI.cmd` to play it.

Routine observations remain text-only. Important or critical events can use
voice according to the player's settings, and speech stops immediately when
interrupted.

The HUD includes a fog-respecting numeric threat bar whose color reflects the
current severity. Calm and guarded automatic messages are capped at one per minute;
high and critical threats use faster 10-second and 4-second budgets, with an
immediate message when the level escalates.

AUTO runs OpenRA's full real-time `ModularBot` behavior: economy, power,
production, harvesting, base placement, repair, support powers, expansion,
squads, counters, defense, retreats, and attacks continue every game tick
without waiting for an LLM. The companion provides the slower command layer.
In `adaptive` mode it can select OpenRA's balanced, rush, turtle, naval, or
measured profile at major fog-respecting events; explicit voice commands always
take precedence. See the [strategy doctrine](docs/ai-strategy.md).

Live companion questions and action requests use full multimodal game vision:
the player's current rendered viewport plus a generated whole-map tactical
overview. Both views preserve shroud and fog; hidden cells are black and hidden
actors or resources are never supplied. Heated automatic alerts may use the
same views, while calm observation remains structured and inexpensive.
Persistent economy, power, production, and damage alerts are rendered from
local deterministic templates and fire on state transitions, so they never
consume model tokens or repeat merely because a cooldown elapsed.

Confirmed actions are currently limited to single-player matches and at most
twelve orders per proposal. The allowlist covers movement, attack and
attack-move, harvesting, building/training/placement/cancellation, deploy,
stop, repair, sell, rally points, guard/stance, transports, power-down, and
primary-production controls. Surrender, support powers, match lifecycle, and
hidden-information access are never exposed.

### Autonomous game agent

The development build also includes a headless autonomous commander backed by
the Agents SDK, the BeTenshi AI router, and a local, stdio-only OpenRA MCP server. It receives the
same fog-respecting observations and can use the complete safe gameplay
allowlist without confirmation because starting `autoplay` is explicit blanket
authorization for that one local test match. The MCP server deliberately does
not expose surrender, match destruction, arbitrary code, files, or external
connectors.

The default route is `local-coder` through `http://127.0.0.1:4000`. Local mode
disables SDK tracing, never loads `OPENAI_API_KEY`, and has no hosted-provider
fallback. A hosted run remains an explicit opt-in with `--provider openai`.

```powershell
./.venv/Scripts/openra-ai-companion.exe autoplay --provider local --model local-coder --opponent beginner --evidence-dir ./.artifacts/autoplay/manual
./.venv/Scripts/python.exe services/companion/evals/grade_victory.py ./.artifacts/autoplay/manual
./.venv/Scripts/openra-ai-companion.exe learn --provider local --model local-coder --opponent beginner --attempts 3 --evidence-root ./.artifacts/autoplay/learning-runs
```

`learn` repeats disposable matches until it records a verified victory or reaches
the attempt limit. Every material decision is logged with its evidence and
expected result. After each match the companion reviews the resource curve,
combat trades, build/train actions, and timeline; stores the full review under
`.artifacts/autoplay/learning`; and injects the resulting lessons into the next
attempt. The local admin page exposes the cumulative record, latest lessons, and
recent decision feed. Storage above OpenRA's warning threshold is treated as an
economy transition: if no silo is already being built, both advisory and AUTO
modes prioritize building and placing one.

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

## OpenRA: World War III

**World War III** is the modern global-conflict mod being built on this fork.
Its first playable theater is the scripted Red Sea 2026 vertical slice:
Saudi Arabia and Yemen, original directional sprites, Arabic vehicle responses,
bilingual campaign radio, native bot production weights, and a source-dated
three-mission campaign slice. After setup, run `Play-Red-Sea-2026.cmd` to generate,
validate, install, and open Jizan Corridor, or run
`.\scripts\play-red-sea-2026.ps1 -Mission hodeidah-lifeline-2026` to play the
Yemen-side Hodeidah Lifeline mission.

The third mission is available with
`.\scripts\play-red-sea-2026.ps1 -Mission bab-al-mandab-passage-2026` and adds
Tech Center progression, coastal reconnaissance, actual civilian ship lanes,
deadlock recovery, and a final combined-arms passage defense.

See the [Red Sea 2026 theater](docs/red-sea-2026.md).

### Experience and faction packs

New installs use the **World War III** profile, which enables the five built-in
modern factions and the complete reusable capability portfolio. Select
**AI Assistant Only** in **Workshop > Experience Builder** to run the classic
base simulation without those optional packs. Changing a profile activates
files already shipped with the game, resolves dependencies, and restarts the
mod; it does not download the original source mod. External community packs
are a separate import action. They are restricted to validated data, copied
into the user's OpenRA support directory, and can be removed without changing
the base installation. See the
[Experience Composer guide](docs/experience-composer/README.md).

OpenRA AI does **not** bundle Red Alert 2, Yuri's Revenge, or their proprietary
factions, maps, art, audio, or game data. Some capability modules adapt or cite
GPL-compatible architecture from the separate OpenRA Red Alert 2 project, but
those reusable mechanics are not a packaged Red Alert 2 game or mod.

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
| battlefield language | `local-coder` | Routed local tactical language and action interpretation |
| structured battlefield view | `local-coder` | Fog-respecting snapshot and tactical overview interpretation |
| voice input | `local-whisper` | Local push-to-talk transcription |
| spoken response | `local-kokoro` | Local interruptible speech |

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
