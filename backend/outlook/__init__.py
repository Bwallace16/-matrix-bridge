"""Outlook integration point for Matrix Bridge.

Pulls calendar and mail from Microsoft Graph with delta queries, keeps a
small local mirror, applies a privacy filter before anything leaves the
process, and serves a digest that downstream consumers (the second brain
sync, other agents) read instead of talking to Graph themselves.

Entry points:
    outlook.router      FastAPI routes under /api/outlook
    outlook.cli         `python -m outlook auth|pull|digest|status|subscribe`
    outlook.sync        OutlookSync, the pull + digest engine
"""

from .config import OutlookSettings
from .models import CalendarItem, MailItem, OutlookDigest
from .privacy import PrivacyFilter
from .sync import OutlookSync

__all__ = [
    "OutlookSettings",
    "CalendarItem",
    "MailItem",
    "OutlookDigest",
    "PrivacyFilter",
    "OutlookSync",
]
