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
