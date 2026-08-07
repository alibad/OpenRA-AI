# OpenRA adapter

This package owns the boundary between OpenRA and the rest of OpenRA AI:

- observations and event interrupts;
- fog-respecting player state;
- session lifecycle;
- generated map installation and validation;
- future high-level game intents.

It will extract the useful platform concepts from OpenRA-RL while presenting a
small, stable contract designed for the player-facing product.

