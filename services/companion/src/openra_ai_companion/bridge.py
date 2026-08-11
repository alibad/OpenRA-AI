from __future__ import annotations

import json
from typing import Any

import grpc
from google.protobuf.json_format import MessageToDict

from .generated import rl_bridge_pb2, rl_bridge_pb2_grpc
from .models import ActionCommand, ActionReceipt, GameSnapshot, VisionFrame


ACTION_TYPES = {
    "move": rl_bridge_pb2.MOVE,
    "attack_move": rl_bridge_pb2.ATTACK_MOVE,
    "attack": rl_bridge_pb2.ATTACK,
    "stop": rl_bridge_pb2.STOP,
    "harvest": rl_bridge_pb2.HARVEST,
    "build": rl_bridge_pb2.BUILD,
    "train": rl_bridge_pb2.TRAIN,
    "deploy": rl_bridge_pb2.DEPLOY,
    "sell": rl_bridge_pb2.SELL,
    "repair": rl_bridge_pb2.REPAIR,
    "place_building": rl_bridge_pb2.PLACE_BUILDING,
    "cancel_production": rl_bridge_pb2.CANCEL_PRODUCTION,
    "set_rally_point": rl_bridge_pb2.SET_RALLY_POINT,
    "guard": rl_bridge_pb2.GUARD,
    "set_stance": rl_bridge_pb2.SET_STANCE,
    "enter_transport": rl_bridge_pb2.ENTER_TRANSPORT,
    "disguise": rl_bridge_pb2.DISGUISE,
    "infiltrate": rl_bridge_pb2.INFILTRATE,
    "demolish": rl_bridge_pb2.DEMOLISH,
    "unload": rl_bridge_pb2.UNLOAD,
    "power_down": rl_bridge_pb2.POWER_DOWN,
    "set_primary": rl_bridge_pb2.SET_PRIMARY,
}

DEFAULT_INTERRUPTS = (
    "enemy_spotted",
    "building_discovered",
    "under_attack",
    "unit_destroyed",
    "own_building_destroyed",
    "enemy_building_destroyed",
    "production_complete",
    "game_over",
)


