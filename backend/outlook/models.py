"""Normalized shapes. Graph payloads come in, these go out."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Graph returns up to 7 fractional digits; Python wants 6.
    text = value.rstrip("Z")
    if "." in text:
        head, frac = text.split(".", 1)
        text = f"{head}.{frac[:6]}"
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class Person(BaseModel):
    name: str = ""
    email: str = ""

    @classmethod
    def from_graph(cls, node: dict[str, Any] | None) -> "Person":
        if not node:
            return cls()
        addr = node.get("emailAddress", node)
        return cls(name=addr.get("name") or "", email=(addr.get("address") or "").lower())


class Attendee(Person):
    type: str = "required"
    response: str = "none"


class CalendarItem(BaseModel):
    id: str
    subject: str = ""
    start: datetime | None = None
    end: datetime | None = None
    time_zone: str = "UTC"
    organizer: Person = Field(default_factory=Person)
    attendees: list[Attendee] = Field(default_factory=list)
    external_attendees: list[str] = Field(default_factory=list)
    is_online_meeting: bool = False
    online_meeting_url: str = ""
    is_cancelled: bool = False
    is_all_day: bool = False
    web_link: str = ""
    last_modified: datetime | None = None
    removed: bool = False

    @classmethod
    def from_graph(cls, node: dict[str, Any]) -> "CalendarItem":
        if "@removed" in node:
            return cls(id=node["id"], removed=True)
        start = node.get("start") or {}
        end = node.get("end") or {}
        online = node.get("onlineMeeting") or {}
        return cls(
            id=node["id"],
            subject=node.get("subject") or "",
            start=_dt(start.get("dateTime")),
            end=_dt(end.get("dateTime")),
            time_zone=start.get("timeZone") or "UTC",
            organizer=Person.from_graph(node.get("organizer")),
            attendees=[
                Attendee(
                    name=(a.get("emailAddress") or {}).get("name") or "",
                    email=((a.get("emailAddress") or {}).get("address") or "").lower(),
                    type=a.get("type") or "required",
                    response=(a.get("status") or {}).get("response") or "none",
                )
                for a in node.get("attendees") or []
            ],
            is_online_meeting=bool(node.get("isOnlineMeeting")),
            online_meeting_url=online.get("joinUrl") or node.get("onlineMeetingUrl") or "",
            is_cancelled=bool(node.get("isCancelled")),
            is_all_day=bool(node.get("isAllDay")),
            web_link=node.get("webLink") or "",
            last_modified=_dt(node.get("lastModifiedDateTime")),
        )


MAIL_SELECT = ",".join(
    [
        "id",
        "conversationId",
        "subject",
        "from",
        "sender",
        "toRecipients",
        "ccRecipients",
        "receivedDateTime",
        "sentDateTime",
        "lastModifiedDateTime",
        "bodyPreview",
        "isRead",
        "isDraft",
        "hasAttachments",
        "webLink",
        "importance",
    ]
)


class MailItem(BaseModel):
    id: str
    folder: str = "inbox"
    conversation_id: str = ""
    subject: str = ""
    sender: Person = Field(default_factory=Person)
    to: list[Person] = Field(default_factory=list)
    cc: list[Person] = Field(default_factory=list)
    counterparts: list[str] = Field(default_factory=list)
    received: datetime | None = None
    sent: datetime | None = None
    last_modified: datetime | None = None
    preview: str = ""
    is_read: bool = False
    is_draft: bool = False
    has_attachments: bool = False
    importance: str = "normal"
    web_link: str = ""
    removed: bool = False

    @classmethod
    def from_graph(cls, node: dict[str, Any], folder: str) -> "MailItem":
        if "@removed" in node:
            return cls(id=node["id"], folder=folder, removed=True)
        return cls(
            id=node["id"],
            folder=folder,
            conversation_id=node.get("conversationId") or "",
            subject=node.get("subject") or "",
            sender=Person.from_graph(node.get("from") or node.get("sender")),
            to=[Person.from_graph(r) for r in node.get("toRecipients") or []],
            cc=[Person.from_graph(r) for r in node.get("ccRecipients") or []],
            received=_dt(node.get("receivedDateTime")),
            sent=_dt(node.get("sentDateTime")),
            last_modified=_dt(node.get("lastModifiedDateTime")),
            preview=(node.get("bodyPreview") or "")[:400],
            is_read=bool(node.get("isRead")),
            is_draft=bool(node.get("isDraft")),
            has_attachments=bool(node.get("hasAttachments")),
            importance=node.get("importance") or "normal",
            web_link=node.get("webLink") or "",
        )

    @property
    def when(self) -> datetime | None:
        return self.received or self.sent or self.last_modified


class Account(BaseModel):
    name: str = ""
    email: str = ""
    id: str = ""


class DigestFlags(BaseModel):
    stale_drafts: list[str] = Field(default_factory=list)
    unanswered: list[str] = Field(default_factory=list)
    contacts_seen: list[str] = Field(default_factory=list)


class OutlookDigest(BaseModel):
    schema_id: str = Field(default="matrix-bridge.outlook-digest/1", alias="schema")
    generated_at: datetime
    since: datetime
    until: datetime
    account: Account
    events: list[CalendarItem]
    upcoming: list[CalendarItem] = Field(default_factory=list)
    messages: list[MailItem]
    flags: DigestFlags
    stats: dict[str, int]

    model_config = {"populate_by_name": True}


class PullResult(BaseModel):
    pulled_at: datetime
    events_seen: int = 0
    events_kept: int = 0
    events_removed: int = 0
    messages_seen: int = 0
    messages_kept: int = 0
    messages_removed: int = 0
    first_pull: bool = False
