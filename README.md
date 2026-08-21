# Matrix Bridge 🌉

**Bidirectional context synchronization between Claude and ChatGPT.**

A seamless bridge that keeps your Claude and GPT conversations in perfect sync—neither knows they're separate. If one learns something, the other knows it. If you create something in one, it appears in the other (with user approval gates).

## Vision

```
Claude.ai ←→ [MATRIX BRIDGE] ←→ ChatGPT.com
  (work)      (context sync)      (work)
             (transparent)
```

Think of it like a **Matrix-style data bridge** where both LLMs operate as extensions of each other, with minimal user friction and intelligent, code-driven context synthesis.

## Core Features

- **Bidirectional Sync**: Changes in Claude auto-sync to GPT and vice versa
- **Smart Approval Gates**: User controls what syncs (new projects flagged, sensitive changes require review)
- **Code Synthesis**: Conversations compressed into minimal, runnable code (reduces token bloat)
- **Semantic Memory**: Each LLM learns from the other's work as if it did it
- **Project Tagging**: Auto-tag syncs with source (`"project-Claude"` ↔ `"project-GPT"`)
- **LLM-Driven Persistence**: Uses LLM logic to decide what to remember and how long
- **Vector Embeddings**: Semantic search across both conversation histories

## Architecture

### Components

1. **Browser Extension** - Captures interactions from claude.ai & chatgpt.com
2. **Backend API** - FastAPI + Vector Database (context hub)
3. **Sync Engine** - Handles bidirectional sync with conflict resolution
4. **Approval Queue** - User review UI for sensitive syncs
5. **CLI Tool** - Manual sync triggers and diagnostics
6. **Dashboard** - Settings, history, and sync management
7. **MCP Server** - Standalone stdio MCP server exposing the sync loop as tools, so Claude and ChatGPT can each connect directly (see below)

### Data Flow

```
User Action (Claude/GPT)
    ↓
Browser Extension captures
    ↓
Is new project? → Flag for approval
    ↓
Extract + Synthesize context
    ↓
Approval Queue (if needed)
    ↓ [User approves]
    ↓
Push to Context Hub
    ↓
Inject into waiting LLM
    ↓
LLM learns automatically
```

## Tech Stack

- **Backend**: FastAPI, PostgreSQL, Pinecone/Weaviate (vector DB)
- **Extension**: Chrome/Firefox WebExtension API
- **CLI**: Python Click
- **Frontend**: React + TailwindCSS
- **LLM SDKs**: Anthropic SDK, OpenAI SDK

## Project Structure

```
matrix-bridge/
├── backend/                 # FastAPI server
│   ├── app.py
│   ├── models/             # Data models
│   ├── sync/               # Sync engine logic
│   ├── approval/           # Approval queue
│   ├── mcp_server/         # Standalone MCP server (stdio, SQLite-backed)
│   └── persistence/        # Vector DB + storage
├── extension/              # Browser extension
│   ├── manifest.json
│   ├── content-script.js   # Page interaction capture
│   ├── background.js       # Sync orchestration
│   └── popup/              # Settings UI
├── cli/                    # Command-line tool
├── dashboard/              # React approval UI
├── docs/                   # Architecture & setup guides
├── tests/
└── docker-compose.yml      # Local dev environment
```

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Claude API key (Anthropic)
- ChatGPT API key (OpenAI)
- Docker (for local dev)

### Local Development

```bash
# Clone
git clone https://github.com/Bwallace16/matrix-bridge.git
cd matrix-bridge

# Backend setup
cd backend
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
python app.py

# Extension setup (Chrome)
cd ../extension
npm install
npm run build
# Load unpacked extension from `dist/` in chrome://extensions

# Dashboard
cd ../dashboard
npm install
npm start  # Runs on http://localhost:3000
```

## ChatGPT / Claude MCP Connector

For a working bridge today—without standing up Postgres/Pinecone/Weaviate—use
the standalone MCP server in `backend/mcp_server/`. It's a stdio MCP server
backed by local SQLite that exposes the sync loop (`capture_context`,
`get_context`, `list_projects`, `list_pending_approvals`, `approve_sync`) as
tools any MCP client can call, including ChatGPT's "Connect to a custom MCP"
dialog and Claude Desktop/Code.

```bash
cd backend
pip install -r mcp_server/requirements.txt
python3 -m mcp_server
```

See [docs/CHATGPT_MCP_SETUP.md](./docs/CHATGPT_MCP_SETUP.md) for the exact
field values to paste into ChatGPT's custom MCP connector form.

## Configuration

### User Sync Rules

Control what syncs and what requires approval:

```json
{
  "autoSyncTypes": ["message", "code", "output"],
  "requireApprovalFor": ["file", "new_project", "system_prompt"],
  "persistenceMode": "llm_driven",
  "tokenLimit": 2000
}
```

### Project Tagging

New projects auto-tagged:
- `"my-project-Claude"` → syncs to GPT as `"my-project-GPT"`
- Requires user approval on first sync

## API Overview

### Core Endpoints

```
POST /api/sync/capture
  Capture interaction from browser

GET /api/projects
  List all synced projects

POST /api/approval/review
  User reviews pending syncs

GET /api/context/{project-id}
  Retrieve synthesized context

POST /api/settings/update
  Update sync rules
```

See [API Docs](./docs/API.md) for full reference.

## How It Works

### Example: New Project Sync

1. **User** creates conversation in Claude about building a REST API
2. **Extension** captures the conversation + code snippets
3. **Backend** tags it: `"rest-api-Claude"`
4. **Approval Queue** notifies user: *"New project detected: sync to GPT?"*
5. **User approves** via dashboard
6. **Sync Engine** synthesizes the conversation into minimal context
7. **Backend** injects it into GPT's system context
8. **GPT** sees the work as if it did it: *"I see I was building a REST API with FastAPI..."*
9. **Next Claude session** gets GPT's insights automatically injected

### Conflict Resolution

If both LLMs edit the same file simultaneously:
- **Automatic**: Diff-merge with LLM-driven conflict resolution
- **Manual**: User review UI shows both versions

## Development Roadmap

- [ ] Backend API scaffold
- [x] Standalone MCP server for ChatGPT/Claude connectors (stdio + SQLite)
- [ ] Browser extension (Chrome/Firefox)
- [ ] Vector DB integration
- [ ] Approval dashboard
- [ ] CLI tool
- [ ] Conflict resolution engine
- [ ] Rate limiting & cost tracking
- [ ] Multi-workspace support
- [ ] Audit logging

## Contributing

Contributions welcome! See [CONTRIBUTING.md](./CONTRIBUTING.md)

## License

MIT

---

**Built to dissolve the boundary between Claude and ChatGPT.**
