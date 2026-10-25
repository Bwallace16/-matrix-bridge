"""Settings for the Outlook integration. Everything comes from OUTLOOK_* env vars."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [v.strip() for v in value if v and v.strip()]
    return [v.strip() for v in value.split(",") if v.strip()]


class OutlookSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OUTLOOK_", extra="ignore")

    # Entra app registration (public client, "Allow public client flows" = Yes)
    tenant_id: str = "organizations"
    client_id: str = ""
    client_secret: str = ""  # only needed for a confidential client; leave blank for device flow

    # Delegated Graph scopes. offline_access is added by MSAL.
    scopes: list[str] = Field(default_factory=lambda: ["Calendars.Read", "Mail.Read", "User.Read"])

    # Where the token cache, delta links and the local mirror live.
    state_dir: Path = Path(".outlook-state")

    # Pull window for the first calendar delta. Later pulls ride the delta token.
    calendar_lookback_days: int = 30
    calendar_lookahead_days: int = 14

    # Well-known folder names Graph accepts: inbox, sentitems, drafts, archive...
    mail_folders: list[str] = Field(default_factory=lambda: ["inbox", "sentitems", "drafts"])

    page_size: int = 50

    # Privacy filter. Domains that count as "us". Keywords that mark personal items.
    internal_domains: list[str] = Field(default_factory=list)
    personal_keywords: list[str] = Field(default_factory=list)

    # Flag thresholds used by the digest.
    stale_after_days: int = 3

    # Webhooks (optional). Public HTTPS URL that Graph can reach.
    notification_url: str = ""
    client_state: str = ""

    @field_validator("scopes", "mail_folders", "internal_domains", "personal_keywords", mode="before")
    @classmethod
    def _csv(cls, value):
        return _split_csv(value)

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def configured(self) -> bool:
        return bool(self.client_id)
