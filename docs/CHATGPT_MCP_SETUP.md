# Connecting ChatGPT to Matrix Bridge via custom MCP

Matrix Bridge ships a standalone MCP server (`backend/mcp_server/`) that speaks
the Model Context Protocol over stdio. It stores sync state in a local SQLite
file, so it needs no Postgres/Pinecone/Weaviate setup to run.

## 1. Install dependencies

```bash
cd matrix-bridge/backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r mcp_server/requirements.txt
```

## 2. Fill in the ChatGPT "Connect to a custom MCP" form

| Field | Value |
|---|---|
| Name | `Matrix Bridge` |
| Type | `STDIO` |
| Command to launch | `python3` |
| Arguments | `-m` then `mcp_server` (two separate argument entries) |
| Environment variables | none required |
| Environment variable passthrough | none required |
| Working directory | absolute path to your clone's `backend` folder, e.g. `/Users/you/code/matrix-bridge/backend` |

If you used a virtualenv, point "Command to launch" at that venv's Python
instead, e.g. `/Users/you/code/matrix-bridge/backend/venv/bin/python3`, so the
`mcp` package is importable without activating the venv manually.

Optional: set `MATRIX_BRIDGE_DB_PATH` as an environment variable to control
where the SQLite file lives. Defaults to `~/.matrix-bridge/bridge.db`.

## 3. Available tools

- `capture_context(source_model, project_name, content_type, content)` — save
  a message/code/output/file from Claude or GPT into a project, tagged by
  source. New projects and `file`/`system_prompt` content require approval.
- `get_context(project_name, requesting_model)` — fetch what the *other*
  model has synced into a project.
- `list_projects()` — all known projects with their Claude/GPT tags.
- `list_pending_approvals()` — sync events waiting on a decision.
- `approve_sync(sync_id, action)` — `action` is `"approve"` or `"reject"`.

## 4. Verify it locally first

```bash
cd matrix-bridge/backend
python3 -m mcp_server
```

The process will sit waiting for stdio input — that's expected; it's how MCP
clients talk to it. Ctrl+C to stop. Point Claude Desktop/Code at the same
command first if you want to sanity-check the tools before wiring up ChatGPT.
