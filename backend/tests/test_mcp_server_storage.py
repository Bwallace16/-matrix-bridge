import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_server.storage import BridgeStore


def _store(tmp_path):
    return BridgeStore(tmp_path / "bridge.db")


def test_new_project_requires_approval(tmp_path):
    store = _store(tmp_path)
    project, created = store.get_or_create_project("rest-api")
    assert created is True
    sync_id, status = store.record_event(
        project["id"], "claude", "message", "hello", requires_approval=True
    )
    assert status == "pending"
    assert store.list_pending()[0]["id"] == sync_id


def test_auto_sync_types_skip_approval(tmp_path):
    store = _store(tmp_path)
    project, _ = store.get_or_create_project("rest-api")
    sync_id, status = store.record_event(
        project["id"], "claude", "message", "hello", requires_approval=False
    )
    assert status == "synced"
    context = store.synced_context(project["id"], from_model="claude")
    assert len(context) == 1
    assert context[0]["id"] == sync_id


def test_approve_sync_moves_event_to_synced(tmp_path):
    store = _store(tmp_path)
    project, _ = store.get_or_create_project("rest-api")
    sync_id, status = store.record_event(
        project["id"], "gpt", "file", "print('hi')", requires_approval=True
    )
    assert status == "pending"

    resolved = store.resolve_approval(sync_id, approve=True)
    assert resolved == "synced"
    context = store.synced_context(project["id"], from_model="gpt")
    assert len(context) == 1


def test_reject_sync_never_appears_in_context(tmp_path):
    store = _store(tmp_path)
    project, _ = store.get_or_create_project("rest-api")
    sync_id, _ = store.record_event(
        project["id"], "gpt", "file", "print('hi')", requires_approval=True
    )
    store.resolve_approval(sync_id, approve=False)
    context = store.synced_context(project["id"], from_model="gpt")
    assert context == []
