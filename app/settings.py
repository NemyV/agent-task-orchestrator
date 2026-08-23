import socket
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./agent.db"
    worker_poll_seconds: float = Field(default=0.5, gt=0)
    max_attempts: int = Field(default=3, ge=1, le=20)
    worker_id: str = Field(default_factory=socket.gethostname)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
