from __future__ import annotations
import json
from typing import Any, AsyncIterator, Callable
import asyncio


def sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def sse_stream(queue: "asyncio.Queue[dict]") -> AsyncIterator[str]:
    while True:
        msg = await queue.get()
        if msg.get("stage") == "done":
            yield sse_event("progress", msg)
            break
        yield sse_event("progress", msg)
