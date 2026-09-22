"""Typed runtime configuration for offline and live execution modes."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cliproxy_base_url: str = "http://127.0.0.1:8317/v1"
    cliproxy_api_key: SecretStr | None = None
    cliproxy_model: str = "gpt-5.6-luna"
    langchain_tracing_v2: bool = False
    langchain_api_key: SecretStr | None = None
    langchain_project: str = "zensible"
    postgres_dsn: str = "postgresql://zensible:zensible_dev@localhost:5433/zensible"
