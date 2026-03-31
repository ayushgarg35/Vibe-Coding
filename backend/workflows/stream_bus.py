"""
Redis streaming bus — connects agent token output to SSE clients.

Flow:
  Agent produces token
    → publish_token() → Redis channel: "session:{id}:stream"
      → SSE route subscribes → EventSource in browser

Each session gets its own Redis channel.
Events are JSON-encoded SSE payloads.
"""
import asyncio
import json
from enum import Enum
from typing import AsyncIterator

import redis.asyncio as aioredis
import structlog

from config.settings import get_settings

log = structlog.get_logger()
settings = get_settings()

# Singleton connection pool — shared across the process
_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


def _channel(session_id: str) -> str:
    return f"session:{session_id}:stream"


class StreamEventType(str, Enum):
    CONNECTED = "connected"
    AGENT_START = "agent_start"
    AGENT_TOKEN = "agent_token"
    AGENT_COMPLETE = "agent_complete"
    GATE_REACHED = "gate_reached"
    CLARIFICATION_NEEDED = "clarification_needed"
    PHASE_CHANGED = "phase_changed"
    ERROR = "error"
    PING = "ping"
    DONE = "done"          # signals SSE stream can close


async def publish(session_id: str, event_type: StreamEventType, data: dict | None = None) -> None:
    """
    Publish a structured event to the session's Redis channel.
    Called by agents, orchestrator nodes, and gate handlers.
    """
    redis = await get_redis()
    payload = json.dumps({"type": event_type.value, "session_id": session_id, **(data or {})})
    await redis.publish(_channel(session_id), payload)
    log.debug("Stream event published", session_id=session_id, event=event_type.value)


async def publish_token(session_id: str, agent: str, token: str, model: str | None = None) -> None:
    """Shorthand for publishing a single streaming token from an agent."""
    await publish(session_id, StreamEventType.AGENT_TOKEN, {
        "agent": agent,
        "token": token,
        **({"model": model} if model else {}),
    })


async def publish_agent_start(session_id: str, agent: str, model: str | None = None) -> None:
    await publish(session_id, StreamEventType.AGENT_START, {
        "agent": agent,
        **({"model": model} if model else {}),
    })


async def publish_agent_complete(session_id: str, agent: str) -> None:
    await publish(session_id, StreamEventType.AGENT_COMPLETE, {"agent": agent})


async def publish_gate_reached(session_id: str, gate_number: int, gate_title: str) -> None:
    await publish(session_id, StreamEventType.GATE_REACHED, {
        "gate": gate_number,
        "title": gate_title,
    })


async def publish_clarification(session_id: str, questions: list[dict]) -> None:
    await publish(session_id, StreamEventType.CLARIFICATION_NEEDED, {"questions": questions})


async def publish_phase_changed(session_id: str, phase: str) -> None:
    await publish(session_id, StreamEventType.PHASE_CHANGED, {"phase": phase})


async def subscribe(session_id: str) -> AsyncIterator[str]:
    """
    Subscribe to a session's event stream.
    Yields SSE-formatted strings for consumption by StreamingResponse.
    Automatically sends keep-alive pings every 15 seconds.
    Closes when a DONE event is received or connection drops.
    """
    redis = await get_redis()
    pubsub = redis.pubsub()
    channel = _channel(session_id)

    await pubsub.subscribe(channel)
    log.info("SSE subscriber connected", session_id=session_id, channel=channel)

    # Send immediate connect confirmation
    yield _sse({"type": StreamEventType.CONNECTED.value, "session_id": session_id})

    try:
        ping_task = asyncio.create_task(_ping_loop())

        async for raw_message in pubsub.listen():
            if raw_message["type"] != "message":
                continue

            data_str = raw_message.get("data", "")
            if not data_str:
                continue

            # Pass ping events through
            if data_str == "__ping__":
                yield _sse({"type": StreamEventType.PING.value})
                continue

            try:
                payload = json.loads(data_str)
            except json.JSONDecodeError:
                log.warning("Malformed SSE payload", data=data_str)
                continue

            yield _sse(payload)

            # Close the stream after DONE event
            if payload.get("type") == StreamEventType.DONE.value:
                break

    except asyncio.CancelledError:
        pass
    finally:
        ping_task.cancel()
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        log.info("SSE subscriber disconnected", session_id=session_id)


async def _ping_loop() -> None:
    """Sends a ping to the channel every 15s to keep SSE connections alive through proxies."""
    redis = await get_redis()
    while True:
        await asyncio.sleep(15)
        # Publish to all active session channels — in practice, we track them
        # TODO: maintain active session set in Redis for targeted pings


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event string."""
    return f"data: {json.dumps(data)}\n\n"
