"""In-process fan-out of new thread events to open SSE connections."""

import asyncio
from collections import defaultdict


class Broker:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, thread_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[thread_id].add(queue)
        return queue

    def unsubscribe(self, thread_id: str, queue: asyncio.Queue) -> None:
        self._subscribers[thread_id].discard(queue)
        if not self._subscribers[thread_id]:
            del self._subscribers[thread_id]

    def publish(self, thread_id: str, event: dict) -> None:
        for queue in self._subscribers.get(thread_id, ()):
            queue.put_nowait(event)


broker = Broker()
