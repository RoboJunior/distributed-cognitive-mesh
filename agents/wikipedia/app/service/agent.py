import asyncio
from contextlib import asynccontextmanager

import logfire
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.config.settings import get_settings
from app.service.redis_service import REDIS, redis_stream

# Wikipedia Mcp Server
mcp = MCPServerStdio(
    command="wikipedia-mcp",
    args=["--transport", "stdio"],
)
# configure logfire
logfire.configure(token=get_settings().LOGFIRE_API_KEY, service_name="wikipedia-agent")
logfire.instrument_pydantic_ai()
logfire.instrument_system_metrics(base="full")

# Intializing the stream task
STREAM_TASK: asyncio.Task | None = None
# Initalizing the provider
provider = GoogleProvider(api_key=get_settings().API_KEY)
# Initalizing the model
model = GoogleModel(get_settings().MODEL_NAME, provider=provider)
# Pydantic AI agent
agent = Agent(
    model=model,
    instructions="""
    Your task is to understand the user query and retrieve information only from Wikipedia.
    Do not use any other sources; rely strictly on Wikipedia content.
    Summarize or explain the information in clear, concise language, while maintaining accuracy.
    Provide references in the format: [Wikipedia] after each fact or statement.
    Avoid adding personal opinions, interpretations, or information not present in Wikipedia.
    If a query cannot be answered from Wikipedia, respond: “No information available on Wikipedia.""",
    mcp_servers=[mcp],
)

# Agent Server
wikipedia_agent_server = agent.to_a2a(
    name="wikipedia",
    description="""
        A Wikipedia-based information agent that answers user queries using only Wikipedia content, 
        providing accurate summaries with citations""",
)

# Getting the current lifespan context
a2a_lifespan = wikipedia_agent_server.router.lifespan_context


# Updated lifespan with redis stream
@asynccontextmanager
async def lifespan(app_instance):
    global STREAM_TASK
    STREAM_TASK = asyncio.create_task(redis_stream())
    print("[App] Redis Stream Started")
    # Maintians the original lifespan for interal a2a tasks aswell
    async with a2a_lifespan(app_instance) as state:
        try:
            yield state
        finally:
            # Shutting down the redis server
            if STREAM_TASK:
                STREAM_TASK.cancel()
                try:
                    await STREAM_TASK
                except asyncio.CancelledError:
                    print("[App] Redis Stream task cancelled")
            await REDIS.close()
            print("[App] Redis client closed")


# Adding the redis stream to the exisitng a2a lifespan
wikipedia_agent_server.router.lifespan_context = lifespan
