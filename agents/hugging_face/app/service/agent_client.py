import asyncio

from fasta2a.client import A2AClient, Message

from app.config.settings import get_settings


async def send_message(message: Message):
    client = A2AClient(base_url=get_settings().AGENT_SERVER_URL)
    response = await client.send_message(message=message)
    task_id = response["result"]["history"][-1]["task_id"]
    while True:
        task_status_response = await client.get_task(task_id=task_id)
        status = task_status_response["result"]["status"]["state"]
        if status in ["completed", "failed", "canceled", "rejected", "input-required"]:
            return status, task_status_response

        await asyncio.sleep(0.5)
