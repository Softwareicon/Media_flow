"""Application settings. Every secret comes from the environment; nothing is hard-coded."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- core ---
    environment: str = "development"  # development | test | production
    database_url: str = "postgresql+asyncpg://mediaflow:mediaflow@localhost:5432/mediaflow"
    public_base_url: str = "http://localhost:8000"  # used to build OAuth redirect URIs
    app_redirect_scheme: str = "mediaflow"  # deep link back into the mobile app
    cors_origins: list[str] = Field(default_factory=list)  # mobile apps don't need CORS
    require_https: bool = False  # set True in production behind TLS
    auto_create_tables: bool = False  # tests / quick local runs only; production uses Alembic

    # --- secrets ---
    token_encryption_key: SecretStr | None = None  # Fernet key for stored OAuth tokens
    session_ttl_days: int = 30

    # --- limits ---
    rate_limit_per_minute: int = 30  # per principal, for /media/analyze and /downloads
    rate_limit_auth_per_minute: int = 10
    analysis_ttl_seconds: int = 900
    max_media_bytes: int = 4 * 1024**3  # refuse options larger than this
    max_html_bytes: int = 512 * 1024
    http_timeout_seconds: float = 10.0
    max_redirects: int = 3
    allowed_ports: list[int] = Field(default_factory=lambda: [80, 443])
    download_record_retention_days: int = 30

    # --- platform credentials (all optional; adapters report "not configured" without them) ---
    youtube_api_key: SecretStr | None = None
    vimeo_client_id: str | None = None
    vimeo_client_secret: SecretStr | None = None
    instagram_app_id: str | None = None
    instagram_app_secret: SecretStr | None = None
    facebook_app_id: str | None = None
    facebook_app_secret: SecretStr | None = None
    facebook_graph_version: str = "v21.0"
    pinterest_app_id: str | None = None
    pinterest_app_secret: SecretStr | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: SecretStr | None = None
    reddit_user_agent: str = "server:mediaflow-pro:1.0 (by /u/your_reddit_username)"
    x_bearer_token: SecretStr | None = None
    x_media_downloads_enabled: bool = False  # operator must confirm their X agreement permits it

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
