import asyncio

import httpx


def get_agents():
    agent_cards = []
    agent_urls = ["http://localhost:8003"]

    with httpx.Client(verify=False) as client:  # disable SSL verification
        for agent_url in agent_urls:
            agent_card = client.get(url=f"{agent_url}/.well-known/agent.json")
            agent_cards.append(agent_card.json())

    return agent_cards


print(get_agents())
