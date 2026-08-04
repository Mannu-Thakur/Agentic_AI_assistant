# Omni — Flagship Agentic AI Workspace

A full-stack, enterprise-grade, stateful agentic AI platform built with **FastAPI**, **LangGraph**, **React 18**, **TypeScript**, **ChromaDB**, **Redis**, and **Model Context Protocol (MCP)**.

---

## 🌟 Overview & Highlights

Omni is an advanced AI Assistant workspace designed for production environments. It features a stateful **LangGraph** execution graph, multi-provider LLM orchestration with live streaming, a dual-layer **OCR document ingestion pipeline**, a 4-tier **multi-engine web search waterfall**, **compound query decomposition**, **semantic memory extraction**, **MCP Workspace tool integration**, **Monaco code canvas**, and developer-focused telemetry (**DevHUD**).

---

## 🏗 System Architecture

```
AI Assistant Chatbot/
├── backend/                  # FastAPI + LangGraph Agent Backend
│   ├── app/
│   │   ├── agent/            # LangGraph graph, execution nodes, prompts, state
│   │   ├── api/              # REST & SSE endpoints (auth, chat, docs, memories, mcp, health, metrics, admin)
│   │   ├── core/             # Hardened config, database, security, Redis, metrics, telemetry
│   │   ├── embeddings/       # Embedding service (ChromaDB & sentence-transformers)
│   │   ├── memory/           # Semantic memory extraction and vector indexing
│   │   ├── middleware/        # Security headers, payload limits, XSS sanitization
│   │   ├── models/           # SQLAlchemy ORM database models
│   │   ├── providers/        # LLM provider adapters (Gemini, Groq, OpenRouter, OpenAI-compatible)
│   │   ├── retrieval/        # Vector store retriever & document chunking
│   │   ├── schemas/          # Pydantic request & response validation models
│   │   ├── services/         # Business logic (chat, document parser, web search, memory, audit)
│   │   ├── tools/            # MCP Workspace server, local tools, scheduler, tool registry
│   │   └── workers/          # Background tasks (provider health checker, memory extractor)
│   ├── alembic/              # Database schema migrations
│   └── tests/                # Comprehensive pytest suite
│
└── frontend/                 # React 18 + Vite + TypeScript Frontend
    └── src/
        ├── components/       # UI components (ChatInput, CanvasPanel, DevHUD, SourcesDrawer, Modals)
        ├── hooks/            # Custom React hooks (audio, chat, theme, toast)
        ├── layouts/          # AppLayout, AuthLayout
        ├── pages/            # ChatPage, LoginPage, OAuthCallbackPage, SettingsPage, SharedChatPage
        ├── router/           # React Router route definitions
        ├── services/         # Axios API client & SSE stream handler
        ├── store/            # Zustand state management (auth, chat, UI, settings)
        ├── types/            # TypeScript interface & type definitions
        └── utils/            # Formatting, code utilities, export helpers
```

---

## ⚡ Features & Key Capabilities

### 🧠 1. Stateful LangGraph Agentic Engine
* **State Graph Execution**: Autonomous multi-step cycle (`intent_route` → `retrieve_context` → `execute_tools` → `generate_response`).
* **Compound Query Decomposition**: Detects multi-part user queries (e.g. *"who won tennis 2026 AND how does food tracking work?"*) and decomposes them into independent sub-questions. Each sub-question is searched and answered separately, then merged into a single cohesive response — ensuring no part of a complex query gets dropped.
* **Source Attribution**: Accurate tracking and citation of web links and ingested document passages. Web search sources now carry clickable URLs and provider names to the frontend.
* **Context-Aware Prompts**: Dynamically injects long-term semantic memory, workspace documents, and systemic rules into model context.

