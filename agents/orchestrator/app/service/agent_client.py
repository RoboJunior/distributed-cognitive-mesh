import asyncio

import httpx
from fasta2a.client import A2AClient, Message

from app.config.settings import get_settings


async def send_message(message: Message):
    client = A2AClient(base_url=get_settings().AGENT_SERVER_URL)
    response = await client.send_message(message=message)
    print(response)
    task_id = response["result"]["history"][-1]["task_id"]
    while True:
        task_status_response = await client.get_task(task_id=task_id)
        print(task_status_response)
        status = task_status_response["result"]["status"]["state"]
        if status in ["completed", "failed", "canceled", "rejected", "input-required"]:
            return status, task_status_response

        await asyncio.sleep(0.5)


def get_agents():
    agent_cards = []
    agent_urls = ["http://localhost:8003", "http://localhost:8004"]

    with httpx.Client() as client:
        for agent_url in agent_urls:
            agent_card = client.get(url=f"{agent_url}/.well-known/agent.json")
            agent_cards.append(agent_card.json())

    return agent_cards
