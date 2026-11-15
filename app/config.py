from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://shortform:local-dev-only@localhost:5432/shortform"
    redis_url: str = "redis://localhost:6379/0"
    video_data_dir: Path = Path(".artifacts/jobs")


@lru_cache
def get_settings() -> Settings:
    return Settings()
