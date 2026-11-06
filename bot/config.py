from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    BACKEND_URL: str = "http://app:8000"
    BOT_ADMIN_IDS: list[int] = []
    INTERNAL_TOKEN: str
    ADMIN_TOKEN: str = ""
    BOT_API_PORT: int = 9000

    @field_validator("BOT_ADMIN_IDS", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v):
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


settings = Settings()

def get_settings() -> Settings:
    return settings