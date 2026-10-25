# Matrix Bridge API Reference

## Base URL
```
http://localhost:8000/api
```

## Endpoints

### POST /sync/capture
Capture an interaction from Claude or ChatGPT.

**Request:**
```json
{
  "source_model": "claude",
  "content_type": "message",
  "content": "User message text",
  "files": []
}
```

**Response:**
```json
{
  "success": true,
  "sync_id": "sync_12345",
  "requires_approval": false,
  "status": "synced"
}
```

### GET /projects
List all synced projects.

**Response:**
```json
{
  "projects": [
    {
      "id": "proj_1",
      "name": "REST API",
      "tag_claude": "rest-api-Claude",
      "tag_gpt": "rest-api-GPT",
      "last_sync": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### POST /approval/review
Review and approve/reject a pending sync.

**Request:**
```json
{
  "sync_id": "sync_12345",
  "action": "approve"
}
```

### GET /context/{project_id}
Retrieve synthesized context for a project.

### POST /settings/update
Update user sync rules.

**Request:**
```json
{
  "auto_sync_types": ["message", "code"],
  "require_approval_for": ["file", "new_project"],
  "token_limit": 2000
}
```

## Outlook integration

All routes are read-only against the mailbox. See [OUTLOOK.md](./OUTLOOK.md) for setup and the digest schema.

### GET /api/outlook/status
Configuration, sign-in state, last pull, mirror counts, active subscriptions.

### POST /api/outlook/pull
Run one delta round for calendar and each configured mail folder.

**Response:**
```json
{ "pulled_at": "...", "events_seen": 12, "events_kept": 4, "events_removed": 0,
  "messages_seen": 30, "messages_kept": 11, "messages_removed": 1, "first_pull": false }
```

### GET /api/outlook/digest
Query: `since` (ISO, default 7 days ago), `until` (ISO, default now), `refresh` (bool, pull first).
Returns a `matrix-bridge.outlook-digest/1` document.

### POST /api/outlook/notifications
Microsoft Graph webhook target. Echoes `validationToken` on the handshake, otherwise validates `clientState`, answers 202 and pulls in the background.

### POST /api/outlook/subscriptions
Create or renew Graph change-notification subscriptions for inbox and calendar.

### DELETE /api/outlook/subscriptions
Remove them.

Errors: `503 outlook_not_ready` when no sign-in is cached (run `python -m outlook auth`), `502` when Graph fails.
