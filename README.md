# Omni — Production-Grade Agentic AI Workspace

A full-stack, production-ready AI assistant platform built with **FastAPI**, **LangGraph**, **React**, and **ChromaDB**.

## Architecture

```
├── backend/          # FastAPI + LangGraph agent backend
│   ├── app/
│   │   ├── agent/        # LangGraph state graph, nodes, prompts
│   │   ├── api/          # REST + SSE streaming endpoints
│   │   ├── core/         # Config, database, security (JWT)
│   │   ├── embeddings/   # Embedding service (mock + sentence-transformers)
│   │   ├── memory/       # Semantic memory models
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── providers/    # Gemini, Groq, OpenRouter LLM adapters
│   │   ├── retrieval/    # ChromaDB vector store
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # Chat, memory, document parsing services
│   │   └── tools/        # Tool registry, MCP client, local tools
│   ├── alembic/          # Database migrations
│   └── tests/            # pytest test suite (13 tests)
│
└── frontend/         # React + Vite + TypeScript frontend
    └── src/
        ├── components/   # Reusable UI components
        ├── layouts/      # AppLayout, AuthLayout
        ├── pages/        # ChatPage, WorkspacePage, LoginPage, SettingsPage
        ├── store/        # Zustand state (auth, chat, UI)
        ├── services/     # Axios API client
        └── types/        # TypeScript type definitions
```

## Features

- **LangGraph Agent** — Stateful graph with `retrieve_context → generate_response → execute_tools` loop
- **Multi-Provider LLM** — Gemini, Groq, OpenRouter with unified streaming interface
- **RAG Pipeline** — ChromaDB vector store, multi-format document ingestion (PDF, DOCX, XLSX, PPTX)
- **Semantic Memory** — Automatic extraction background task, deduplication, context injection
- **MCP Support** — Model Context Protocol client + example calculator server
- **Tools** — Tavily web search, Python sandbox executor
- **SSE Streaming** — Real-time token streaming via Server-Sent Events
- **Auth** — JWT access + refresh tokens, bcrypt password hashing
- **DevHUD** — Developer telemetry panel with LangGraph execution stepper and context inspector

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```
 
## Environment Variables

Copy `.env.template` to `.env` and fill in your API keys:

```env
GEMINI_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
OPENROUTER_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here
SECRET_KEY=your_jwt_secret_here
```

## Tests

```bash
cd backend
pytest
# 13/13 tests pass
```

## Docker

```bash
docker-compose up -d
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy, Alembic, SQLite/Postgres |
| Agent | LangGraph, LangChain |
| LLMs | Gemini, Groq, OpenRouter |
| Vector DB | ChromaDB |
| Embeddings | sentence-transformers |
| Frontend | React 18, Vite, TypeScript, Zustand |
| Styling | Tailwind CSS |
| Auth | JWT, bcrypt |
| DevOps | Docker Compose |
