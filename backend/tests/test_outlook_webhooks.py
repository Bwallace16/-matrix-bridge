import pytest

from outlook.webhooks import ClientStateMismatch, SubscriptionManager, parse_notifications


def test_parse_accepts_matching_client_state():
    body = {"value": [{"subscriptionId": "s1", "changeType": "created", "resource": "me/events", "clientState": "ok"}]}
    notes = parse_notifications(body, "ok")
    assert notes[0].subscription_id == "s1" and notes[0].change_type == "created"


def test_parse_rejects_wrong_client_state():
    body = {"value": [{"subscriptionId": "s1", "changeType": "created", "resource": "x", "clientState": "nope"}]}
    with pytest.raises(ClientStateMismatch):
        parse_notifications(body, "ok")


def test_ensure_creates_then_renews(graph, store, fake_graph):
    mgr = SubscriptionManager(graph, store, "https://bridge.example/api/outlook/notifications", "s3cret")
    subs = mgr.ensure()
    assert set(subs) == {"inbox", "calendar"}
    assert all(s["clientState"] == "s3cret" for s in fake_graph.subscriptions.values())
    posts = [c for c in fake_graph.calls if c[0] == "POST"]
    assert len(posts) == 2

    mgr.ensure()
    patches = [c for c in fake_graph.calls if c[0] == "PATCH"]
    assert len(patches) == 2 and len(fake_graph.subscriptions) == 2


def test_ensure_recreates_when_graph_lost_it(graph, store, fake_graph):
    mgr = SubscriptionManager(graph, store, "https://bridge.example/n", "s3cret")
    mgr.ensure()
    fake_graph.subscriptions.clear()
    mgr.ensure()
    assert len(fake_graph.subscriptions) == 2


def test_remove_all(graph, store, fake_graph):
    mgr = SubscriptionManager(graph, store, "https://bridge.example/n", "s3cret")
    mgr.ensure()
    assert mgr.remove_all() == 2
    assert fake_graph.subscriptions == {} and store.load_state().subscriptions == {}


def test_client_state_length_guard(graph, store):
    with pytest.raises(ValueError):
        SubscriptionManager(graph, store, "https://x", "a" * 129)
