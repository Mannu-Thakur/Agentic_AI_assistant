# Enterprise GenAI Intelligence Platform — Multi-Agent Workspace v3.0

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3+-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://reactjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5+-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent_Supervisor-FF6F00?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Store-FC521F?style=for-the-badge)](https://www.trychroma.com)
[![Redis](https://img.shields.io/badge/Redis-Cache_%26_Rate_Limiting-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

> A production-grade **Multi-Agent AI Workspace** — not just a chatbot. Features a **LangGraph Supervisor Orchestrator** with 7 specialized agents, **Mission Mode** for complex multi-step tasks, **real-time plan DAG visualization**, **critic quality loop with auto-retry**, **persistent artifact store**, **cost & latency dashboard**, and full **human-in-the-loop (HITL)** gating — all backed by a 14-node agentic workflow, hybrid RAG, and enterprise-grade infrastructure.

---

## Table of Contents

- [What Is This?](#-what-is-this)
- [Architecture — Multi-Agent System](#-architecture--multi-agent-system)
- [Mission Mode](#-mission-mode)
- [Specialized Agents (7)](#-specialized-agents-7)
- [Key Capabilities](#-key-capabilities)
- [Tech Stack](#-tech-stack)
- [Quick Start](#-quick-start)
- [Environment Variables](#-environment-variables)
- [API Reference](#-api-reference)
- [Changelog](#-changelog)

---

## 🤖 What Is This?

This platform started as a chatbot and has been transformed into a **production-grade multi-agent AI workspace**. The key architectural shift:

| Before | After |
|--------|-------|
| Single LLM call per message | Supervisor orchestrates N specialized agents in parallel |
| Response lost on refresh | All messages persisted to database |
| No task decomposition | Planner decomposes complex tasks into agent sub-queries |
| No quality checking | Critic agent scores output; auto-retries if score < 0.65 |
| Blocking HTTP for long tasks | Async job queue — immediate job ID, reconnectable SSE stream |
| No visibility into execution | Real-time Plan DAG visualization + Agent Trace Panel |

---

## 🏗️ Architecture — Multi-Agent System

```
User Query
    │
    ▼
Supervisor Classify (LLM Planner)
    │
    ├─ SIMPLE ──────────────────▶ Single Agent Graph ──▶ Response
    │
    └─ MISSION ─────────────────▶ Parallel Dispatch (asyncio fan-out)
                                         │
                              ┌──────────┼──────────┐
                              ▼          ▼          ▼
                          web_research  code      rag ...   (run concurrently)
                              │          │          │
                              └──────────┴──────────┘
                                         │
                                   Result Collector
                                         │
                                  Critic Verification
                                    score < 0.65?
                                    ┌────┴────┐
                               YES  │         │  NO
                               (retry ≤2)     │
                                    │    HITL Gate?
                            supervisor_classify  │
                            (re-plan w/ feedback)│
                                              Synthesizer
                                                 │
                                           Final Response
                                    (persisted to DB + chat)
```

### Job Queue Flow (non-blocking)
```
POST /mission/run  →  job_id returned immediately
GET  /mission/{id}/stream  →  reconnectable SSE (Last-Event-ID support)
GET  /mission/{id}         →  polling fallback
POST /mission/persist      →  save to DB after completion
```

---

## ⚡ Mission Mode

**Mission Mode** activates when a user submits a complex, multi-step task. The system:

1. **Plans** — LLM planner classifies intent and selects agents + sub-queries
2. **Dispatches** — Selected agents run **in parallel** via `asyncio.gather()`
3. **Collects** — Results merged into a unified context block
4. **Critiques** — Critic agent scores quality (0–1); if score < 0.65 and retries < 2, re-plans
5. **Gates** — Risky actions (code execution, external writes) trigger HITL approval
6. **Synthesizes** — LLM produces clean Markdown response from all agent outputs
7. **Persists** — User query + response saved as real DB messages (survives refresh)

### Triggering Mission Mode
Click **⚡ Mission Mode** in the chat input, then send a complex query:
- *"Research the latest AI agent frameworks and write a Python implementation example"*
- *"Analyze my uploaded sales data and create a PowerPoint presentation with insights"*
- *"Find current best practices for React performance and refactor my component"*

---

## 🤖 Specialized Agents (7)

| Agent | Trigger | What it does |
|-------|---------|-------------|
| **web_research** | Anything needing current/external data | Searches the web via unified search API, extracts and summarizes content |
| **code** | Coding, scripting, implementation | Generates, validates, and sandboxes code execution |
| **rag** | Questions about uploaded documents | ChromaDB + BM25 hybrid retrieval, cross-encoder reranking, cited answers |
| **data_analysis** | CSV/data files, statistics, charts | Pandas-based analysis, statistical insights, pattern detection |
| **document** | "Create a presentation/report/doc" | Generates PPTX (python-pptx) and DOCX (python-docx) artifacts |
| **vision** | Image provided | Multimodal LLM analysis (Gemini/GPT-4o), Tesseract OCR fallback |
| **critic** | Runs automatically after all others | Hallucination detection, citation validation, quality score 0–1 |

All agents self-register via `@agent_registry.register("name")` decorator. New agents are one file.

---

## 🔑 Key Capabilities

### Multi-Agent Infrastructure
- **LangGraph Supervisor** — `StateGraph` with conditional routing, `MemorySaver` checkpointing
- **Critic Retry Loop** — Auto-retries with critic feedback injected into planner (max 2 cycles)
- **HITL Gate** — Interrupt before synthesizer for human approval of risky actions
- **Async Job Queue** — `asyncio.Queue` worker, reconnectable SSE with `Last-Event-ID`
- **Artifact Store** — Filesystem persistence with JSON index, REST CRUD API

### Frontend
- **Plan DAG** — Real-time execution graph showing agent nodes, status, duration, critic score
- **Agent Trace Panel** — Per-agent status, duration, artifacts, HITL approve/reject controls
- **Mission Mode Banner** — Animated status with agent pills
- **Artifact Browser** — Type/agent/search filters, preview modal, download, delete
- **Cost Dashboard** — Per-provider calls, success rate, avg/p95 latency, tokens, estimated cost

### Existing RAG & Chat Infrastructure
- 14-node LangGraph agentic workflow for single-agent chat
- Neo4j GraphRAG + ChromaDB vector store + BM25 hybrid retrieval
- Cross-encoder reranking (BGE, Cohere)
- RAGAS evaluation framework
- Multi-provider LLM routing (Gemini, GPT-4o, Claude, Groq, OpenRouter)
- Model Context Protocol (MCP) tool integration
- Proactive intelligence engine with background scanners
- Statistical data drift detection (PSI + KS tests)
- Rate limiting (per-IP + per-user), circuit breakers, Redis caching
- Full-text search, conversation memory, document upload pipeline

---

## 🛠️ Tech Stack

### Backend
| Layer | Technology |
|-------|-----------|
| Framework | FastAPI + Uvicorn |
| Orchestration | LangGraph 0.2+ with StateGraph |
| Agent Checkpointing | `langgraph-checkpoint-sqlite` v3.x (MemorySaver at startup, AsyncSqliteSaver per-run) |
| Vector DB | ChromaDB |
| Graph DB | Neo4j (optional, for GraphRAG) |
| BM25 | `rank_bm25` |
| Reranking | Cross-encoder (sentence-transformers) |
| Document Gen | `python-pptx`, `python-docx` |
| OCR | Tesseract (via `pytesseract`) |
| Cache | Redis |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Auth | JWT (access + refresh tokens) |
| Evaluation | RAGAS |

### Frontend
| Layer | Technology |
|-------|-----------|
| Framework | React 18 + Vite |
| State | Zustand |
| Styling | Tailwind CSS |
| Icons | Lucide React |
| Markdown | react-markdown + remark-gfm |
| Syntax highlight | Prism / highlight.js |
| Real-time | Fetch-based SSE (supports Auth headers) |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Redis (optional, degrades gracefully)

### 1. Clone & install
```bash
git clone <repo-url>
cd "AI Assistan Chatbot"

# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 2. Configure environment
```bash
cp backend/.env.example backend/.env
# Fill in API keys (see Environment Variables section)
```

### 3. Start
```bash
# Terminal 1 — Backend
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open http://localhost:5173

---

## 🔧 Environment Variables

```env
# ── Core ──────────────────────────────────────────────────────────────
DATABASE_URL=sqlite:///./data/app.db          # or postgresql://...
SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256

# ── LLM Providers (at least one required) ─────────────────────────────
GEMINI_API_KEY=your-gemini-key
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
GROQ_API_KEY=your-groq-key
OPENROUTER_API_KEY=your-openrouter-key

# ── Optional Infrastructure ────────────────────────────────────────────
REDIS_URL=redis://localhost:6379
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# ── Multi-Agent ────────────────────────────────────────────────────────
AGENT_CHECKPOINT_DB=./data/agent_checkpoints.db
ARTIFACT_DIR=./artifacts

# ── Search (for web_research agent) ───────────────────────────────────
SERPER_API_KEY=your-serper-key
TAVILY_API_KEY=your-tavily-key
BRAVE_API_KEY=your-brave-key
```

---

## 📡 API Reference

### Multi-Agent / Mission Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/mission/run` | Enqueue a mission — returns `{job_id, stream_url}` immediately |
| `GET` | `/api/v1/mission/{id}/stream` | SSE stream — reconnectable via `Last-Event-ID` |
| `GET` | `/api/v1/mission/{id}` | Poll job status |
| `GET` | `/api/v1/mission/` | List user's missions |
| `POST` | `/api/v1/mission/persist` | Save mission messages to DB |
| `GET` | `/api/v1/artifacts/` | List artifacts |
| `GET` | `/api/v1/artifacts/{id}/download` | Download artifact file |
| `DELETE`| `/api/v1/artifacts/{id}` | Delete artifact |
| `POST` | `/api/v1/artifacts/{id}/approve` | HITL approve |
| `POST` | `/api/v1/artifacts/{id}/reject` | HITL reject |

### SSE Event Types

| Event | Payload | Meaning |
|-------|---------|---------|
| `mission_started` | `{job_id, query, timestamp}` | Job picked up by worker |
| `mission_classified` | `{is_mission, agents, plan_reason}` | Planner decision |
| `agent_done` | `{agent, success, artifacts}` | Single agent completed |
| `critic_done` | `{score, passes, feedback, retry_count}` | Critic evaluated |
| `hitl_required` | `{reason, approve_url, reject_url}` | Human approval needed |
| `mission_complete` | `{response, artifacts, critic_score}` | All done |
| `mission_delegated` | `{reason}` | Simple query — use chat endpoint |
| `error` | `{error}` | Job failed |

### Observability

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/metrics/usage` | Workspace totals: conversations, messages, documents |
| `GET` | `/api/v1/metrics/providers` | Per-provider latency, tokens, cost, health |
| `GET` | `/api/v1/metrics` | Prometheus text format |
| `GET` | `/health` | Health check |

---

## 📋 Project Structure

```
AI Assistan Chatbot/
├── backend/
│   └── app/
│       ├── agents/                    ← Multi-Agent System (NEW)
│       │   ├── registry.py            ← AgentRegistry + BaseAgent ABC
│       │   ├── artifacts.py           ← ArtifactStore (filesystem + JSON index)
│       │   ├── supervisor.py          ← LangGraph Supervisor Orchestrator
│       │   ├── job_queue.py           ← Async background job queue + SSE
│       │   ├── node_helpers.py        ← LLM call helpers (lazy provider import)
│       │   ├── code_agent.py          ← Code generation + sandbox
│       │   ├── web_research_agent.py  ← Web search + content extraction
│       │   ├── rag_agent.py           ← Hybrid RAG (ChromaDB + BM25)
│       │   ├── vision_agent.py        ← Multimodal + OCR
│       │   ├── document_agent.py      ← PPTX + DOCX generation
│       │   ├── data_analysis_agent.py ← Pandas + statistical analysis
│       │   └── critic_agent.py        ← Quality scoring + hallucination detection
│       ├── api/
│       │   ├── mission.py             ← Mission job queue API + SSE (NEW)
│       │   ├── mission_persist.py     ← Save mission to DB (NEW)
│       │   ├── artifacts.py           ← Artifact CRUD + HITL (NEW)
│       │   └── metrics.py             ← Provider metrics endpoint (NEW)
│       ├── agent/                     ← Single-agent LangGraph (original)
│       ├── retrieval/                 ← ChromaDB, BM25, reranker
│       ├── services/                  ← Web search, chat, memory
│       └── providers/                 ← Multi-provider LLM routing
└── frontend/
    └── src/
        ├── components/agents/         ← Multi-Agent UI (NEW)
        │   ├── AgentTracePanel.tsx    ← Execution trace + HITL controls
        │   ├── ArtifactBrowser.tsx    ← Artifact browser with preview
        │   ├── CostDashboard.tsx      ← Provider cost & latency dashboard
        │   ├── MissionModeBanner.tsx  ← Mission status banner
        │   └── PlanDAG.tsx            ← Real-time plan DAG visualization
        ├── hooks/
        │   └── useMission.ts          ← Mission lifecycle hook (NEW)
        └── services/
            └── missionApi.ts          ← Mission API client (NEW)
```

---

## 📅 Changelog

### v3.1.0 — Workspace UI & Settings Center Overhaul (Current)
- **NEW** — **20-Tab Categorized Settings Center**: Reorganized with grouped sidebar navigation (Personal, Integrations, Coding):
  - *Personal*: General, Profile, Appearance, Personalization (custom instructions & coding preferences), Notifications (in-app & browser permission), Voice (speech recognition & TTS synthesis test), Keyboard Shortcuts, Usage & Billing, Storage (health monitors & semantic memory management), Data Controls, Semantic Memory, Account & Security.
  - *Integrations*: AI Models, Generation, AI Features, Remote MCP Servers, Connections (search APIs & OAuth), Documents & RAG.
  - *Coding*: Git integration & commit assistant configuration, Runtime Environments & `.env` configuration guide.
- **NEW** — **Interactive Mermaid Diagrams**: Inline rendering for `mermaid` diagrams with dynamic loading, dark theme styling, and fallback.
- **NEW** — **6 Unified Search Modes**: Search strategy picker (✨ Auto, 🌐 Web, 📚 Knowledge Base, ⚡ Cache, 🔬 Deep Research, 🔀 Hybrid) with API payload forwarding.
- **NEW** — **Interactive Welcome Workspace**: Quick-start prompt cards across Deep Research, Code, Document Analysis, Data, Writing, and Math, with search mode selectors.
- **NEW** — **Full-Workspace Theme & Accent Sync**: `AppLayout` dynamically synchronizes dark/light/system modes, typography scale (`font-sm`, `font-lg`), compact density, and CSS `--accent` variables across the entire viewport.
- **NEW** — **Workspace Usage Metrics API**: `GET /api/v1/metrics/usage` endpoint returning live counts of user conversations, messages, and ingested documents.
- **FIX** — Fixed `.env` Docker-to-local filesystem path configurations (`VECTOR_DB_DIR`, `UPLOAD_DIR`).

### v3.0.0 — Multi-Agent Workspace
- **NEW** — LangGraph Supervisor Orchestrator with parallel agent dispatch
- **NEW** — 7 specialized agents: code, web_research, rag, vision, document, data_analysis, critic
- **NEW** — Critic quality loop: auto-retries with feedback injection (max 2 cycles, threshold 0.65)
- **NEW** — Async job queue — `POST /mission/run` returns job_id immediately (no blocking)
- **NEW** — Reconnectable SSE stream with `Last-Event-ID` support
- **NEW** — Mission messages persisted to DB — survive page refresh
- **NEW** — Plan DAG visualization — real-time agent execution graph
- **NEW** — Cost & Latency Dashboard — per-provider metrics in Dev HUD
- **NEW** — Workspace Artifact Browser — filter, preview, download, delete
- **NEW** — Human-in-the-Loop (HITL) approve/reject flow
- **NEW** — `GET /api/v1/metrics/providers` — live provider cost/health data
- **FIX** — `langgraph-checkpoint-sqlite` v3.x compatibility (MemorySaver at startup, AsyncSqliteSaver per-run)
- **FIX** — `get_current_user` import path corrected (`app.api.auth`)

### v2.2.0 — Settings & Provider Overhaul
- Full Settings panel redesign
- Per-provider API key management
- Real-time provider health checks

### v2.1.0 — Document Pipeline
- DOCX/PDF/PPTX upload + ingestion
- Inline document context in chat
- Chunk-level citation with source panel

### v2.0.0 — LangGraph + GraphRAG
- 14-node LangGraph agentic workflow
- Neo4j GraphRAG integration
- BM25 + Dense hybrid retrieval
- Cross-encoder reranking
- RAGAS evaluation framework
- Statistical drift detection (PSI + KS)

---

## 📄 License

MIT License — see [LICENSE](LICENSE)
