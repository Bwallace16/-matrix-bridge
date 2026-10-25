from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import app
from conftest import NOW, OWNER, event, mail
from outlook import router as outlook_router
from outlook.auth import AuthRequired
from outlook.config import OutlookSettings


@pytest.fixture
def client(sync, settings):
    outlook_router.set_runtime(outlook_router.Runtime(settings, sync=sync))
    yield TestClient(app)
    outlook_router.set_runtime(None)


def test_root_lists_integration(client):
    assert "outlook" in client.get("/").json()["integrations"]


def test_status_when_unconfigured(tmp_path):
    outlook_router.set_runtime(
        outlook_router.Runtime(OutlookSettings(client_id="", state_dir=tmp_path, _env_file=None))
    )
    try:
        body = TestClient(app).get("/api/outlook/status").json()
    finally:
        outlook_router.set_runtime(None)
    assert body["configured"] is False and body["signed_in"] is False


def test_pull_and_digest(client, fake_graph):
    fake_graph.queue("calendar", [event("e1", "Kickoff", NOW - timedelta(days=1), ["pm@acme.io"])])
    fake_graph.queue("inbox", [mail("m1", "Hi", "pm@acme.io", [OWNER], NOW - timedelta(days=1))])
    pulled = client.post("/api/outlook/pull").json()
    assert pulled["events_kept"] == 1 and pulled["messages_kept"] == 1

    digest = client.get("/api/outlook/digest", params={"since": (NOW - timedelta(days=7)).isoformat()}).json()
    assert digest["schema"] == "matrix-bridge.outlook-digest/1"
    assert [e["id"] for e in digest["events"]] == ["e1"]
    assert digest["flags"]["contacts_seen"] == ["pm@acme.io"]


def test_digest_refresh_pulls_first(client, fake_graph):
    fake_graph.queue("calendar", [event("e1", "Kickoff", NOW - timedelta(days=1), ["pm@acme.io"])])
    params = {"refresh": "true", "since": (NOW - timedelta(days=7)).isoformat()}
    digest = client.get("/api/outlook/digest", params=params).json()
    assert digest["stats"]["events"] == 1


def test_notification_handshake_echoes_token(client):
    r = client.post("/api/outlook/notifications?validationToken=abc%20123")
    assert r.status_code == 200 and r.text == "abc 123" and r.headers["content-type"].startswith("text/plain")


def test_notification_with_good_state_triggers_pull(client, fake_graph):
    fake_graph.queue("calendar", [event("e1", "Pushed", NOW, ["c@acme.io"])])
    body = {
        "value": [{"subscriptionId": "s", "changeType": "created", "resource": "me/events", "clientState": "s3cret"}]
    }
    r = client.post("/api/outlook/notifications", json=body)
    assert r.status_code == 202 and r.json() == {"accepted": 1}
    assert any("calendarView" in u for _, u in fake_graph.calls)


def test_notification_with_bad_state_is_ignored(client, fake_graph):
    body = {
        "value": [{"subscriptionId": "s", "changeType": "created", "resource": "me/events", "clientState": "wrong"}]
    }
    r = client.post("/api/outlook/notifications", json=body)
    assert r.status_code == 202 and r.json() == {"accepted": 0}
    assert not any("calendarView" in u for _, u in fake_graph.calls)


def test_subscriptions_roundtrip(client, fake_graph):
    created = client.post("/api/outlook/subscriptions").json()
    assert set(created) == {"inbox", "calendar"}
    assert client.delete("/api/outlook/subscriptions").json() == {"removed": 2}


def test_auth_required_is_503(settings, store):
    class Broken:
        graph = None

        def pull(self):
            raise AuthRequired("run auth")

    broken = Broken()
    broken.store = store
    outlook_router.set_runtime(outlook_router.Runtime(settings, sync=broken))
    try:
        r = TestClient(app).post("/api/outlook/pull")
    finally:
        outlook_router.set_runtime(None)
    assert r.status_code == 503 and r.json()["error"] == "outlook_not_ready"
