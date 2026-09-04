import asyncio

import pytest

from backend.api.websocket import WebSocketHub


class FakeWebSocket:
    def __init__(self, delay: float = 0):
        self.delay = delay
        self.messages = []

    async def send_json(self, payload):
        await asyncio.sleep(self.delay)
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_broadcast_delivers_to_healthy_clients_and_removes_stale_ones():
    hub = WebSocketHub(send_timeout_seconds=0.01)
    healthy = FakeWebSocket()
    stale = FakeWebSocket(delay=1)
    hub.connections["market"].update({healthy, stale})

    await hub.broadcast("market", {"symbol": "AAPL", "price": 123.45})

    assert healthy.messages == [{"symbol": "AAPL", "price": 123.45}]
    assert healthy in hub.connections["market"]
    assert stale not in hub.connections["market"]
