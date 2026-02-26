# GithubAutoLark Architecture

## Senior Architect Review - February 2026

### Current Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │   CLI       │  │  chat.py    │  │   Web UI    │  <- TODO        │
│  │ (test_*.py) │  │  (new)      │  │  (planned)  │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        AGENT LAYER (LangGraph)                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Supervisor (LLM-enhanced)                                    │  │
│  │  - Intent Classification (keyword + LLM)                      │  │
│  │  - Entity Extraction                                          │  │
│  │  - Command Enhancement                                        │  │
│  │  - Conversational Memory                                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│         │              │              │              │              │
│         ▼              ▼              ▼              ▼              │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐       │
│  │  Member   │  │  GitHub   │  │   Lark    │  │   Sync    │       │
│  │  Agent    │  │  Agent    │  │   Agent   │  │   Agent   │       │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        SERVICE LAYER                                │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │
│  │ GitHubService │  │ LarkService   │  │ MemberService │           │
│  │ (REST API)    │  │ (MCP + Direct)│  │ (local)       │           │
│  └───────────────┘  └───────────────┘  └───────────────┘           │
│  ┌───────────────┐  ┌───────────────┐                              │
│  │ SyncEngine    │  │ LLMProcessor  │                              │
│  │ (outbox)      │  │ (OpenAI API)  │                              │
│  └───────────────┘  └───────────────┘                              │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                                   │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │
│  │ Members       │  │ Tasks         │  │ Mappings      │           │
│  │ Repository    │  │ Repository    │  │ Repository    │           │
│  └───────────────┘  └───────────────┘  └───────────────┘           │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │
│  │ Outbox        │  │ SyncLog       │  │ LarkTable     │           │
│  │ Repository    │  │ Repository    │  │ Repository    │           │
│  └───────────────┘  └───────────────┘  └───────────────┘           │
│                              │                                      │
│                              ▼                                      │
│                    ┌───────────────┐                                │
│                    │   SQLite DB   │                                │
│                    │  (local)      │                                │
│                    └───────────────┘                                │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Local DB as Source of Truth** - All member/task data syncs through local SQLite
2. **Outbox Pattern** - Async sync via outbox queue for reliability
3. **Dependency Injection** - Services injected into agents at build time
4. **LLM Enhancement** - Optional LLM for natural language understanding

### Gaps Identified

| Gap | Impact | Priority |
|-----|--------|----------|
| No Web UI | Users can't access via browser | HIGH |
| No due dates | Can't track deadlines | HIGH |
| No progress % | Can't track completion | MEDIUM |
| No webhooks | Manual sync only | MEDIUM |
| Limited tests | Low confidence in sync | HIGH |

### Improvement Plan

#### Phase 1: Core Features (Current Sprint)
1. ✅ Add due dates to tasks
2. ✅ Add progress tracking
3. ✅ Improve assignee sync
4. ✅ Create web server

#### Phase 2: Frontend
1. Simple HTML chat interface
2. Task dashboard
3. Member directory

#### Phase 3: Advanced
1. Webhook listeners for real-time sync
2. Slack/Teams integration
3. Mobile-friendly UI

### File Structure

```
GithubAutoLark/
├── src/
│   ├── agent/              # LangGraph agents
│   │   ├── graph.py        # Original graph
│   │   ├── enhanced_graph.py # LLM-enhanced graph
│   │   ├── llm_supervisor.py # LLM intent classifier
│   │   ├── supervisor.py   # Keyword classifier
│   │   ├── *_agent.py      # Sub-agents
│   │   └── tools/          # Agent tools
│   ├── db/                 # Data layer
│   │   ├── database.py     # SQLite connection
│   │   ├── schema.py       # Table definitions
│   │   └── *_repo.py       # Repositories
│   ├── models/             # Domain models
│   ├── services/           # External APIs
│   │   ├── github_service.py
│   │   ├── lark_service.py
│   │   └── lark_token_manager.py
│   └── sync/               # Sync logic
├── server/                 # NEW: Web server
│   ├── app.py              # FastAPI app
│   ├── routes/             # API endpoints
│   └── static/             # HTML/CSS/JS
├── tests/                  # Test suite
├── demos/                  # Demo scripts
├── chat.py                 # CLI chat interface
└── data/                   # SQLite databases
```

### API Design (Planned)

```
POST /api/chat              # Natural language chat
GET  /api/members           # List members
POST /api/members           # Create member
GET  /api/tasks             # List tasks
POST /api/tasks             # Create task
GET  /api/issues            # List GitHub issues
POST /api/issues            # Create issue
GET  /api/sync/status       # Sync status
POST /api/sync/run          # Trigger sync
```
