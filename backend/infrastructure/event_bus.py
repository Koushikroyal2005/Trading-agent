"""Observer bus with local delivery and an optional durable Redis Stream."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable

from backend.models.domain.entities import AgentEvent

Handler = Callable[[AgentEvent], Awaitable[None]]


class EventBus:
    def __init__(self, redis_url: str | None = None, max_length: int = 50_000) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._redis_url = redis_url
        self._max_length = max_length
        self._redis = None

    async def initialize(self) -> None:
        if not self._redis_url:
            return
        try:
            from redis.asyncio import from_url
            self._redis = from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
        except Exception:
            self._redis = None

    def subscribe(self, topic: str, handler: Handler) -> None:
        if handler not in self._subscribers[topic]:
            self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        if handler in self._subscribers[topic]:
            self._subscribers[topic].remove(handler)

    async def publish(self, event: AgentEvent) -> None:
        if self._redis:
            try:
                await self._redis.xadd("vector:events", {"topic": event.topic, "source": event.source, "payload": event.model_dump_json()}, maxlen=self._max_length, approximate=True)
            except Exception:
                self._redis = None
        handlers = [*self._subscribers.get(event.topic, []), *self._subscribers.get("*", [])]
        if handlers:
            await asyncio.gather(*(handler(event) for handler in handlers), return_exceptions=True)

    async def health(self) -> bool:
        if not self._redis and self._redis_url:
            await self.initialize()
        try:
            return bool(self._redis and await self._redis.ping())
        except Exception:
            self._redis = None
            return False

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
