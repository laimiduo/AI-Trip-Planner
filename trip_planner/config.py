"""集中配置管理 — 基于 pydantic-settings，支持 .env 加载."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # === LLM ===
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-v4-flash"
    LLM_TEMPERATURE: float = 0.5

    # === Amap ===
    AMAP_API_KEY: str = ""

    # === Redis (optional) ===
    REDIS_URL: Optional[str] = None
    ENABLE_CACHE: bool = True

    # === PostgreSQL (optional) ===
    DATABASE_URL: Optional[str] = None
    ENABLE_DB: bool = True

    # === ARQ (optional) ===
    ENABLE_ARQ: bool = True

    # === Server ===
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
