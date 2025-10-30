import asyncio
import json
from datetime import datetime
from typing import Dict

import redis.asyncio as redis
from fasta2a.client import Message
from fasta2a.schema import TextPart
from redis.exceptions import ResponseError

from app.config.settings import get_settings
from app.service.agent_client import send_message
from app.service.auth_service import validate_token

# Redis
REDIS = redis.from_url(get_settings().REDIS_URL, decode_responses=True)
# Channel where the response messages should be streamed back from the agent
CHAT_CHANNEL_NAME = get_settings().CHAT_CHANNEL_NAME
# limit concurrent tasks
SEMAPHORE = asyncio.Semaphore(10)


# To check wheather the exist or not
async def ensure_group():
    try:
        # Create group only if it doesn't exist
        await REDIS.xgroup_create(
            get_settings().TOPIC_NAME, get_settings().GROUP_NAME, id="0", mkstream=True
        )
        print("Task Group Created Successfully!")
    except ResponseError as e:
        # Check for the specific error when the group already exists
        if "BUSYGROUP" in str(e):
            pass
        else:
            raise  # re-raise unexpected errors


async def send_message_to_socket(message: Dict):
    await REDIS.publish(
        channel=get_settings().CHAT_CHANNEL_NAME, message=json.dumps(message)
    )


async def ack_message(msg_id: str):
    """Acknowledge and delete message after successful processing."""
    await REDIS.xack(get_settings().TOPIC_NAME, get_settings().GROUP_NAME, msg_id)
    await REDIS.xdel(get_settings().TOPIC_NAME, msg_id)


async def process_message(agent_name: str, msg_id: str, msg_data: dict):
    """Process a single message concurrently."""
    async with SEMAPHORE:
        try:
            token = msg_data["token"]
            task_id = msg_data["task_id"]
            query = msg_data["query"]
            timestamp = msg_data["timestamp"]
            session_id = msg_data["session_id"]

            # Step 1: Validate token
            is_valid_token = await validate_token(token=token)
            if is_valid_token.status_code != 200:
                await send_message_to_socket(
                    {"status": "error", "message": is_valid_token.detail}
                )
                await ack_message(msg_id)
                return

            # Step 2: Validate user role
            if f"{agent_name}-user" not in is_valid_token.detail.roles:
                await send_message_to_socket(
                    {
                        "status": "unauthorized",
                        "message": f"{is_valid_token.detail.username} is not authorized to access {agent_name}",
                    }
                )
                await ack_message(msg_id)
                return

            # Step 3: Task assigned notification
            await send_message_to_socket(
                {
                    "status": "assigned",
                    "message": f"Task assigned to {agent_name} agent",
                }
            )

            # Step 4: Send message to agent
            message = Message(
                role="user",
                parts=[TextPart(kind="text", text=query)],
                kind="message",
                message_id=msg_id,
                task_id=task_id,
                context_id=session_id,
            )

            agent_status, agent_response = await send_message(message=message)

            # Step 5: Send agent response
            timestamp_dt = datetime.fromisoformat(timestamp)
            current_dt = datetime.now()

            if agent_status == "completed":
                agent_messages = [
                    m
                    for m in agent_response["result"]["history"]
                    if m["role"] == "agent"
                ]
                for msg in agent_messages:
                    for part in msg["parts"]:
                        if part.get("text"):
                            await send_message_to_socket(
                                {
                                    "status": agent_status,
                                    "type": "response",
                                    "agent_response": part["text"],
                                    "time_taken": (
                                        current_dt - timestamp_dt
                                    ).total_seconds()
                                    * 1000,
                                }
                            )

            # Step 6: Acknowledge message
            await ack_message(msg_id)

        except Exception as e:
            # Log or send error message but don't requeue
            print(f"[ERROR] Message {msg_id} failed: {e}")
            await send_message_to_socket(
                {
                    "status": "failed",
                    "message": f"Task failed for {agent_name}: {str(e)}",
                }
            )
            # Acknowledge even on error to prevent retry loops
            await ack_message(msg_id)


async def redis_stream():
    """Main Redis stream consumer loop."""
    await ensure_group()

    while True:
        messages = await REDIS.xreadgroup(
            groupname=get_settings().GROUP_NAME,
            consumername=get_settings().CONSUMER_NAME,
            streams={get_settings().TOPIC_NAME: ">"},
            count=10,  # batch size
            block=5000,  # wait up to 5s for new messages
        )

        if not messages:
            await asyncio.sleep(1)
            continue

        tasks = []
        for stream, msgs in messages:
            for msg_id, msg_data in msgs:
                tasks.append(
                    asyncio.create_task(process_message(stream, msg_id, msg_data))
                )

        # Run all tasks concurrently, but handle exceptions safely
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, Exception):
                print(f"[Unhandled Exception in message processor] {res}")

        await asyncio.sleep(0.5)
