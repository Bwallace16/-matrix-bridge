"""Fake Graph. Serves delta rounds and subscriptions from in-memory fixtures. No network."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from outlook.auth import StaticTokenProvider
from outlook.config import OutlookSettings
from outlook.graph import GraphClient
from outlook.privacy import PrivacyFilter
from outlook.state import StateStore
from outlook.sync import OutlookSync

NOW = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)
OWNER = "owner@example.com"
INTERNAL = "example.com"


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")


def person(email: str, name: str = "") -> dict:
    return {"emailAddress": {"address": email, "name": name or email.split("@")[0].title()}}


def event(id_: str, subject: str, start: datetime, attendees: list[str], organizer: str = OWNER, **extra) -> dict:
    node = {
        "id": id_,
        "subject": subject,
        "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"},
        "end": {"dateTime": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"},
        "organizer": person(organizer),
        "attendees": [{**person(a), "type": "required", "status": {"response": "accepted"}} for a in attendees],
        "isOnlineMeeting": True,
        "onlineMeeting": {"joinUrl": f"https://teams.example/{id_}"},
        "lastModifiedDateTime": iso(start - timedelta(days=1)),
        "webLink": f"https://outlook.example/{id_}",
    }
    node.update(extra)
    return node


def mail(
    id_: str,
    subject: str,
    sender: str,
    to: list[str],
    received: datetime,
    conversation: str = "",
    is_draft: bool = False,
    preview: str = "hello",
) -> dict:
    return {
        "id": id_,
        "conversationId": conversation or f"conv-{id_}",
        "subject": subject,
        "from": person(sender),
        "toRecipients": [person(t) for t in to],
        "ccRecipients": [],
        "receivedDateTime": iso(received),
        "sentDateTime": iso(received),
        "lastModifiedDateTime": iso(received),
        "bodyPreview": preview,
        "isRead": False,
        "isDraft": is_draft,
        "hasAttachments": False,
        "webLink": f"https://outlook.example/mail/{id_}",
    }


class FakeGraph:
    """Scripted responses keyed by resource. Each delta round pages in twos, then hands out a deltaLink."""

    def __init__(self):
        self.rounds: dict[str, list[list[dict]]] = {"calendar": [], "inbox": [], "sentitems": [], "drafts": []}
        self.calls: list[tuple[str, str]] = []
        self.subscriptions: dict[str, dict] = {}
        self.throttle_once: set[str] = set()
        self._round_no: dict[str, int] = {}

    def queue(self, resource: str, items: list[dict]) -> None:
        self.rounds[resource].append(items)

    def _resource(self, path: str) -> str:
        if "calendarView" in path:
            return "calendar"
        for folder in ("inbox", "sentitems", "drafts"):
            if f"mailFolders/{folder}/" in path:
                return folder
        raise AssertionError(f"unknown resource in {path}")

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = urlparse(str(request.url))
        path, qs = url.path, parse_qs(url.query)
        self.calls.append((request.method, str(request.url)))
        assert request.headers["Authorization"] == "Bearer test-token"

        if path.endswith("/me"):
            return httpx.Response(200, json={"displayName": "Owner Person", "mail": OWNER, "id": "u1"})

        if "/subscriptions" in path:
            return self._subscriptions(request, path)

        if "/delta" in path:
            resource = self._resource(path)
            if resource in self.throttle_once:
                self.throttle_once.discard(resource)
                return httpx.Response(429, headers={"Retry-After": "1"}, json={"error": {"message": "slow down"}})
            if "$deltatoken" in qs or "$skiptoken" in qs:
                token = (qs.get("$deltatoken") or qs.get("$skiptoken"))[0]
                round_no, page = (int(x) for x in token.split("-"))
            else:
                round_no, page = self._round_no.get(resource, 0), 0
                if "$skiptoken" not in qs:
                    self._round_no[resource] = round_no + 1
            items = self.rounds[resource][round_no] if round_no < len(self.rounds[resource]) else []
            chunk = items[page * 2 : page * 2 + 2]
            body = {"value": chunk}
            base = f"https://graph.microsoft.com/v1.0{path}"
            if (page + 1) * 2 < len(items):
                body["@odata.nextLink"] = f"{base}?$skiptoken={round_no}-{page + 1}"
            else:
                body["@odata.deltaLink"] = f"{base}?$deltatoken={round_no + 1}-0"
            return httpx.Response(200, json=body)

        return httpx.Response(404, json={"error": {"message": f"no fake for {path}"}})

    def _subscriptions(self, request: httpx.Request, path: str) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content)
            sub_id = f"sub-{len(self.subscriptions) + 1}"
            self.subscriptions[sub_id] = {"id": sub_id, **body}
            return httpx.Response(201, json=self.subscriptions[sub_id])
        sub_id = path.rsplit("/", 1)[-1]
        if sub_id not in self.subscriptions:
            return httpx.Response(404, json={"error": {"message": "gone"}})
        if request.method == "PATCH":
            self.subscriptions[sub_id].update(json.loads(request.content))
            return httpx.Response(200, json=self.subscriptions[sub_id])
        if request.method == "DELETE":
            del self.subscriptions[sub_id]
            return httpx.Response(204)
        return httpx.Response(405)


@pytest.fixture
def fake_graph() -> FakeGraph:
    return FakeGraph()


@pytest.fixture
def settings(tmp_path: Path) -> OutlookSettings:
    return OutlookSettings(
        client_id="test-client",
        state_dir=tmp_path / "state",
        internal_domains=[INTERNAL],
        personal_keywords=["dentist", "soccer"],
        notification_url="https://bridge.example/api/outlook/notifications",
        client_state="s3cret",
        _env_file=None,
    )


@pytest.fixture
def graph(fake_graph: FakeGraph) -> GraphClient:
    return GraphClient(
        StaticTokenProvider("test-token"),
        transport=httpx.MockTransport(fake_graph.handler),
        page_size=2,
        sleep=lambda _s: None,
    )


@pytest.fixture
def store(settings: OutlookSettings) -> StateStore:
    return StateStore(settings.state_dir)


@pytest.fixture
def sync(graph: GraphClient, store: StateStore, settings: OutlookSettings) -> OutlookSync:
    return OutlookSync(graph, store, settings, clock=lambda: NOW)


@pytest.fixture
def privacy() -> PrivacyFilter:
    return PrivacyFilter([INTERNAL], ["dentist", "soccer"], OWNER)
