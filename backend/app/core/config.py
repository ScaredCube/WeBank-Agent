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

    data_encryption_key: str = ""
    data_encryption_key_version: str = "v1"
    data_encryption_previous_keys: str = "{}"
    data_hmac_key: str = ""

    demo_username: str = "demo"
    demo_password: str = "demo123"
    demo_display_name: str = "演示用户"
    # Seed a second account and holding so the drag collision matrix is demoable.
    demo_multi_assets: bool = True
    # Dynamic read-only views can be disabled without disabling trusted tool cards.
    generative_ui_enabled: bool = True

    risk_night_start_hour: int = Field(default=0, ge=0, le=23)
    risk_night_end_hour: int = Field(default=6, ge=0, le=23)
    guard_timeout_seconds: float = Field(default=8.0, gt=0, le=60)

    security_failure_threshold: int = Field(default=5, ge=1, le=100)
    security_failure_window_seconds: int = Field(default=600, ge=1, le=86400)
    security_lock_seconds: int = Field(default=900, ge=1, le=604800)
    security_rate_limit_requests: int = Field(default=60, ge=1, le=10000)
    security_rate_window_seconds: int = Field(default=60, ge=1, le=86400)
    security_unlock_code: str = Field(default="246810", pattern=r"^[0-9]{6}$")

    # Fixed code is solely for local demonstration; verification is disabled unless DEBUG=true.
    demo_verification_code: str = Field(default="123456", pattern=r"^[0-9]{6}$")

    llm_base_url: str = "https://tokendance.space/gateway/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4.1-flash-1017"
    # Additional provider-specific HTTP headers, supplied as a JSON object in .env.
    # Authorization: Bearer is automatically handled by AsyncOpenAI via llm_api_key.
    llm_extra_headers: dict[str, str] = Field(default_factory=dict)
    llm_timeout: float = 60.0
    llm_max_history: int = 20
    # Output review is independent of the tool-call Guard. It rewrites an
    # unsupported reply and never changes risk levels or executes tools.
    reply_grounding_enabled: bool = True
    reply_grounding_timeout_seconds: float = Field(default=8.0, gt=0, le=60)
    view_review_timeout_seconds: float = Field(default=8.0, gt=0, le=60)
    view_max_generations: int = Field(default=2, ge=1, le=3)

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
