"""SQLite-backed storage for the Matrix Bridge MCP server."""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".matrix-bridge" / "bridge.db"

AUTO_SYNC_TYPES = {"message", "code", "output"}
APPROVAL_REQUIRED_TYPES = {"file", "system_prompt"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BridgeStore:
    """Owns the SQLite connection and schema for sync state."""

    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                tag_claude TEXT NOT NULL,
                tag_gpt TEXT NOT NULL,
                last_sync TEXT
            );

            CREATE TABLE IF NOT EXISTS sync_events (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_model TEXT NOT NULL,
                content_type TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                requires_approval INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );
            """
        )
        self.conn.commit()

    def get_or_create_project(self, name: str):
        row = self.conn.execute(
            "SELECT * FROM projects WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return dict(row), False
        project_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO projects (id, name, tag_claude, tag_gpt, last_sync) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, name, f"{name}-Claude", f"{name}-GPT", None),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return dict(row), True

    def record_event(self, project_id, source_model, content_type, content, requires_approval):
        event_id = f"sync_{uuid.uuid4().hex[:12]}"
        status = "pending" if requires_approval else "synced"
        self.conn.execute(
            "INSERT INTO sync_events "
            "(id, project_id, source_model, content_type, content, status, requires_approval, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, project_id, source_model, content_type, content, status, int(requires_approval), _now()),
        )
        if not requires_approval:
            self.conn.execute(
                "UPDATE projects SET last_sync = ? WHERE id = ?", (_now(), project_id)
            )
        self.conn.commit()
        return event_id, status

    def list_projects(self):
        rows = self.conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def list_pending(self):
        rows = self.conn.execute(
            "SELECT * FROM sync_events WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_event(self, sync_id):
        row = self.conn.execute(
            "SELECT * FROM sync_events WHERE id = ?", (sync_id,)
        ).fetchone()
        return dict(row) if row else None

    def resolve_approval(self, sync_id, approve: bool):
        event = self.get_event(sync_id)
        if event is None:
            return None
        status = "synced" if approve else "rejected"
        self.conn.execute(
            "UPDATE sync_events SET status = ? WHERE id = ?", (status, sync_id)
        )
        if approve:
            self.conn.execute(
                "UPDATE projects SET last_sync = ? WHERE id = ?", (_now(), event["project_id"])
            )
        self.conn.commit()
        return status

    def synced_context(self, project_id, from_model=None):
        query = "SELECT * FROM sync_events WHERE project_id = ? AND status = 'synced'"
        params = [project_id]
        if from_model:
            query += " AND source_model = ?"
            params.append(from_model)
        query += " ORDER BY created_at"
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
