from functools import lru_cache
from pathlib import Path
from typing import Literal
from pathlib import Path as PathLib

from dotenv import load_dotenv
load_dotenv()

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_")
    # Убрано значение по умолчанию — переменная окружения обязательна
    openai_api_key: SecretStr = Field(description="OpenAI API key (required)")
    base_url: str = "https://api.proxyapi.ru/openai/v1"
    default_model: str = "gpt-4o-mini"
    request_timeout: float = 30.0
    max_retries: int = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PathLib(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "llm-service"
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600
    llm: LLMSettings = Field(default_factory=LLMSettings)
    rate_limit_per_min: int = 30  # по умолчанию

    # Chat ---------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://chat:chat@localhost:5432/chat"

    chat_repository: Literal["json", "postgres"] = Field("json", env="CHAT_REPOSITORY")
    chat_storage_dir: Path = Field(Path("./var/chats"), env="CHAT_STORAGE_DIR")
    chat_context_window: int = Field(10, env="CHAT_CONTEXT_WINDOW")
    chat_context_strategy: Literal["sliding", "hybrid"] = Field("sliding", env="CHAT_CONTEXT_STRATEGY")
    context_window_tokens: int = Field(128000, env="CONTEXT_WINDOW_TOKENS")
    response_tokens: int = Field(4096, env="RESPONSE_TOKENS")
    safety_margin: int = Field(1024, env="SAFETY_MARGIN")

    # в классе Settings (не LLMSettings):
    bot_url: str = "http://bot:9000"
    internal_token: SecretStr
    bot_api_port: int = 9000

    MODERATION_ENABLED: bool = True
    MODERATION_USE_OPENAI: bool = False
    MODERATION_THRESHOLD: float = 0.7

    ADMIN_TOKEN: str = ""

    # Б4.4
    BOT_ADMIN_IDS: list[int] = []

    @field_validator("BOT_ADMIN_IDS", mode="before")
    @classmethod
    def _split_ids(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, int):
            return [v]
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            s = v.strip().strip("[]").strip()
            if not s:
                return []
            return [int(x) for x in s.replace(";", ",").split(",") if x.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
