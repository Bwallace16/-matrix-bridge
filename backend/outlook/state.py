"""Delta links, subscriptions and the local mirror. Plain JSON files, one directory."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .models import Account, CalendarItem, MailItem


class SyncState(BaseModel):
    account: Account = Field(default_factory=Account)
    calendar_delta_link: str = ""
    mail_delta_links: dict[str, str] = Field(default_factory=dict)
    last_pull: datetime | None = None
    pull_count: int = 0
    subscriptions: dict[str, dict[str, Any]] = Field(default_factory=dict)


class StateStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._state_path = self.root / "state.json"
        self._events_path = self.root / "events.json"
        self._messages_path = self.root / "messages.json"

    # ---- state ------------------------------------------------------------

    def load_state(self) -> SyncState:
        if self._state_path.exists():
            return SyncState.model_validate_json(self._state_path.read_text())
        return SyncState()

    def save_state(self, state: SyncState) -> None:
        self._state_path.write_text(state.model_dump_json(indent=2))

    # ---- mirror -----------------------------------------------------------

    def load_events(self) -> dict[str, CalendarItem]:
        return {k: CalendarItem.model_validate(v) for k, v in self._read(self._events_path).items()}

    def save_events(self, items: dict[str, CalendarItem]) -> None:
        self._write(self._events_path, {k: v.model_dump(mode="json") for k, v in items.items()})

    def load_messages(self) -> dict[str, MailItem]:
        return {k: MailItem.model_validate(v) for k, v in self._read(self._messages_path).items()}

    def save_messages(self, items: dict[str, MailItem]) -> None:
        self._write(self._messages_path, {k: v.model_dump(mode="json") for k, v in items.items()})

    def reset(self) -> None:
        for path in (self._state_path, self._events_path, self._messages_path):
            if path.exists():
                path.unlink()

    # ---- io ---------------------------------------------------------------

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text() or "{}")

    @staticmethod
    def _write(path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.replace(path)