class OpenRABridge:
    def __init__(self, address: str = "127.0.0.1:9999", session_id: str = "", timeout: float = 3.0):
        self.address = address
        self.session_id = session_id
        self.timeout = timeout
        self.channel = grpc.insecure_channel(address)
        self.stub = rl_bridge_pb2_grpc.RLBridgeStub(self.channel)

    def observe(self) -> GameSnapshot:
        if not hasattr(self.stub, "Observe"):
            raise RuntimeError("The engine bridge does not expose Observe; update the pinned OpenRA fork.")
        try:
            message = self.stub.Observe(rl_bridge_pb2.StateRequest(session_id=self.session_id), timeout=self.timeout)
        except grpc.RpcError as exc:
            raise RuntimeError(f"OpenRA companion bridge unavailable at {self.address}: {exc.code().name}") from exc
        value: dict[str, Any] = MessageToDict(message, preserving_proto_field_name=True)
        return GameSnapshot.from_dict(value)

    @staticmethod
    def _command_message(command: ActionCommand) -> rl_bridge_pb2.Command:
        return rl_bridge_pb2.Command(
            action=ACTION_TYPES[command.action],
            actor_id=command.actor_id,
            target_actor_id=command.target_actor_id,
            target_x=command.target_x,
            target_y=command.target_y,
            item_type=command.item_type,
            queued=command.queued,
            ticks=command.ticks,
        )

    def state(self) -> dict[str, Any]:
        message = self.stub.GetState(rl_bridge_pb2.StateRequest(session_id=self.session_id), timeout=self.timeout)
        return MessageToDict(message, preserving_proto_field_name=True)

    def update_companion_status(
        self,
        state: str,
        message: str,
        *,
        enabled: bool = True,
        muted: bool = False,
    ) -> bool:
        if not hasattr(self.stub, "UpdateCompanionStatus"):
            return False
        try:
            response = self.stub.UpdateCompanionStatus(
                rl_bridge_pb2.CompanionStatus(
                    state=state,
                    message=message,
                    enabled=enabled,
                    muted=muted,
                ),
                timeout=self.timeout,
            )
        except grpc.RpcError:
            return False
        return bool(response.accepted)

    def update_threat_status(self, score: int, level: str, reason: str) -> bool:
        if not hasattr(self.stub, "UpdateCompanionThreat"):
            return False
        try:
            response = self.stub.UpdateCompanionThreat(
                rl_bridge_pb2.CompanionThreat(
                    score=max(0, min(100, int(score))),
                    level=level,
                    reason=reason,
                ),
                timeout=self.timeout,
            )
        except grpc.RpcError:
            return False
        return bool(response.accepted)

    def capture_frame(self) -> VisionFrame:
        if not hasattr(self.stub, "CaptureCompanionFrame"):
            raise RuntimeError("The engine bridge does not support live vision; update the pinned OpenRA fork.")
        try:
            message = self.stub.CaptureCompanionFrame(
                rl_bridge_pb2.StateRequest(session_id=self.session_id),
                timeout=max(5.0, self.timeout),
            )
        except grpc.RpcError as exc:
            raise RuntimeError(f"OpenRA live vision unavailable at {self.address}: {exc.code().name}") from exc
        if not message.png:
            raise RuntimeError("OpenRA returned an empty vision frame")
        return VisionFrame(
            png=bytes(message.png),
            tick=int(message.tick),
            width=int(message.width),
            height=int(message.height),
            scope=str(message.scope),
        )

    def execute_actions(
        self,
        request_id: str,
        expected_tick: int,
        commands: tuple[ActionCommand, ...],
    ) -> ActionReceipt:
        """Submit an explicitly confirmed proposal to the engine safety boundary."""
        if not hasattr(self.stub, "ExecuteCompanionActions"):
            raise RuntimeError("The engine bridge does not support companion actions; update the pinned OpenRA fork.")
        request = rl_bridge_pb2.CompanionActionRequest(
            request_id=request_id,
            expected_tick=expected_tick,
            commands=[
                self._command_message(command)
                for command in commands
            ],
        )
        try:
            message = self.stub.ExecuteCompanionActions(request, timeout=max(3.0, self.timeout))
        except grpc.RpcError as exc:
            raise RuntimeError(f"OpenRA action bridge unavailable at {self.address}: {exc.code().name}") from exc
        value: dict[str, Any] = MessageToDict(message, preserving_proto_field_name=True)
        return ActionReceipt.from_dict(value)

    def create_session(self, map_name: str, bots: str, seed: int = 0) -> str:
        """Create and select a headless multi-session match."""
        try:
            message = self.stub.CreateSession(
                rl_bridge_pb2.CreateSessionRequest(map_name=map_name, bots=bots, seed=seed),
                timeout=max(5.0, self.timeout),
            )
        except grpc.RpcError as exc:
            raise RuntimeError(f"OpenRA could not create a match at {self.address}: {exc.code().name}") from exc
        self.session_id = str(message.session_id)
        if not self.session_id:
            raise RuntimeError("OpenRA returned an empty session id")
        return self.session_id

    def destroy_session(self, session_id: str | None = None) -> None:
        target = session_id or self.session_id
        if not target:
            return
        try:
            self.stub.DestroySession(
                rl_bridge_pb2.DestroySessionRequest(session_id=target),
                timeout=max(5.0, self.timeout),
            )
        except grpc.RpcError as exc:
            raise RuntimeError(f"OpenRA could not destroy match {target}: {exc.code().name}") from exc
        if target == self.session_id:
            self.session_id = ""

    def fast_advance(
        self,
        ticks: int,
        commands: tuple[ActionCommand, ...] = (),
        *,
        check_events_every: int = 25,
        enabled_interrupts: tuple[str, ...] = DEFAULT_INTERRUPTS,
    ) -> GameSnapshot:
        """Issue safe commands and advance a selected headless match at CPU speed."""
        if not self.session_id:
            raise RuntimeError("No headless OpenRA session is selected")
        if not 1 <= ticks <= 10_000:
            raise ValueError("ticks must be between 1 and 10000")
        request = rl_bridge_pb2.FastAdvanceRequest(
            ticks=ticks,
            commands=[self._command_message(command) for command in commands],
            session_id=self.session_id,
            check_events_every=max(0, min(int(check_events_every), ticks)),
            enabled_interrupts=list(enabled_interrupts),
        )
        try:
            message = self.stub.FastAdvance(request, timeout=max(15.0, self.timeout))
        except grpc.RpcError as exc:
            raise RuntimeError(f"OpenRA fast advance failed for {self.session_id}: {exc.code().name}") from exc
        value: dict[str, Any] = MessageToDict(message, preserving_proto_field_name=True)
        return GameSnapshot.from_dict(value)

    def close(self) -> None:
        self.channel.close()

    def __enter__(self) -> "OpenRABridge":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
