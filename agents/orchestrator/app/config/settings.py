from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    TOPIC_NAME: str
    MODEL_NAME: str
    API_KEY: str
    REDIS_URL: str
    CHAT_CHANNEL_NAME: str
    GROUP_NAME: str
    CONSUMER_NAME: str
    JWKS_URL: str
    AGENT_SERVER_URL: str
    LOGFIRE_API_KEY: str

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings():
    return Settings()
