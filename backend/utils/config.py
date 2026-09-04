"""Singleton, validated application settings."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "backend/config/dev.env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Vector Trading System"
    environment: str = "development"
    mode: str = "PAPER_TRADING"
    api_key: SecretStr | None = None
    alpaca_api_key: SecretStr | None = None
    alpaca_secret_key: SecretStr | None = None
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.6-flash"
    database_url: str = "sqlite+aiosqlite:///./backend/data/vector.db"
    timescale_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    hdd_storage_path: Path = Path("./backend/data")
    log_level: str = "INFO"
    max_position_percentage: float = Field(default=0.05, gt=0, le=0.2)
    max_daily_loss_percentage: float = Field(default=0.02, gt=0, le=0.1)
    agent_timeout_seconds: float = Field(default=5, ge=1, le=30)
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    allow_synthetic_data: bool = True
    auto_trade_enabled: bool = False
    scheduled_symbols: str = "AAPL,MSFT,SPY"
    scheduled_timeframes: str = "15"
    cycle_schedule_seconds: int = Field(default=300, ge=60, le=3600)
    market_stream_interval_seconds: int = Field(default=60, ge=5, le=300)
    market_data_max_age_minutes: int = Field(default=20, ge=1, le=120)
    event_stream_max_length: int = Field(default=50_000, ge=1000, le=1_000_000)

    @field_validator("mode")
    @classmethod
    def paper_only(cls, value: str) -> str:
        if value.upper() != "PAPER_TRADING":
            raise ValueError("This project only permits PAPER_TRADING mode")
        return value.upper()

    @property
    def alpaca_configured(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_secret_key)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def symbols(self) -> list[str]:
        return [value.strip().upper() for value in self.scheduled_symbols.split(",") if value.strip()]

    @property
    def timeframes(self) -> list[int]:
        return [int(value.strip()) for value in self.scheduled_timeframes.split(",") if value.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.hdd_storage_path.mkdir(parents=True, exist_ok=True)
    return settings