### 🤖 2. Multi-Provider LLM Orchestration & Resilience
* **Supported Providers**: Google Gemini (2.0 / 2.5), Groq (Llama 3.1 / 3.3, Gemma 2, Mixtral), OpenRouter (Claude 3.5 Sonnet, DeepSeek R1/V3, GPT-4o), and custom OpenAI-compatible endpoints.
* **Provider Circuit Breakers**: Built-in `CircuitBreaker` instances (`CLOSED`, `OPEN`, `HALF_OPEN`) with a 30-second cooldown window for isolated error recovery. Degraded or failing providers are automatically bypassed without bringing down the entire pipeline.
* **Provider Telemetry & Health Tracking**: Tracks request counts, average latency, error rates, and failure thresholds (`app/providers/provider_metrics.py`).
* **Curated Model Picker**: Frontend exposes a hand-curated list of tested, reliable models filtered by which provider keys are currently verified — eliminating the 300+ entry OpenRouter model flood. Includes automatic snap-back to `gemini-2.5-flash` if a stale/unknown model is detected in localStorage.
* **Dynamic Provider Fallback**: Automatic fallback on rate limits or API errors via the central `ProviderRegistry`.
* **BYOK (Bring Your Own Key)**: Secure user-level API key storage and runtime validation via `x-api-keys` header.
* **Improved Provider Routing**: `gemma` and `groq` prefixed model IDs now correctly resolve to the Groq provider.

### 🌐 3. Multi-Engine Web Search Waterfall
* **4-Tier Fallback Hierarchy**:
  1. **Tavily AI Search**: AI-curated snippets optimized for LLMs.
  2. **SerpAPI**: Real-time Google Search engine results.
  3. **Exa AI**: Neural semantic search.
  4. **DuckDuckGo**: Free, keyless fallback provider.
* **Per-Engine 8s Timeouts**: Every search SDK call is wrapped in an `asyncio.wait_for` timeout so a hung provider never stalls the entire pipeline.
* **Deep Web Content Extraction**: Automated HTML scraping, domain filtering, and relevance ranking.

### 📄 4. Advanced RAG & Dual-Layer OCR Document Pipeline
* **Multi-Format Ingestion**: Native text extraction for PDF, DOCX, XLSX, CSV, PPTX, TXT, and Markdown.
* **Dual-Layer OCR Engine**: Automated fallback for scanned documents and images (PNG, JPG, WEBP, TIFF, BMP) using `pytesseract` + `pdf2image` + `OpenCV` image preprocessing (denoising, thresholding, deskewing).
* **Cross-Platform Auto-Detection**: Tesseract binary auto-detection for Windows and Linux/Docker environments.

#### 🧪 RAG Engine Benchmark Evaluation
The RAG (Retrieval-Augmented Generation) engine combines **Dense Vector Search** (`gemini-embedding-001` @ 768-dim), **BM25 Keyword Search**, **Reciprocal Rank Fusion (RRF)**, and **Self-RAG Intent Routing**.

| Test Category | Benchmark Scenario | Retrieval Accuracy | Result & Verification |
| :--- | :--- | :---: | :--- |
| **High-Level Definition** | Identity & platform purpose query | **100%** | Extracted exact platform scope, creator metadata, and architectural design intent. |
| **Exact Field Extraction** | Specific language IDs & enum mappings | **100%** | Precision extraction of numerical Language IDs (Python: 71, JS: 63, C++: 54, Java: 62). |
| **Deep Architecture** | Execution queue & sandboxing mechanics | **100%** | Detailed Redis `LPUSH/BRPOP` queues, PostgreSQL status states, and Linux `Isolate` cgroups. |
| **Schema & SQL Extraction**| Database tables, join relationships, SQL queries | **100%** | Accurate tabular output for `Companies`, `Topics`, and `ProblemCompanies` join tables + SQL JOINs. |
| **Cross-Doc Synthesis** | Multi-file summary (`Part 1` + `Part 2`) | **100%** | Seamless multi-document context fusion combining architecture, AI features, and security specs. |
| **Structured Output** | Tech stack & component mapping | **100%** | Generated component tables and valid Mermaid architecture flowcharts. |
| **Self-RAG Routing** | Out-of-domain knowledge (World Cup) | **100%** | Self-RAG routed away from vector DB to Web Search fallback with zero hallucination. |

