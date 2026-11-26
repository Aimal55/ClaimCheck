"""
Application settings loaded from environment variables / .env file.

Using pydantic-settings so every value is typed and validated at startup —
no silent failures from a missing or mistyped env var.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Server
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # Logging
    log_level: str = "INFO"

    # Database
    db_path: str = "claimcheck.db"

    # Claim validation limits
    claim_min_length: int = 10
    claim_max_length: int = 2000

    # Gemini atomic-claim decomposition
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",   # silently drop unknown env vars
    )


# Single shared instance — import this everywhere.
settings = Settings()
