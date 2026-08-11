# OpenRA adapter

The pinned engine fork exposes `RLBridge.Observe`, a unary, read-only gRPC
method for the local human player. `CompanionBridge` serializes the latest
snapshot on the game thread every ten ticks and serves immutable clones from
port 9998 when `OPENRA_AI_COMPANION=1`.

`RLBridge.ExecuteCompanionActions` accepts only proposals that the player has
confirmed through the companion. It applies idempotency, stale-tick, queue,
single-player, action-allowlist, actor-ownership, capability, item, and map-bound
checks on the game thread before issuing any normal synchronized player order.

`RLBridge.UpdateCompanionThreat` refreshes the native 0–100 threat bar without
refreshing or extending the lifetime of the current companion message.

`RLBridge.CaptureCompanionFrame` captures a bounded PNG from the player's
already fogged render buffer on the game thread. The spatial observation also
supports a full-map tactical image; unexplored resource density and non-visible
enemy actors are excluded before leaving the engine.

For autonomous headless evaluation, multi-session `Observe` now reads the
requested session under that session's tick lock, and `FastAdvance` accepts the
same 19-action safe gameplay allowlist. This path is scoped to an explicitly
created disposable session and is not exposed by the live companion port.

The bridge:

- respects the player's fog of war;
- does not pause or advance the world;
- accepts at most twelve allowlisted commands in one confirmed request;
- remains off in the editor, shell map, replay, and normal launches where the
  environment flag is absent.

The Python adapter is `openra_ai_companion.bridge.OpenRABridge`; its generated
client bindings come from the proto pinned in `engine/openra`.
