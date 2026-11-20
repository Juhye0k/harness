from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    enable_auth: bool = False
    auth_origin: str = "http://localhost:8000"
    google_login_client_id: str = ""
    google_login_client_secret: SecretStr = SecretStr("")
    database_url: str = "postgresql+psycopg://shortform:local-dev-only@localhost:5432/shortform"
    redis_url: str = "redis://localhost:6379/0"
    video_data_dir: Path = Path(".artifacts/jobs")
    upload_data_dir: Path = Path(".artifacts/uploads")
    enable_paid_ai: bool = False
    enable_free_ai: bool = False
    groq_free_tier_confirmed: bool = False
    groq_api_key: SecretStr = SecretStr("")
    record_groq_error_body: bool = False
    groq_error_dir: Path = Path(".artifacts/private/provider-errors")
    transcription_provider: Literal["groq", "azure"] = "groq"
    recommendation_provider: Literal["none", "groq", "openai"] = "none"
    azure_speech_endpoint: str = ""
    azure_speech_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    recommendation_model: str = "gpt-5.6-terra"
    enable_sns_upload: bool = False
    sns_origin: str = "http://localhost:8000"
    youtube_client_id: str = ""
    youtube_client_secret: SecretStr = SecretStr("")
    sns_token_key: SecretStr = SecretStr("")


@lru_cache
def get_settings() -> Settings:
    return Settings()
