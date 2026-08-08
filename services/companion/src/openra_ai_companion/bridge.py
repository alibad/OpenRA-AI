from __future__ import annotations

import json
from typing import Any

import grpc
from google.protobuf.json_format import MessageToDict

from .generated import rl_bridge_pb2, rl_bridge_pb2_grpc
from .models import GameSnapshot


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

    def close(self) -> None:
        self.channel.close()

    def __enter__(self) -> "OpenRABridge":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
