import uuid
from datetime import datetime

import logfire
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse

from app.config.settings import get_settings
from app.schema.auth import TokenData
from app.service.auth_service import get_access_token, get_auth_url, get_current_user
from app.service.redis_service import (
    ACTIVE_CONNECTIONS,
    CHAT_CHANNEL_NAME,
    REDIS,
    lifespan,
)

# Initalizing the fastapi server
app = FastAPI(title="Main Server", lifespan=lifespan)
logfire.configure(token=get_settings().LOGFIRE_API_KEY, service_name="main-server")
logfire.instrument_fastapi(app)
logfire.instrument_system_metrics(base="full")


@app.get("/login")
async def login():
    auth_url = await get_auth_url()
    return RedirectResponse(auth_url)


@app.get("/callback")
async def callback(code: str):
    token_data = await get_access_token(code=code)
    return {"message": "Login successful", "token": token_data}


# Main Chat Server
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, token: str, session_id: str):
    """
    Connect via WebSocket with query param ?token=<access_token>
    """
    try:
        # Validate token
        current_user: TokenData = await get_current_user(token)
        await websocket.accept()
        ACTIVE_CONNECTIONS.add(websocket)

        # Welcome message
        await REDIS.publish(
            CHAT_CHANNEL_NAME,
            f"Welcome to the chat {current_user.username}",
        )

        # Chat loop
        while True:
            data = await websocket.receive_text()
            # Create a new task
            task = {
                "task_id": str(uuid.uuid4()),
                "query": data,
                "timestamp": str(datetime.now()),
                "token": token,
                "session_id": session_id,
            }
            # Setting the session data to the tool in the orchestrator agent
            await REDIS.hset("queue_message_to_agent", mapping=task)
            # Setting a ttl of 60 seconds for each task
            await REDIS.expire("queue_message_to_agent", time=60)
            # Add the task to the orchestractor agent task queue
            await REDIS.xadd(get_settings().ORCHESTRATOR_TASK_QUEUE_NAME, task)

    except WebSocketDisconnect:
        ACTIVE_CONNECTIONS.remove(websocket)
        await REDIS.publish(
            CHAT_CHANNEL_NAME, f"{current_user.username} left the chat."
        )

    except HTTPException:
        # Token invalid → close connection
        await websocket.close(code=1008)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
