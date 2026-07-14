from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CHAT_",
        env_file=str(_BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database — use absolute path for SQLite
    database_url: str = f"sqlite+aiosqlite:///{_BASE_DIR / 'chat.db'}"

    # FastAuth — these use the FASTAUTH_ prefix internally
    fastauth_secret_key: str = "dev-secret-key-change-in-production"
    fastauth_algorithm: str = "HS256"
    fastauth_access_token_ttl_minutes: int = 60
    fastauth_refresh_token_ttl_days: int = 7

    @property
    def fastauth_env(self) -> dict[str, str]:
        """Return a dict suitable for setting env vars before FastAuth reads them."""
        return {
            "FASTAUTH_SECRET_KEY": self.fastauth_secret_key,
            "FASTAUTH_ALGORITHM": self.fastauth_algorithm,
            "FASTAUTH_ACCESS_TOKEN_TTL_MINUTES": str(
                self.fastauth_access_token_ttl_minutes
            ),
            "FASTAUTH_REFRESH_TOKEN_TTL_DAYS": str(
                self.fastauth_refresh_token_ttl_days
            ),
            "FASTAUTH_COOKIE_SECURE": "false",  # dev-friendly default
        }


settings = Settings()