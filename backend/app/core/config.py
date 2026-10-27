from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Bank Agent"
    debug: bool = True
    api_prefix: str = "/api"

    database_url: str = "sqlite:///./bank_agent.db"
    cors_origins: str = "http://localhost:5173"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    demo_username: str = "demo"
    demo_password: str = "demo123"
    demo_display_name: str = "演示用户"

    risk_night_start_hour: int = Field(default=0, ge=0, le=23)
    risk_night_end_hour: int = Field(default=6, ge=0, le=23)

    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout: float = 60.0
    llm_max_history: int = 20

    @model_validator(mode="after")
    def validate_night_hours(self) -> "Settings":
        if self.risk_night_start_hour == self.risk_night_end_hour:
            raise ValueError("夜间风控开始和结束时间不能相同")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
