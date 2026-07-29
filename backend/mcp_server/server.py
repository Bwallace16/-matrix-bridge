"""Matrix Bridge MCP server (requires mcp>=1.2.0,<2.0.0 for the FastMCP API).

Exposes the bidirectional Claude <-> ChatGPT context-sync loop as MCP tools,
backed by local SQLite storage. Runs over stdio so either an MCP client
(Claude Desktop/Code) or ChatGPT's custom MCP connector can launch it as a
subprocess.
"""

import os

from mcp.server.fastmcp import FastMCP

from .storage import AUTO_SYNC_TYPES, APPROVAL_REQUIRED_TYPES, DEFAULT_DB_PATH, BridgeStore

mcp = FastMCP("matrix-bridge")
store = BridgeStore(os.environ.get("MATRIX_BRIDGE_DB_PATH", DEFAULT_DB_PATH))

VALID_MODELS = {"claude", "gpt"}
VALID_CONTENT_TYPES = AUTO_SYNC_TYPES | APPROVAL_REQUIRED_TYPES


@mcp.tool()
def capture_context(
    source_model: str,
    project_name: str,
    content_type: str,
    content: str,
) -> dict:
    """Capture an interaction from Claude or GPT and queue it for sync.

    source_model: "claude" or "gpt" - which model produced this content.
    project_name: logical project this content belongs to (auto-created).
    content_type: one of message, code, output, file, system_prompt.
    content: the text/code to share with the other model.
    """
    source_model = source_model.lower()
    if source_model not in VALID_MODELS:
        raise ValueError(f"source_model must be one of {sorted(VALID_MODELS)}")
    if content_type not in VALID_CONTENT_TYPES:
        raise ValueError(f"content_type must be one of {sorted(VALID_CONTENT_TYPES)}")

    project, created = store.get_or_create_project(project_name)
    requires_approval = created or content_type in APPROVAL_REQUIRED_TYPES
    sync_id, status = store.record_event(
        project["id"], source_model, content_type, content, requires_approval
    )
    return {
        "sync_id": sync_id,
        "project": project_name,
        "requires_approval": requires_approval,
        "status": status,
    }


@mcp.tool()
def get_context(project_name: str, requesting_model: str) -> dict:
    """Fetch synced context for a project, as seen by the requesting model.

    requesting_model: "claude" or "gpt" - returns the OTHER model's synced
    contributions to this project (what it should learn about).
    """
    requesting_model = requesting_model.lower()
    if requesting_model not in VALID_MODELS:
        raise ValueError(f"requesting_model must be one of {sorted(VALID_MODELS)}")
    other_model = "gpt" if requesting_model == "claude" else "claude"

    project, _ = store.get_or_create_project(project_name)
    events = store.synced_context(project["id"], from_model=other_model)
    return {
        "project": project_name,
        "source_model": other_model,
        "entries": [
            {
                "sync_id": e["id"],
                "content_type": e["content_type"],
                "content": e["content"],
                "created_at": e["created_at"],
            }
            for e in events
        ],
    }


@mcp.tool()
def list_projects() -> list:
    """List all known projects with their Claude/GPT tags and last sync time."""
    return store.list_projects()


@mcp.tool()
def list_pending_approvals() -> list:
    """List sync events awaiting user approval before they cross the bridge."""
    return store.list_pending()


@mcp.tool()
def approve_sync(sync_id: str, action: str) -> dict:
    """Approve or reject a pending sync event.

    action: "approve" or "reject".
    """
    action = action.lower()
    if action not in {"approve", "reject"}:
        raise ValueError('action must be "approve" or "reject"')
    status = store.resolve_approval(sync_id, approve=(action == "approve"))
    if status is None:
        raise ValueError(f"no sync event found with id {sync_id}")
    return {"sync_id": sync_id, "status": status}


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
