# 🤖 agentic-ReAct

> **FastAPI · Hexagonal Architecture · ReAct Agent · Streaming SSE · Function Calling · LangChain**

A production-ready implementation of a **ReAct (Reason + Act) agent** built with FastAPI and strict Hexagonal Architecture. The agent reasons step-by-step using a `Thought → Action → Observation` loop, calls external tools via **Function Calling**, and streams its reasoning to clients via **Server-Sent Events (SSE)**.

---

## ✨ Features

| Feature | Details |
|---|---|
| **ReAct reasoning loop** | `Thought → Action → Observation → Final Answer` |
| **Function Calling tools** | `get_erp_data` (MySQL) · `calculate_tax_discrepancy` (Python) · `search_regulations` (RAG) |
| **Tool chaining** | Agent chains `get_erp_data → calculate_tax_discrepancy` automatically |
| **Token Streaming** | SSE via `StreamingResponse` — real-time reasoning, events typed per step |
| **LLM abstraction** | Swap OpenAI ↔ Claude ↔ LangChain via `LLM_PROVIDER` env var — zero code changes |
| **RAG + Metadata Filtering** | ChromaDB (real embeddings) or SimulatedRAG · year/region/category filters avoid retrieval noise |
| **Security Middleware** | Prompt injection guard · Sensitive data blocker · RBAC (operator/viewer/auditor) · API Key auth |
| **Rate Limiting** | Sliding-window in-memory rate limiter (20 req/min per key) |
| **Error handling** | Typed SSE error events for `LLM_UNAVAILABLE`, `ERP_UNAVAILABLE`, `AGENT_ERROR` |
| **Hexagonal Architecture** | Domain → Application → Infrastructure → API — fully decoupled layers |
| **Docker Compose** | MySQL 8.4 + FastAPI in one command — DB healthcheck gates app startup |
| **Test suite** | 38 unit tests — zero external deps required (mocked LLM, in-memory RAG corpus) |

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
│   ToolRegistry (get_erp_data · calculate_tax_discrepancy · search_regulations) │
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
│  OpenAIAdapter · ClaudeAdapter · LangChainAdapter     │
│  MySQLERPAdapter · MySQLConversationAdapter           │
│  ChromaRAGAdapter · SimulatedRAGAdapter               │
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
│   │   ├── tools/          # ToolRegistry · tax_tool (calculate_tax_discrepancy)
│   │   └── use_cases/      # RunAgentUseCase, GetConversationHistoryUseCase
│   ├── infrastructure/
│   │   ├── llm/            # OpenAIAdapter · ClaudeAdapter · LangChainAdapter · LLMFactory
│   │   ├── db/             # MySQLERPAdapter · MySQLConversationAdapter
│   │   └── rag/            # ChromaRAGAdapter · SimulatedRAGAdapter
│   ├── api/
│   │   ├── v1/routers/     # agent_router (SSE) · health_router
│   │   ├── v1/schemas/     # ChatRequest · SSEEvent (Pydantic)
│   │   └── middleware/     # SecurityMiddleware · RateLimitMiddleware
│   ├── config/settings.py  # Pydantic BaseSettings (all env vars)
│   ├── dependencies.py     # FastAPI DI wiring
│   └── main.py             # App factory + lifespan
├── data/
│   └── regulations.json    # RAG corpus — 12 logistics/customs regulations
├── sql/
│   └── init.sql            # MySQL schema + seed data (10 shipments, 5 users)
├── tests/
│   ├── unit/
│   │   ├── test_react_orchestrator.py   # ReAct loop + tool chaining (6 tests)
│   │   ├── test_security_middleware.py  # Security + RBAC + tax tool (18 tests)
│   │   └── test_rag_adapter.py          # RAG + metadata filtering (12 tests)
│   └── integration/
│       └── test_agent_endpoint.py       # SSE endpoint (mocked LLM)
├── docker-compose.yml      # MySQL + FastAPI — full stack in one command
├── Dockerfile
├── .env.example
├── postman_collection.json # 20 ready-to-run requests covering all eval criteria
└── requirements.txt
```

---

## 🚀 Deployment

### Option A — Docker Compose (recommended)

The fastest way to run the full stack. The `api` service waits for MySQL to be healthy before starting.

**1. Clone and configure**

```bash
git clone <repo-url>
cd agentic-ReAct
cp .env.example .env
```

Edit `.env` and set at minimum:

```dotenv
# Pick one provider
LLM_PROVIDER=openai          # or: claude | langchain
OPENAI_API_KEY=sk-...        # required for openai + langchain
ANTHROPIC_API_KEY=sk-ant-... # required for claude

