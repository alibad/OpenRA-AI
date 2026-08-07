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

## Development

All validation, builds, packaging, and releases are intentionally local.
This repository does not use GitHub Actions.

Run the repository checks from PowerShell:

```powershell
./scripts/check.ps1
```

See [Local development](docs/development.md) and
[Architecture](docs/architecture.md).

## License

OpenRA AI is licensed under GPL-3.0. Third-party datasets, game assets, and
dependencies retain their own licenses and attribution requirements.

