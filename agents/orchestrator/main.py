import asyncio
import uuid

from fasta2a.client import A2AClient, Message, SendMessageResponse
from fasta2a.schema import TextPart


async def agent_send_message(message: Message) -> SendMessageResponse:
    client = A2AClient(base_url="http://localhost:8002")
    response = await client.send_message(message=message)
    task_id = response["result"]["history"][-1]["task_id"]

    while True:
        task_status_response = await client.get_task(task_id=task_id)
        status = task_status_response["result"]["status"]["state"]
        if status in ["completed", "failed", "canceled", "rejected"]:
            if status == "completed":
                print(
                    task_status_response["result"]["artifacts"][-1]["parts"][-1]["text"]
                )

            break
        else:
            print("Task still runnnig")
            await asyncio.sleep(2)


asyncio.run(
    agent_send_message(
        Message(
            role="user",
            parts=[TextPart(kind="text", text="Hello bro")],
            kind="message",
            message_id=str(uuid.uuid4()),
        )
    )
)
