from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    KEYCLOAK_URL: str
    REALM_NAME: str
    KEYCLOAK_CLIENT_ID: str
    JWKS_URL: str
    AUTHORIZATION_URL: str
    TOKEN_URL: str
    KEYCLOAK_CLIENT_SECRET: str
    REDIRECT_URI: str
    REDIS_URL: str
    CHAT_CHANNEL_NAME: str
    ORCHESTRATOR_TASK_QUEUE_NAME: str
    LOGFIRE_API_KEY: str

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings():
    return Settings()