**Overall Benchmark Score:** `7 / 7 Passed (100% Accuracy)`

### 🔌 5. Model Context Protocol (MCP) — Workspace Server
* **Protocol Support**: Native stdio and SSE transport support for connecting external MCP servers.
* **Built-in Workspace Server** (`mcp_calculator_server.py`): A fully-featured MCP server with the following tools:
  * **`calculate`** — Safe sandboxed mathematical expression evaluator (`sin`, `cos`, `sqrt`, `log`, `pi`, `e`).
  * **`add_expense`** — Log expenses with amount, description, category, and optional ISO date. Accepts natural-language category aliases (`fooding`, `bf`, `fast food`, `coupon`, `cab`, etc.) which are normalised to canonical categories automatically.
  * **`get_expenses`** — Retrieve and filter logged expenses by category and/or date.
  * **`summarize_expenses`** — Full breakdown of all expenses grouped by category with per-category subtotals and a grand total.
  * **`create_reminder`** — Schedule calendar reminders.
  * **`send_email`** — Draft and queue email messages.
* **Persistent JSON Store**: All expenses, reminders, and emails are persisted to a local `mcp_store.json` file on the server.
* **Management UI/API**: Add, edit, test, and manage MCP server connections in real time (`/api/v1/mcp-servers`).

### 💡 6. Semantic Long-Term Memory
* **Background Fact Extraction**: Automatically analyzes user messages to identify facts, preferences, and details.
* **Dual-Mode Extraction**: Attempts LLM-based extraction (Gemini) first — uses the user's personal key or falls back to the server's `GEMINI_API_KEY`. When neither is available, automatically falls back to **rule-based pattern extraction** so memories are always captured regardless of key status.
* **Vector Indexing & Deduplication**: Index stored memories in ChromaDB to prevent duplicate entries.
* **Memory Management**: View, filter, edit, or delete stored memories directly from the Settings interface.

### 💻 7. Interactive Canvas Panel & Code Workspace
* **Split-Screen Workspace**: Side-by-side view for chatting and viewing generated code/artifacts.
* **Monaco Code Editor**: Full syntax highlighting, auto-completion, and code editing capabilities.
* **Math & Markdown Rendering**: LaTeX math formatting via KaTeX (`remark-math`, `rehype-katex`) and GitHub Flavored Markdown.

### 🛡️ 8. Enterprise Hardening & Security
* **Authentication**: JWT access tokens (24h) + refresh tokens (30 days). Each refresh token now carries a unique `jti` (JWT ID) to ensure token rotation always produces a distinct, non-reusable token. Bcrypt password hashing and OAuth 2.0 (Google & GitHub).
* **Self-Service Password Reset**: Complete password recovery flow with single-use, 15-minute expiration tokens (`/api/v1/auth/forgot-password` and `/api/v1/auth/reset-password`). Integrates with SMTP (`email_service.py`) for email delivery, with dev token cache fallback for offline testing.
* **Mock OAuth Support**: Test-mode mock codes (`mock_` prefix) for both Google and GitHub OAuth flows — allows integration testing without live external OAuth.
* **Open Redirect Defense**: Strict URI whitelisting (`ALLOWED_REDIRECT_URIS`).
* **Security Middlewares**: `SecureHeadersMiddleware` (CSP, HSTS, X-Frame-Options), `PayloadLimitMiddleware` (upload size restriction), and `InputSanitizationMiddleware` (XSS sanitization).
* **Resilient Cache & Rate Limiting**: Redis-backed soft rate limiting with an in-memory fallback cache layer (`app/core/redis_client.py`) to prevent service interruption during Redis outages. W3C Trace Context propagation (`traceparent`, `X-Trace-ID`, `X-Span-ID`), structured single-line JSON logging, and Prometheus metrics endpoint (`/api/v1/metrics`).

