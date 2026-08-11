# Red Sea 2026 vertical slice

The first playable cut adds **Saudi Arabia** and **Yemen** to the Red Alert
country selector. It proves faction identity, country-gated units, native bot
production, source-dated Earth missions, original visual direction, and an
original sound pipeline before the full standalone expansion is split from the
base `ra` mod.

## Play it

After running `scripts/setup.ps1`, double-click:

```text
Play-Red-Sea-2026.cmd
```

The launcher generates and validates `Jizan Corridor` on first use, installs it
as a normal OpenRA map, and opens the game. Choose **Saudi Arabia** or **Yemen**
in the lobby. Pass `-Regenerate` to rebuild the Earth package.

## Live prototype roster

Saudi Arabia:

- M1A2S: durable, expensive medium-tech main battle tank;
- Mobile Air Defense System: radar-guided long-range anti-air platform.

Yemen:

- Armed Technical: inexpensive high-speed raider;
- Mobile Missile Launcher: fragile, mobile long-range strike system;
- Samad Drone: low-cost one-payload strike aircraft.

The prototype actors reuse existing Red Alert render sequences so mechanics,
faction gating, balance, and AI behavior can be tested before final sprite
sheets replace them. The custom launch, intercept, and drone-strike sounds are
already original assets.

## Scenario boundary

Each real-world scenario stores a factual cutoff, sources, country profiles,
authored objectives, and an editorial boundary in `openra-ai-manifest.json`.
The factual background is source-dated; objectives, force composition, timing,
distances, and outcomes are declared gameplay abstractions.

The first two contracts are:

- `jizan-corridor-2026`;
- `hodeidah-lifeline-2026`.

`Jizan Corridor` currently launches as a validated geographic skirmish with the
full briefing contract. Lua objective phases, convoy actors, final country
sprites, native-language unit voices, and the dedicated `redsea` mod shell are
the next production layer.
