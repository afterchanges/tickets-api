from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    app_env: str = Field(default="dev", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_access_ttl_min: int = Field(default=15, alias="JWT_ACCESS_TTL_MIN")
    jwt_refresh_ttl_days: int = Field(default=30, alias="JWT_REFRESH_TTL_DAYS")

    cors_origins: List[str] = Field(default_factory=list, alias="CORS_ORIGINS")

    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    rate_limit_window_sec: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SEC")
    rate_limit_login_per_ip: int = Field(default=20, alias="RATE_LIMIT_LOGIN_PER_IP")
    rate_limit_login_per_email: int = Field(default=10, alias="RATE_LIMIT_LOGIN_PER_EMAIL")
    rate_limit_register_per_ip: int = Field(default=10, alias="RATE_LIMIT_REGISTER_PER_IP")

    seed_admin: bool = Field(default=False, alias="SEED_ADMIN")
    seed_admin_update_existing: bool = Field(default=False, alias="SEED_ADMIN_UPDATE_EXISTING")
    admin_email: str | None = Field(default=None, alias="ADMIN_EMAIL")
    admin_password: str | None = Field(default=None, alias="ADMIN_PASSWORD")

    seed_agent: bool = Field(default=False, alias="SEED_AGENT")
    seed_agent_update_existing: bool = Field(default=False, alias="SEED_AGENT_UPDATE_EXISTING")
    agent_email: str | None = Field(default=None, alias="AGENT_EMAIL")
    agent_password: str | None = Field(default=None, alias="AGENT_PASSWORD")


settings = Settings()