# RAG backend (simulated works with no API key)
RAG_PROVIDER=simulated       # or: chroma (requires OPENAI_API_KEY for embeddings)
```

**2. Build and start**

```bash
docker compose up --build
```

Both services start in the correct order:

```
react_db   → MySQL 8.4 initialises and seeds data
react_api  → waits for DB healthcheck, then starts Uvicorn on :8000
```

**3. Verify**

```bash
curl http://localhost:8000/health
# {"status": "ok", "service": "agentic-ReAct"}
```

**Stop everything**

```bash
docker compose down          # keeps DB volume
docker compose down -v       # also removes DB data (clean slate)
```

**Rebuild only the API** (after code changes, without touching the DB):

```bash
docker compose up --build api
```

---

### Option B — Local development (without Docker)

Requires Python 3.12+ and a running MySQL instance (or use `docker compose up db` to start only the database).

**1. Create virtual environment**

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure environment**

```bash
cp .env.example .env
# Edit .env — set OPENAI_API_KEY (or ANTHROPIC_API_KEY) and DB credentials
```

If you want MySQL without a local install, start only the DB container:

```bash
docker compose up db
# Then set in .env:
MYSQL_HOST=localhost
```

**4. Run the server**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

### Option C — Run tests (no infrastructure needed)

All 38 unit tests run with mocked LLM, in-memory RAG corpus and no DB connection:

```bash
pip install -r requirements.txt
pytest tests/unit/ -v
```

Expected output: **38 passed**.

```
tests/unit/test_rag_adapter.py            12 passed  # RAG + metadata filtering
tests/unit/test_react_orchestrator.py      6 passed  # ReAct loop + tool chaining
tests/unit/test_security_middleware.py    18 passed  # Security + RBAC + tax tool
```

---

## 🧪 Testing the API

### Quick SSE test (curl)

```bash
curl -N -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-12345" \
  -d '{
    "query": "Get shipment shp-001 from the ERP and validate the tax: declared 210 EUR on a 1000 EUR invoice from Spain",
    "user_id": "user-001",
    "user_context": {"role": "logistics_manager"}
  }'
```

**Example SSE response (tool chaining):**

```
event: thought
data: {"content": "I need to first retrieve the shipment from ERP, then validate the tax."}

event: action
data: {"tool_name": "get_erp_data", "tool_input": {"action": "get_shipment", "shipment_id": "shp-001"}}

event: observation
data: {"content": "[Result from get_erp_data]: {\"id\": \"shp-001\", \"status\": \"in_transit\", \"origin\": \"Madrid, ES\"}"}

event: action
data: {"tool_name": "calculate_tax_discrepancy", "tool_input": {"amount": 1000.0, "region": "ES", "declared_tax": 210.0}}

event: observation
data: {"content": "[Result from calculate_tax_discrepancy]: {\"status\": \"OK\", \"expected_tax\": 210.0, \"discrepancy\": 0.0}"}

event: final_answer
data: {"content": "Shipment shp-001 is in transit from Madrid. The declared tax of 210 EUR is correct (Spain VAT 21% on 1000 EUR = 210 EUR). No discrepancy."}

event: done
data: {"conversation_id": "...", "total_steps": 5}
```

### Postman Collection

Import `postman_collection.json` — 20 requests organised by evaluation criteria:

| Folder | Requests | What it tests |
|---|---|---|
| `1 · Agent — Core` | 5 | ERP query · tool chaining OK · UNDER_DECLARED · list_shipments · multi-turn |
| `2 · RAG Pipeline` | 3 | year=2024 filter · contrast (no filter) · year=2021 filter |
| `3 · Error Handling` | 3 | ERP not found · LLM unavailable · ERP unreachable (DB down) |
| `4 · Security` | 12 | Auth · 3× injection · 2× sensitive data · 4× RBAC · rate limit |
| `5 · Conversations` | 3 | Get by ID · list by user · 404 not found |

Set the collection variable `api_key` to `dev-key-12345` (default dev key from `.env.example`).

---

## 🔧 Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` · `claude` · `langchain` |
| `OPENAI_API_KEY` | — | Required for `openai` and `langchain` providers |
| `ANTHROPIC_API_KEY` | — | Required for `claude` provider |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI / LangChain model name |
| `ANTHROPIC_MODEL` | `claude-3-5-sonnet-20241022` | Anthropic model name |
| `RAG_PROVIDER` | `chroma` | `simulated` (keyword, no API key) · `chroma` (real embeddings) |
| `AGENT_MAX_ITERATIONS` | `10` | Max ReAct reasoning steps before forced answer |
| `VALID_API_KEYS` | `["dev-key-12345"]` | JSON array — application-level auth keys (`X-API-Key` header) |
| `RATE_LIMIT_REQUESTS` | `20` | Max requests per window per key |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit sliding window |
| `MYSQL_HOST` | `db` | DB hostname (`db` inside Docker, `localhost` for local dev) |
| `MYSQL_PORT` | `3306` | DB port |
| `MYSQL_USER` | `reactuser` | DB user |
| `MYSQL_PASSWORD` | `reactpass` | DB password |
| `MYSQL_DATABASE` | `react_db` | DB name |
| `LLM_MAX_TOKENS` | `4096` | Max tokens per LLM response |
| `LLM_TEMPERATURE` | `0.0` | LLM temperature (0 = deterministic) |
| `DEBUG` | `false` | Enable debug logging |

