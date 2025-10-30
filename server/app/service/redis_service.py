import asyncio
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI, WebSocket

from app.config.settings import get_settings

# Redis
REDIS = redis.from_url(get_settings().REDIS_URL, decode_responses=True)

# Active websocket connections per server process
ACTIVE_CONNECTIONS: set[WebSocket] = set()

# Channel where all the chat messages are published
CHAT_CHANNEL_NAME = get_settings().CHAT_CHANNEL_NAME

# Intializing the lister task
LISTENER_TASK: asyncio.Task | None = None


async def redis_listener():
    """Listen to Redis channel and broadcast messages to local connections."""
    pubsub = REDIS.pubsub()
    await pubsub.subscribe(CHAT_CHANNEL_NAME)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                print(f"[Redis] Received: {data}")

                disconnected = []
                # Broadcast to all connected WebSockets
                for connection in ACTIVE_CONNECTIONS:
                    try:
                        await connection.send_text(data)
                    except Exception as e:
                        # Log broken connections
                        print(
                            f"[Redis] Broken connection removed: {connection}, error: {e}"
                        )
                        disconnected.append(connection)

                # Remove broken connections
                for connection in disconnected:
                    ACTIVE_CONNECTIONS.remove(connection)

    except asyncio.CancelledError:
        await pubsub.unsubscribe(CHAT_CHANNEL_NAME)
        await pubsub.close()
        print("[Redis] Listener stopped gracefully")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    global LISTENER_TASK
    # Startup: start Redis listener
    LISTENER_TASK = asyncio.create_task(redis_listener())
    print("[App] Redis listener started")
    try:
        yield
    finally:
        # Shutdown: cancel Redis listener
        if LISTENER_TASK:
            LISTENER_TASK.cancel()
            try:
                await LISTENER_TASK
            except asyncio.CancelledError:
                print("[App] Redis listener task cancelled")
        # Close Redis client
        await REDIS.close()
        print("[App] Redis client closed")
