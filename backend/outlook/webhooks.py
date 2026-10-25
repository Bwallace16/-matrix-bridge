"""Graph change notifications. Outlook pushes, we validate, then we pull."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel

from .graph import GraphClient, GraphError
from .state import StateStore

# Outlook message/event subscriptions max out at 10,080 minutes. Stay under it.
SUBSCRIPTION_MINUTES = 10_000
RESOURCES = {
    "inbox": "me/mailFolders('inbox')/messages",
    "calendar": "me/events",
}


class Notification(BaseModel):
    subscription_id: str
    change_type: str
    resource: str
    client_state: str = ""


class ClientStateMismatch(ValueError):
    """A notification arrived with the wrong clientState. Treat as hostile and ignore."""


def parse_notifications(body: dict[str, Any], expected_client_state: str) -> list[Notification]:
    out: list[Notification] = []
    for raw in body.get("value", []):
        note = Notification(
            subscription_id=raw.get("subscriptionId", ""),
            change_type=raw.get("changeType", ""),
            resource=raw.get("resource", ""),
            client_state=raw.get("clientState") or "",
        )
        if expected_client_state and note.client_state != expected_client_state:
            raise ClientStateMismatch(f"subscription {note.subscription_id}")
        out.append(note)
    return out


class SubscriptionManager:
    def __init__(self, graph: GraphClient, store: StateStore, notification_url: str, client_state: str):
        if client_state and len(client_state) > 128:
            raise ValueError("client_state must be 128 characters or fewer")
        self.graph = graph
        self.store = store
        self.notification_url = notification_url
        self.client_state = client_state

    def _expiry(self) -> str:
        return (datetime.now(timezone.utc) + timedelta(minutes=SUBSCRIPTION_MINUTES)).strftime(
            "%Y-%m-%dT%H:%M:%S.0000000Z"
        )

    def ensure(self) -> dict[str, dict[str, Any]]:
        """Create missing subscriptions, renew the ones we hold. Idempotent."""
        if not self.notification_url:
            raise ValueError("OUTLOOK_NOTIFICATION_URL is not set")
        state = self.store.load_state()
        for name, resource in RESOURCES.items():
            existing = state.subscriptions.get(name)
            if existing and existing.get("id"):
                try:
                    renewed = self.graph.patch(
                        f"subscriptions/{existing['id']}", {"expirationDateTime": self._expiry()}
                    )
                    state.subscriptions[name] = {**existing, **renewed}
                    continue
                except GraphError as err:
                    if err.status != 404:
                        raise
            created = self.graph.post(
                "subscriptions",
                {
                    "changeType": "created,updated,deleted",
                    "notificationUrl": self.notification_url,
                    "resource": resource,
                    "expirationDateTime": self._expiry(),
                    "clientState": self.client_state,
                },
            )
            state.subscriptions[name] = created
        self.store.save_state(state)
        return state.subscriptions

    def remove_all(self) -> int:
        state = self.store.load_state()
        removed = 0
        for name, sub in list(state.subscriptions.items()):
            if sub.get("id"):
                try:
                    self.graph.delete(f"subscriptions/{sub['id']}")
                    removed += 1
                except GraphError as err:
                    if err.status != 404:
                        raise
            state.subscriptions.pop(name)
        self.store.save_state(state)
        return removed
