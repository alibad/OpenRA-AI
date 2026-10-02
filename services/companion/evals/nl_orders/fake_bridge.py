"""A read-only gRPC bridge that replays one captured fixture.

The interactive MCP planner (the live ``watch`` path) reads the battlefield
through the engine bridge.  For reproducible evaluation this server answers
``Observe`` and ``GetState`` with a captured live observation and refuses every
other call, so no order can ever be executed.
"""

from __future__ import annotations

import threading
from concurrent import futures

import grpc
from google.protobuf.json_format import ParseDict

from openra_ai_companion.generated import rl_bridge_pb2, rl_bridge_pb2_grpc


class FixtureBridge(rl_bridge_pb2_grpc.RLBridgeServicer):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._observation = rl_bridge_pb2.GameObservation()
        self._state = rl_bridge_pb2.GameState()

    def load(self, payload: dict) -> None:
        observation = ParseDict(payload["observation"], rl_bridge_pb2.GameObservation(), ignore_unknown_fields=True)
        state = ParseDict(payload.get("state", {}), rl_bridge_pb2.GameState(), ignore_unknown_fields=True)
        with self._lock:
            self._observation = observation
            self._state = state

    def Observe(self, request, context):  # noqa: N802
        with self._lock:
            return self._observation

    def GetState(self, request, context):  # noqa: N802
        with self._lock:
            return self._state


def start_fixture_bridge() -> tuple[grpc.Server, FixtureBridge, str]:
    servicer = FixtureBridge()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    rl_bridge_pb2_grpc.add_RLBridgeServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    return server, servicer, f"127.0.0.1:{port}"
