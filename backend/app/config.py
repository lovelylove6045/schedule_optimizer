from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, populated from environment variables / .env file."""

    # Reads the repo-root `.env` (single source of truth for local dev) and falls back to
    # a `backend/.env` if one exists. Missing files are silently skipped by pydantic-settings.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "schedule_optimizer"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    cors_allow_origins: str = "http://localhost:5173"
    cors_allow_origin_regex: str | None = (
        r"^https?://(?:localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}):5173$"
    )

    @property
    def database_url(self) -> str:
        """Build the SQLAlchemy connection string from the individual Postgres settings."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins(self) -> list[str]:
        """Split the comma-separated `cors_allow_origins` setting into a clean list."""
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide `Settings` instance, constructed once and cached."""
    return Settings()
