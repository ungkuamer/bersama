from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator

ISSUES_UPDATED = "issues_updated"
RUNS_UPDATED = "runs_updated"
LOG_APPEND = "log_append"


@dataclass(frozen=True)
class Event:
    type: str
    data: dict


class _Subscriber:
    def __init__(self, bus: EventBus, queue: asyncio.Queue[Event]) -> None:
        self._bus = bus
        self._queue = queue

    async def __aenter__(self) -> _Subscriber:
        return self

    async def __aexit__(self, *args: object) -> None:
        self._bus._subscribers.remove(self._queue)

    def __aiter__(self) -> _Subscriber:
        return self

    async def __anext__(self) -> Event:
        return await self._queue.get()


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[Event]] = []

    async def publish(self, event: Event) -> None:
        self.publish_nowait(event)

    def publish_nowait(self, event: Event) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> _Subscriber:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        return _Subscriber(self, queue)
