# 🤖 agentic-ReAct

> **FastAPI · Hexagonal Architecture · ReAct Agent · Streaming SSE · Function Calling**

A production-ready implementation of a **ReAct (Reason + Act) agent** built with FastAPI and strict Hexagonal Architecture. The agent reasons step-by-step using a `Thought → Action → Observation` loop, calls external tools via **Function Calling**, and streams its reasoning to clients via **Server-Sent Events (SSE)**.

---

## ✨ Features

| Feature | Details |
|---|---|
| **ReAct reasoning loop** | `Thought → Action → Observation → Final Answer` |
| **Function Calling tools** | `get_erp_data` (MySQL) · `search_regulations` (RAG) |
| **Token Streaming** | SSE via `StreamingResponse` — real-time reasoning |
| **LLM abstraction** | Swap OpenAI ↔ Claude via `LLM_PROVIDER` env var |
| **Security Middleware** | Prompt injection guard · Sensitive data blocker · API Key auth |
| **Rate Limiting** | Sliding-window in-memory rate limiter |
| **Hexagonal Architecture** | Domain → Application → Infrastructure → API |
| **Docker Compose** | MySQL 8.4 + FastAPI, fully containerised |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                     API Layer                        │
│  FastAPI Routers · SSE Streaming · Pydantic Schemas  │
│  SecurityMiddleware · RateLimitMiddleware             │
└──────────────────────┬──────────────────────────────┘
                       │ Depends()
┌──────────────────────▼──────────────────────────────┐
│                 Application Layer                     │
│   RunAgentUseCase · ReactOrchestrator                 │
│   ToolRegistry (get_erp_data, search_regulations)    │
└──────────────────────┬──────────────────────────────┘
                       │ Ports (interfaces)
┌──────────────────────▼──────────────────────────────┐
│                   Domain Layer                        │
│  AgentState · ReActStep · Conversation · Tool         │
│  LLMPort · ERPPort · RAGPort · ConversationRepoPort  │
└──────────────────────┬──────────────────────────────┘
                       │ Adapters (implementations)
┌──────────────────────▼──────────────────────────────┐
│               Infrastructure Layer                    │
│  OpenAIAdapter · ClaudeAdapter · LLMFactory           │
│  MySQLERPAdapter · MySQLConversationAdapter           │
│  SimulatedRAGAdapter                                  │
└─────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
agentic-ReAct/
├── app/
│   ├── domain/
│   │   ├── entities/       # AgentState, Conversation, Tool (pure Python)
│   │   └── ports/          # Abstract interfaces (LLMPort, ERPPort, RAGPort…)
│   ├── application/
│   │   ├── services/       # ReactOrchestrator — the ReAct loop engine
│   │   ├── tools/          # ToolRegistry — dispatches tool calls
│   │   └── use_cases/      # RunAgentUseCase, GetConversationHistoryUseCase
│   ├── infrastructure/
│   │   ├── llm/            # OpenAIAdapter, ClaudeAdapter, LLMFactory
│   │   ├── db/             # MySQLERPAdapter, MySQLConversationAdapter
│   │   └── rag/            # SimulatedRAGAdapter (keyword search over JSON)
│   ├── api/
│   │   ├── v1/routers/     # agent_router (SSE), health_router
│   │   ├── v1/schemas/     # ChatRequest, SSEEvent (Pydantic)
│   │   └── middleware/     # SecurityMiddleware, RateLimitMiddleware
│   ├── config/settings.py  # Pydantic BaseSettings
│   ├── dependencies.py     # FastAPI DI wiring
│   └── main.py             # App factory
├── sql/init.sql            # MySQL schema + seed data
├── data/regulations.json   # RAG corpus (12 logistics regulations)
├── tests/
│   ├── unit/               # Orchestrator + Security middleware tests
│   └── integration/        # SSE endpoint tests
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── requirements.txt
```

---

## 🚀 Quick Start

### 1. Clone and configure

```bash
git clone <repo-url>
cd agentic-ReAct
cp .env.example .env
# Edit .env — set your OPENAI_API_KEY or ANTHROPIC_API_KEY
```

### 2. Start with Docker Compose

```bash
docker compose up --build
```

The API will be available at `http://localhost:8000`.

### 3. Test the streaming endpoint

```bash
curl -N -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-12345" \
  -d '{
    "query": "What shipments are currently in transit?",
    "user_id": "user-001"
  }'
```

**Example SSE response stream:**

```
event: thought
data: {"step_type": "thought", "content": "I need to query the ERP system for in-transit shipments."}

event: action
data: {"step_type": "action", "tool_name": "get_erp_data", "tool_input": {"action": "list_shipments", "status": "in_transit"}}

event: observation
data: {"step_type": "observation", "content": "[Result from get_erp_data]: [{'id': 'shp-001', ...}]"}

event: final_answer
data: {"step_type": "final_answer", "content": "There are currently 3 shipments in transit: ..."}

event: done
data: {"conversation_id": "...", "total_steps": 4}
```

---

## 🔧 Configuration

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` or `claude` |
| `OPENAI_API_KEY` | — | Required if using OpenAI |
| `ANTHROPIC_API_KEY` | — | Required if using Claude |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model name |
| `ANTHROPIC_MODEL` | `claude-3-5-sonnet-20241022` | Anthropic model name |
| `AGENT_MAX_ITERATIONS` | `10` | Max ReAct reasoning steps |
| `VALID_API_KEYS` | `["dev-key-12345"]` | Allowed API keys (JSON array) |
| `RATE_LIMIT_REQUESTS` | `20` | Max requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window |

---

## 🛡️ Security

The `SecurityMiddleware` runs on every request and enforces:

1. **API Key validation** — header `X-API-Key` must be in `VALID_API_KEYS`
2. **Prompt injection detection** — blocks patterns like *"ignore all previous instructions"*, `jailbreak`, SQL injection, XSS
3. **Sensitive data guard** — blocks queries containing `salary`, `password`, `SSN`, `credit card`, etc.
4. **Max length** — rejects prompts longer than 4096 characters

---

## 🔄 Switching LLM Providers

```bash
# Use Claude
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...

# Use OpenAI (default)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

No code changes required — the `LLMFactory` handles instantiation.

---

## 🧪 Running Tests

```bash
pip install -r requirements.txt
pytest -v
```

---

## 📊 Database Schema

```sql
users        — id, username, email, full_name, department, role, salary*, password_hash*
conversations — id, user_id, messages (JSON), user_context (JSON), rag_id, timestamps
shipments    — id, tracking_number, status, origin, destination, estimated_delivery,
               weight_kg, carrier, user_id, created_at
```
> *`salary` and `password_hash` are present in the DB to simulate a real ERP but are **always filtered out** by the adapter before exposure to the agent.

---

## 📋 API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/chat` | ReAct agent (SSE stream) |
| `GET` | `/api/v1/conversations/{id}` | Get conversation by ID |
| `GET` | `/api/v1/conversations?user_id=` | List user conversations |
| `GET` | `/docs` | Swagger UI |