### 📊 9. Developer Telemetry (DevHUD)
* **Execution Telemetry**: Live step breakdown showing node transitions, latency, execution state, prompt token consumption, and raw tool output payloads.

### ⏱️ 10. Streaming Reliability & Timeout Guard
* **120-Second Hard Deadline**: The SSE streaming endpoint (`/api/v1/chat/stream`) enforces a 120-second master deadline on the LangGraph task. If any node hangs silently, the task is cancelled and a user-friendly timeout error is emitted — preventing the frontend from showing *"Thinking…"* indefinitely.
* **Rolling Deadline Refresh**: Every received token resets the deadline, so long but actively-generating responses are never cut short.
* **30-Second Checkpoint**: The queue loop re-checks the deadline every 30 seconds even when idle.
* **Client Disconnect Cancellation**: When the browser tab closes mid-stream, the graph task is cancelled immediately to avoid wasting LLM tokens and compute.

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | FastAPI, Uvicorn, Python 3.10+ |
| **Agent Orchestration** | LangGraph, LangChain Core |
| **Database & ORM** | SQLAlchemy 2.0, Alembic, SQLite (Dev) / PostgreSQL (Prod) |
| **Caching & Rate Limit** | Redis 7 + In-Memory Fallback Cache |
| **Vector Database** | ChromaDB |
| **Document Parsing & OCR** | PyPDF, python-docx, openpyxl, python-pptx, PyTesseract, pdf2image, OpenCV |
| **Web Search** | Tavily SDK, SerpAPI, Exa AI, DuckDuckGo Search |
| **LLM Providers** | Google Gemini SDK, Groq SDK, OpenRouter, OpenAI API |
| **Frontend Framework** | React 18, Vite, TypeScript, Zustand |
| **Styling & UI** | Tailwind CSS, Framer Motion, Radix UI |
| **Code & Math Display** | Monaco Editor, KaTeX, React Markdown, Syntax Highlighter |
| **DevOps & Containers** | Docker, Docker Compose, Nginx |

---

## 🚀 Quick Start

