# Contracts

Provider-neutral contracts shared by the engine adapter, companion, world
generator, launcher, and web application live under `schemas/`.

- `game-snapshot.schema.json` is the fog-respecting observation boundary.
- `geo-selection.schema.json` is the reproducible location request boundary.

Model names, API keys, provider response objects, and raw spatial tensors do
not cross these product contracts.
