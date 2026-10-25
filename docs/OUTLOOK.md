# Outlook integration

One door into the mailbox. Everything else in the bridge, and anything outside it, reads from this door instead of calling Microsoft Graph on its own.

```
Outlook / Exchange Online
        │  Microsoft Graph (delegated, read-only)
        │  delta queries + optional webhooks
        ▼
 backend/outlook/            the integration point
   auth.py      MSAL device-code sign-in, token cache on disk
   graph.py     paging, delta rounds, 429 back-off
   privacy.py   the line personal items never cross
   sync.py      pull → local mirror → digest
   webhooks.py  Graph change notifications
   router.py    /api/outlook/*
        │
        ▼
 Digest JSON  (matrix-bridge.outlook-digest/1)
        │
        ├── second brain /sync  (Freedom repo, scripts/ingest-outlook-digest.py)
        ├── other agents
        └── anything that can read a file or call HTTP
```

## Why this shape

- **Delta, not date windows.** Graph hands back a `deltaLink` after each round. Store it, replay it next time, get only what changed. No more "7 days back and hope".
- **Mirror, not proxy.** Pulls land in `.outlook-state/` as JSON. The digest is built from the mirror, so a consumer never waits on Graph and never needs a token.
- **Filter at the source.** `privacy.py` runs before storage. Solo blocks, internal-only meetings and anything matching a personal keyword never reach disk. Downstream code cannot leak what it never saw.
- **Read-only scopes.** `Calendars.Read`, `Mail.Read`, `User.Read`. The bridge cannot send, move or delete. If a consumer needs to act, it goes through its own tool with its own approval gate.

## Setup

### 1. Register the app once (Microsoft Entra)

Entra admin center → App registrations → New registration.

| Setting | Value |
|---|---|
| Supported account types | Accounts in this organizational directory only |
| Redirect URI | leave blank |
| Authentication → Advanced → Allow public client flows | **Yes** |
| API permissions → Microsoft Graph → Delegated | `Calendars.Read`, `Mail.Read`, `User.Read` |

Grant admin consent if your tenant requires it. Copy the **Application (client) ID** and the **Directory (tenant) ID**.

### 2. Configure

```bash
cd backend
cp .env.example .env
# set OUTLOOK_TENANT_ID, OUTLOOK_CLIENT_ID, OUTLOOK_INTERNAL_DOMAINS, OUTLOOK_PERSONAL_KEYWORDS
pip install -r requirements.txt
```

### 3. Sign in once

```bash
python -m outlook auth
```

Prints a code and a URL. Sign in on any device. The refresh token lands in `.outlook-state/token_cache.json` (mode 600, gitignored) and renews itself silently from then on.

### 4. Pull and read

```bash
python -m outlook pull                       # one delta round, all folders
python -m outlook digest --since 2026-10-18  # JSON to stdout
python -m outlook digest --out digest.json   # last 7 days to a file
python -m outlook status
```

Or over HTTP once `python app.py` is running:

```
GET  /api/outlook/status
POST /api/outlook/pull
GET  /api/outlook/digest?since=2026-10-18T00:00:00Z&refresh=true
```

## Digest schema (`matrix-bridge.outlook-digest/1`)

```jsonc
{
  "schema": "matrix-bridge.outlook-digest/1",
  "generated_at": "...", "since": "...", "until": "...",
  "account": { "name": "...", "email": "...", "id": "..." },
  "events": [{
    "id": "...", "subject": "...", "start": "...", "end": "...", "time_zone": "UTC",
    "organizer": { "name": "...", "email": "..." },
    "attendees": [{ "name": "...", "email": "...", "type": "required", "response": "accepted" }],
    "external_attendees": ["..."],          // set by the privacy filter
    "is_online_meeting": true, "online_meeting_url": "...",
    "is_cancelled": false, "web_link": "...", "last_modified": "..."
  }],
  "upcoming": [ /* same shape as events: starts after `until`, not cancelled */ ],
  "messages": [{
    "id": "...", "folder": "inbox|sentitems|drafts", "conversation_id": "...",
    "subject": "...", "sender": {...}, "to": [...], "cc": [...],
    "counterparts": ["..."],                 // external addresses on the thread
    "received": "...", "sent": "...", "preview": "first 400 chars",
    "is_read": false, "is_draft": false, "has_attachments": false, "web_link": "..."
  }],
  "flags": {
    "stale_drafts": ["message ids untouched past OUTLOOK_STALE_AFTER_DAYS"],
    "unanswered":   ["newest inbound external message per conversation with no reply from the owner"],
    "contacts_seen": ["every external address in the window"]
  },
  "stats": { "events": 0, "upcoming": 0, "messages": 0, "stale_drafts": 0, "unanswered": 0, "contacts": 0, "mirror_events": 0, "mirror_messages": 0 }
}
```

Messages referenced by a flag are always present in `messages`, even when older than the window. Only additive changes bump the minor version. A breaking change gets a new schema id.

## Webhooks (optional, near real time)

Graph can push instead of waiting for a pull. Requires a public HTTPS URL.

```bash
# .env
OUTLOOK_NOTIFICATION_URL=https://your-host/api/outlook/notifications
OUTLOOK_CLIENT_STATE=<random string, 128 chars max>

python -m outlook subscribe     # creates or renews; subscriptions last under 7 days
```

Renew on a schedule (daily is plenty): `python -m outlook subscribe` is idempotent. Every notification is checked against `clientState`; a mismatch is logged and dropped. The endpoint answers 202 immediately and runs the pull in the background, which keeps Graph from retrying.

## Privacy filter contract

| Item | Kept when | Dropped when |
|---|---|---|
| Calendar event | at least one attendee or the organizer is outside `OUTLOOK_INTERNAL_DOMAINS` | no external people, or subject contains a personal keyword |
| Mail | at least one external address on from/to/cc | internal-only, or subject/preview contains a personal keyword |
| Draft | always (stale drafts are a flag the owner wants) | subject/preview contains a personal keyword |
| Removal | always propagates so the mirror forgets | never |

Keywords are matched case-insensitively as substrings. Keep the list short and specific.

## Operations

- `python -m outlook reset` clears delta links and the mirror. The next pull is a full window again. The token stays.
- Delta tokens expire after a long idle period. Graph returns 410 Gone; run `reset` and pull.
- Throttling (429) is retried with `Retry-After`, up to four times.
- Nothing here writes to the mailbox. Scopes make that a hard guarantee, not a convention.

## Tests

```bash
cd backend && pytest tests/test_outlook_*.py
```

Runs against a scripted fake Graph (`tests/conftest.py`). No network, no token.
