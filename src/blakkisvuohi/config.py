"""Runtime configuration, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEBHOOK_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{16,256}$")


def _secrets_dir() -> str | None:
    """Docker/Kubernetes secrets: a file /run/secrets/secret_key etc. works as the variable."""
    path = Path("/run/secrets")
    # A host's own /run/secrets (e.g. sops-nix on NixOS) is not readable by the user: skip it
    return str(path) if path.is_dir() and os.access(path, os.R_OK | os.X_OK) else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", secrets_dir=_secrets_dir()
    )

    bot_token: SecretStr
    # Master secret. Pseudonymous ids and the encryption key of personal data are derived from it,
    # so it must never change for an existing database. See README.
    secret_key: SecretStr
    database_path: Path = Path("data/blakkisvuohi.sqlite3")
    # The encryption keys of the users' data, in a file of their own. Do NOT back it up together
    # with the database: that separation is what makes deleting a user's key really erase their
    # data from old backups too.
    key_database_path: Path = Path("data/keys.sqlite3")
    # Everything older than this is deleted by the daily purge (and ignored until then)
    retention_days: int = Field(default=7, ge=1, le=365)
    # Accounts that have not been used for this long are deleted. Defaults to retention_days.
    account_retention_days: int | None = Field(default=None, ge=1, le=365)
    # Local hour (in TIMEZONE) of the daily purge
    purge_hour: int = Field(default=12, ge=0, le=23)
    # Telegram user id of the admin. Admin commands are disabled when unset.
    admin_id: int | None = None
    timezone: str = "Europe/Helsinki"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    bot_mode: Literal["polling", "webhook"] = "polling"
    # Webhook mode only: public https base url, e.g. https://blakkis.example.com
    webhook_url: str | None = None
    webhook_secret: SecretStr | None = None
    host: str = "0.0.0.0"  # noqa: S104 - inside a container this is what we want
    port: int = 8080

    @field_validator("secret_key")
    @classmethod
    def _secret_key_is_strong(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value

    @field_validator("timezone")
    @classmethod
    def _timezone_exists(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {value!r}, e.g. Europe/Helsinki") from exc
        return value

    @model_validator(mode="after")
    def _databases_are_separate(self) -> Settings:
        if self.database_path.resolve() == self.key_database_path.resolve():
            raise ValueError("DATABASE_PATH and KEY_DATABASE_PATH must be different files")
        return self

    @model_validator(mode="after")
    def _webhook_settings_present(self) -> Settings:
        if self.bot_mode == "webhook":
            if not self.webhook_url or not self.webhook_url.startswith("https://"):
                raise ValueError("WEBHOOK_URL (https) is required in webhook mode")
            secret = self.webhook_secret.get_secret_value() if self.webhook_secret else ""
            if not _WEBHOOK_SECRET_RE.match(secret):
                raise ValueError(
                    "WEBHOOK_SECRET is required in webhook mode: 16-256 characters of A-Z a-z 0-9 _ -"
                )
        return self

    @property
    def account_days(self) -> int:
        return self.account_retention_days or self.retention_days

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)
