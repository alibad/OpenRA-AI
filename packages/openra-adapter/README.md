# OpenRA adapter

The pinned engine fork now exposes `RLBridge.Observe`, a unary, read-only gRPC
method for the local human player. `CompanionBridge` serializes the latest
snapshot on the game thread every ten ticks and serves immutable clones from
port 9998 when `OPENRA_AI_COMPANION=1`.

The bridge:

- respects the player's fog of war;
- does not pause or advance the world;
- accepts no companion game orders;
- remains off in the editor, shell map, replay, and normal launches where the
  environment flag is absent.

The Python adapter is `openra_ai_companion.bridge.OpenRABridge`; its generated
client bindings come from the proto pinned in `engine/openra`.
