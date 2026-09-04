from __future__ import annotations
import asyncio
from collections import defaultdict
from fastapi import WebSocket
from backend.models.domain.entities import AgentEvent

class WebSocketHub:
    def __init__(self,send_timeout_seconds:float=2.0):
        self.connections:dict[str,set[WebSocket]]=defaultdict(set)
        self.send_timeout_seconds=send_timeout_seconds
    async def connect(self,channel:str,websocket:WebSocket):await websocket.accept();self.connections[channel].add(websocket)
    def disconnect(self,channel:str,websocket:WebSocket):self.connections[channel].discard(websocket)
    async def broadcast(self,channel:str,payload:dict):
        connections=tuple(self.connections[channel])
        if not connections:return
        async def send(websocket:WebSocket):
            try:
                await asyncio.wait_for(websocket.send_json(payload),timeout=self.send_timeout_seconds)
                return None
            except Exception:
                return websocket
        dead=await asyncio.gather(*(send(websocket) for websocket in connections))
        for websocket in dead:
            if websocket is not None:self.disconnect(channel,websocket)
    async def event_handler(self,event:AgentEvent):
        channel="agents" if event.topic.startswith("agent.") else "orders" if "order" in event.topic else "performance" if event.topic.startswith("trading.") else "alerts"
        await self.broadcast(channel,event.model_dump(mode="json"))

async def websocket_loop(hub:WebSocketHub,channel:str,websocket:WebSocket):
    await hub.connect(channel,websocket)
    try:
        while True:
            try:await asyncio.wait_for(websocket.receive_text(),timeout=25)
            except asyncio.TimeoutError:await websocket.send_json({"type":"heartbeat","channel":channel})
    except Exception:hub.disconnect(channel,websocket)
