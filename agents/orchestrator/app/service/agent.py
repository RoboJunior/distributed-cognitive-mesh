import asyncio
from contextlib import asynccontextmanager

import logfire
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.config.settings import get_settings
from app.service.agent_client import get_agents
from app.service.redis_service import REDIS, redis_stream

# Intializing the stream task
STREAM_TASK: asyncio.Task | None = None
# Initalizing the provider
provider = GoogleProvider(api_key=get_settings().API_KEY)
# Initalizing the model
model = GoogleModel(get_settings().MODEL_NAME, provider=provider)
# configure logfire
logfire.configure(
    token=get_settings().LOGFIRE_API_KEY, service_name="orchestrator-agent"
)
logfire.instrument_pydantic_ai()
logfire.instrument_system_metrics(base="full")


# Intialzing the delegation tools
async def queue_message_to_agent(ctx: RunContext, agent_name: str, query: str):
    print("Agent Name: ", agent_name)
    # Getting the tool name and get all the session details from redis
    tool_name = ctx.tool_name
    task_data = await REDIS.hgetall(name=tool_name)
    # Modify the query to be the updated query
    task_data["query"] = query
    # Push the task data to the respected agent
    await REDIS.xadd(agent_name, task_data)
    return f"Delegated to agent {agent_name}"


# Pydantic AI agent
agent = Agent(
    model=model,
    instructions=f"""
    You are an Orchestrator Agent. Your primary role is to understand the user’s query and delegate tasks to specialized child agents for efficient and accurate completion.
        Instructions:
            * Analyze the user query thoroughly.
            * Break down complex tasks into manageable subtasks.
            * Identify the most suitable child agent for each subtask and assign the work accordingly.
            * Maintain clear coordination and ensure the overall task is completed accurately and efficiently.
            * If no relevant child agents exist, respond with “no relevant agents." 
        Agent Available : {str(get_agents())}""",
    tools=[Tool(queue_message_to_agent)],
)

# Agent Server
orchestrator_agent_server = agent.to_a2a(
    name="orchestrator_agent",
    description="""
Analyzes user queries and breaks them into actionable components.
Assigns each subtask to the most suitable child agent.
Ensures efficient execution and accurate completion of the overall task.""",
)

# Getting the current lifespan context
a2a_lifespan = orchestrator_agent_server.router.lifespan_context


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
orchestrator_agent_server.router.lifespan_context = lifespan
