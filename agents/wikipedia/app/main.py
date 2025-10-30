# Start the Main Orchestrator Agent server
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.service.agent:wikipedia_agent_server",
        host="0.0.0.0",
        port=8004,
        reload=True,
    )