---

## 🔄 Switching LLM Providers

No code changes required — set `LLM_PROVIDER` in `.env` and restart:

```dotenv
# OpenAI (default)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# LangChain (ChatOpenAI + LangSmith tracing)
LLM_PROVIDER=langchain
OPENAI_API_KEY=sk-...

# Anthropic Claude
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 🛡️ Security

Every request passes through `SecurityMiddleware` before reaching the router:

| Check | Status code | Trigger |
|---|---|---|
| Missing / invalid `X-API-Key` | `401` | Key absent or not in `VALID_API_KEYS` |
| Prompt injection detected | `400` | 19 regex patterns (ignore instructions, DAN, jailbreak, SQL injection…) |
| Sensitive data request | `403` | Keywords: `salary`, `password`, `SSN`, `credit card`, `bank account`… |
| RBAC violation — `operator` | `403` | Bulk queries, financial reports |
| RBAC violation — `viewer` | `403` | Mutations (delete, cancel, approve…) |
| RBAC violation — `auditor` | `403` | Direct personal data or user profile access |
| Query too long | `422` | Prompt > 4096 characters |
| Rate limit exceeded | `429` | > 20 requests / 60 s per key |

Additionally, `MySQLERPAdapter` strips `salary`, `password_hash`, `ssn`, `credit_card` columns at the SQL result level — a second defence layer independent of the middleware.

---

## 🗄️ Database Schema

```sql
users         — id, username, email, full_name, department, role, salary*, password_hash*
conversations — id, user_id, messages (JSON), user_context (JSON), rag_id, timestamps
shipments     — id, tracking_number, status, origin, destination, estimated_delivery,
                weight_kg, carrier, user_id, created_at
```

> `*` `salary` and `password_hash` exist in the DB to simulate a real ERP but are **always filtered** by the adapter before the agent sees them.

**Seed data (10 shipments, 5 users):**

| Shipment | Status | Route | Carrier |
|---|---|---|---|
| shp-001 | in_transit | Madrid → Paris | DHL Express |
| shp-002 | delivered | Barcelona → London | FedEx |
| shp-003 | pending | Berlin → Rome | UPS Freight |
| shp-006 | in_transit | Vienna, AT → Prague | DHL Freight |
| shp-010 | in_transit | Copenhagen → Oslo | DB Schenker |

---

## 📋 API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | ✗ | Health check |
| `POST` | `/api/v1/chat` | ✓ | ReAct agent — SSE stream |
| `GET` | `/api/v1/conversations/{id}` | ✓ | Get conversation by UUID |
| `GET` | `/api/v1/conversations?user_id=` | ✓ | List user conversations |
| `GET` | `/docs` | ✗ | Swagger UI |
| `GET` | `/redoc` | ✗ | ReDoc |

### POST `/api/v1/chat` — request body

```json
{
  "query": "string — the user question",
  "user_id": "string",
  "conversation_id": "uuid — optional, continues an existing conversation",
  "user_context": {
    "role": "logistics_manager | operator | viewer | auditor | compliance_officer",
    "language": "en"
  },
  "rag_id": "string — optional, scopes RAG retrieval to a specific document set"
}
```

### SSE event types

| Event | Payload |
|---|---|
| `thought` | `{"content": "..."}` |
| `action` | `{"tool_name": "...", "tool_input": {...}}` |
| `observation` | `{"content": "..."}` |
| `final_answer` | `{"content": "..."}` |
| `done` | `{"conversation_id": "uuid", "total_steps": N}` |
| `error` | `{"code": "LLM_UNAVAILABLE \| ERP_UNAVAILABLE \| AGENT_ERROR", "detail": "...", "retry": bool}` |
