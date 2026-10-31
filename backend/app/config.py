from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_CORS_ORIGINS = ("https://grindpvp-blsu.onrender.com",)


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./grindpvp.db"
    admin_username: str = "admin"
    admin_password: str | None = None
    admin_session_hours: int = Field(default=8, ge=1, le=168)
    cors_origins: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def cors_origin_list(self) -> list[str]:
        configured_origins = [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]
        return list(dict.fromkeys((*DEFAULT_CORS_ORIGINS, *configured_origins)))


@lru_cache
def get_settings() -> Settings:
    return Settings()
