# Matrix Bridge Architecture

## System Overview

Matrix Bridge is a bidirectional sync system that keeps Claude and ChatGPT conversations in perfect sync through a central context hub.

### Core Components

1. **Browser Extension**
   - Monitors claude.ai and chat.openai.com
   - Captures interactions in real-time
   - Communicates with backend API

2. **Backend API (FastAPI)**
   - Manages sync state
   - Stores conversation history
   - Handles approval queue
   - Synthesizes context

3. **Vector Database**
   - Stores embeddings for semantic search
   - Enables cross-model context retrieval

4. **Approval Dashboard**
   - User reviews pending syncs
   - Manages sync rules
   - Tracks sync history

## Data Flow

```
User Action on Claude/GPT
       ↓
   Extension captures
       ↓
   Send to API
       ↓
   Store + Analyze
       ↓
   Check approval rules
       ↓
   If new project: Add to approval queue
       ↓
   Synthesize context
       ↓
   Inject into target LLM
       ↓
   Target LLM learns automatically
```

## Database Schema

### sync_events
- Stores all sync operations
- Tracks source/target, status, timestamps

### projects
- Groups conversations by project
- Tags: "project-Claude" or "project-GPT"

### user_settings
- Sync rules per user
- Approval gates
- Persistence preferences

## Security Considerations

- All API communication encrypted (HTTPS)
- User approval gates for sensitive operations
- Vector DB separate from sensitive data
- Rate limiting on sync operations
