import asyncio
from contextlib import asynccontextmanager

import logfire
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.config.settings import get_settings
from app.service.redis_service import REDIS, redis_stream

# Hugging face Mcp Server
mcp = MCPServerStdio(
    command="npx", args=["-y", "mcp-remote@latest", "https://huggingface.co/mcp?login"]
)
# configure logfire
logfire.configure(
    token=get_settings().LOGFIRE_API_KEY, service_name="huggingface-agent"
)
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
    Understand the user query and provide answers only using Hugging Face models, datasets, or documentation.
    Summarize or explain clearly and accurately.
    Provide references as [Hugging Face].
    If the information is not available in Hugging Face resources, reply: “No information available on Hugging Face.”""",
    mcp_servers=[mcp],
)

# Agent Server
hugging_face_agent_server = agent.to_a2a(
    name="huggingface",
    description="""
        A Hugging Face agent that answers user queries using only Hugging Face models, datasets, 
        and documentation, providing accurate summaries with citations.""",
)

# Getting the current lifespan context
a2a_lifespan = hugging_face_agent_server.router.lifespan_context


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
hugging_face_agent_server.router.lifespan_context = lifespan