### Prerequisites
* **Python**: 3.10 or higher
* **Node.js**: 18.0 or higher
* **Tesseract OCR** (Optional, for scanned PDF/image text extraction):
  * **Windows**: Download installer from [UB-Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
  * **Linux**: `sudo apt-get install tesseract-ocr`

---

### Option A: Local Development Setup

#### 1. Backend Setup
```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template and configure keys
cp ../.env.template ../.env

# Run database migrations
alembic upgrade head

# Start FastAPI development server
uvicorn app.main:app --reload --port 8000
```
Backend will be live at `http://localhost:8000`. Interactive API documentation available at `http://localhost:8000/docs`.

#### 2. Frontend Setup
```bash
# Navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```
Frontend will be live at `http://localhost:5173`.

---

### Option B: Docker Compose (Full Stack Production Setup)

Run the entire platform (PostgreSQL, Redis, FastAPI Backend, React Frontend with Nginx) with a single command:

```bash
# Copy environment template
cp .env.template .env

# Edit .env to add your API keys and SECRET_KEY
# Then launch containers:
docker compose up --build -d

# Check status and logs
docker compose ps
docker compose logs -f
```

Access points:
* **Frontend Web App**: `http://localhost:80` (or custom `FRONTEND_PORT`)
* **Backend API**: `http://localhost:8000/api/v1`
* **Swagger Docs**: `http://localhost:8000/docs`

---

## ⚙️ Environment Configuration

| Variable | Description | Default / Example |
|---|---|---|
| `SECRET_KEY` | JWT signing secret key (Required in production) | `CHANGE_ME_generate_a_strong_random_secret_key` |
| `ENVIRONMENT` | Environment flag (`development`, `staging`, `production`) | `development` |
| `DATABASE_URL` | Primary database connection URL | `sqlite:///./sql_app.db` |
| `REDIS_HOST` | Redis cache hostname | `localhost` (Local) / `redis` (Docker) |
| `REDIS_PORT` | Redis port | `6379` |
| `GEMINI_API_KEY` | Google Gemini API Key (also used as memory-extraction fallback when no user key) | `your_gemini_key` |
| `GROQ_API_KEY` | Groq API Key | `your_groq_key` |
| `OPENROUTER_API_KEY` | OpenRouter API Key | `your_openrouter_key` |
| `TAVILY_API_KEY` | Tavily Web Search Key | `your_tavily_key` |
| `SERP_API_KEY` | SerpAPI Key (Google Search) | `your_serp_key` |
| `EXA_API_KEY` | Exa AI Search Key | `your_exa_key` |
| `WEB_SEARCH_PROVIDER_ORDER` | Search engine fallback priority | `tavily,serpapi,exa,duckduckgo` |
| `SMTP_SERVER` | SMTP host for sending password reset emails | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP server port | `587` |
| `SMTP_USERNAME` | SMTP authentication username | `your_email@example.com` |
| `SMTP_PASSWORD` | SMTP authentication password / App password | `your_app_password` |
| `EMAILS_FROM_EMAIL` | From email address for system emails | `noreply@yourdomain.com` |
| `FRONTEND_URL` | Frontend URL used in password reset links | `http://localhost:5173` |
| `TESSERACT_CMD` | Explicit path to Tesseract binary | Auto-detected if blank |
| `REQUIRE_OCR` | Enforce server exit if Tesseract missing | `false` |
| `ALLOWED_REDIRECT_URIS` | Whitelisted OAuth redirect URIs | `http://localhost:5173/auth/google/callback` |

---

## 🧪 Testing & Quality Assurance

Run the automated backend test suite using `pytest`:

```bash
cd backend
python -m pytest tests
```

---

## 📡 Key API Endpoints Summary

| Group | Endpoint | Method | Description |
|---|---|---|---|
| **Auth** | `/api/v1/auth/register` | `POST` | User registration |
| | `/api/v1/auth/login` | `POST` | User login (JWT access & refresh tokens) |
| | `/api/v1/auth/refresh` | `POST` | Refresh access token |
| | `/api/v1/auth/me` | `GET` | Get current user profile |
| | `/api/v1/auth/forgot-password` | `POST` | Request password reset token via email |
| | `/api/v1/auth/reset-password` | `POST` | Reset password using valid reset token |
| **Chat** | `/api/v1/chat/stream` | `POST` | SSE real-time agent message streaming |
| | `/api/v1/chat/conversations` | `GET` | List user chat conversations |
| | `/api/v1/chat/conversations/{id}` | `DELETE` | Delete single conversation |
| | `/api/v1/chat/conversations` | `DELETE` | Clear all conversations |
| | `/api/v1/chat/share` | `POST` | Generate shareable public chat link |
| **Documents** | `/api/v1/documents/upload` | `POST` | Upload and parse document/image with OCR & RAG vector indexing |
| | `/api/v1/documents/list` | `GET` | List ingested workspace documents |
| | `/api/v1/documents/{id}` | `DELETE` | Delete document and vector embeddings |
| **Memories** | `/api/v1/memories` | `GET` | List extracted user memories |
| | `/api/v1/memories/{id}` | `PUT/DELETE` | Edit or delete semantic memory item |
| **API Keys** | `/api/v1/api-keys/validate` | `POST` | Validate custom provider API keys |
| **MCP** | `/api/v1/mcp-servers` | `GET/POST` | List and register external MCP servers |
| **Health** | `/api/v1/health` | `GET` | Main system health status |
| | `/api/v1/health/providers` | `GET` | Live status check for LLM and search providers |
| **Metrics** | `/api/v1/metrics` | `GET` | Prometheus telemetry metrics |
| | `/api/v1/metrics/cache` | `GET` | Redis and in-memory cache hit/miss statistics |

---

## 📝 License

This project is licensed under the MIT License.

