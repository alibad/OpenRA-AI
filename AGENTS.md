# OpenRA AI game guidance

- Implement and validate game UX directly in the OpenRA codebase; Figma is not part of this product workflow.
- Keep AI interactions native to the game, interruptible, non-blocking, and subordinate to gameplay.
- Keep Earth-to-Battlefield output playable by relying on OpenRA terrain, pathing, resource, spawn, and map-validation systems.
- Prefer local test scripts and local game runs. Never add GitHub Actions or hosted workflow files.
