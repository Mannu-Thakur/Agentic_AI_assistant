# AI Workspace / openChat — Interview Knowledge Base

> **Purpose:** This is a single, AI-ready project briefing. Attach this file with an interview question to GPT, Claude, or another assistant. It is designed to provide enough grounded context for accurate answers about the project's architecture, capabilities, technology choices, trade-offs, fallbacks, security, reliability, scaling limits, and future improvements.
>
> **Evidence level:** Source-level audit of the repository on **18 October 2026**. This document describes what the code and configuration implement or intend to support. It does **not** assert that every optional dependency, provider key, external integration, or cloud service is currently live in a deployment.
>
> **Answering rule for an AI using this file:** Be precise about implementation status. Say **implemented in the repository** when code exists, **optional/configuration-dependent** when it needs credentials/infrastructure, and **recommended next step** when discussing scalability or production hardening. Do not convert planned or optional features into claims that they are currently operating in production.

---

## 1. Project identity and 30-second explanation

### Project name

- Repository folder: `AI Assistan Chatbot`
- README/product description: **Enterprise GenAI Intelligence Platform — Multi-Agent Workspace v3.0**
- Frontend branding seen in the UI: **openChat** / **Omni Agentic Workspace**

The differing names reflect the project's evolution from a chatbot into a broader AI workspace. In an interview, describe it as:

> A full-stack, authenticated, multi-agent AI workspace built with React and FastAPI. It supports persistent AI chat, web research, document-grounded RAG, image/document analysis, complex multi-agent missions, artifact generation, an AI resume studio, monitoring, provider management, and developer operations. Simple queries use an agentic workflow; complex tasks can use a supervisor that plans, dispatches specialist agents in parallel, checks quality, requests human approval for risky actions, and streams progress back to the UI.

### One-minute explanation

The product has two execution paths:

1. **Regular chat path** — the user sends a message in the chat UI. The backend classifies intent, can use semantic memory, optionally rewrites/expands a query, searches the web or uploaded documents, invokes allowed tools, grades evidence, generates a response, and can reflect or retry when needed. Messages, chats, documents, and memory are stored per user.
2. **Mission Mode path** — for multi-step requests, a LangGraph supervisor turns the request into a plan, selects specialized agents, runs safe work concurrently, collects outputs, invokes a critic, retries poor results up to a bounded limit, pauses for human approval before risky work, produces a final synthesis, and persists generated artifacts and the answer.

This is not only an LLM wrapper. It combines product workflows (chat, resume authoring, document management) with reliability and operations concerns (provider fallbacks, caching, metrics, auditing, rate limiting, health checks, traces, drift detection, and deployment artifacts).

---

## 2. Main user capabilities

### 2.1 Account and identity

Implemented account capabilities:

- Register, log in, refresh a session token, and log out.
- JWT access and refresh-token authentication.
- Password-reset request, reset-token verification, and password reset.
- Google OAuth and GitHub OAuth callbacks.
- User profile/account information.
- Server-side admin APIs for user listing and audit-log inspection.

Important security design points:

- API keys are encrypted before storage.
- JWT issuer, audience, algorithm, and token-expiry configuration are available.
- Redirect URIs for OAuth are allow-listed to reduce open-redirect risk.
- CORS is explicitly configured rather than accepting all origins.

### 2.2 Persistent conversational workspace

Users can:

- Create, load, rename, delete, and search chats.
- Persist messages so they survive a browser refresh.
- Search conversations globally and in the sidebar.
- Pin and archive chats in the client experience.
- Edit a previous prompt and resubmit it.
- Retry/regenerate an answer.
- Stop a streaming answer.
- Branch from an answer into a new chat.
- Share a conversation through a public share route and control whether the shared chat is live.
- Copy the share link or use X/Twitter, LinkedIn, and Reddit sharing links.
- Export/handle chat-related data through Settings.

Answer rendering supports:

- GitHub-Flavored Markdown.
- Markdown tables, task lists, and normal formatting.
- Mathematics through KaTeX.
- Mermaid diagrams.
- Syntax-highlighted code blocks.
- Copyable and collapsible code blocks.
- Clickable web citations and expandable local-document sources.
- Answer context actions: view sources, branch, read aloud, and share.
- Text selection actions: ask a follow-up about selected content or start writing from it.
- An answer-editing canvas/panel with copy and Markdown download controls.

### 2.3 Prompt input, multimodality, and retrieval choices

The user can submit text, documents, and images. The composer supports:

- Text prompts.
- Multiple uploaded file attachments.
- Image attachment/previews for vision-capable models.
- Browser speech-to-text dictation when supported and enabled.
- A visible model picker filtered by configured providers.
- A file-content/snippet preview for supported text attachments.
- A model-locked state if no usable model/provider has been configured.

The user can select an answer/retrieval strategy:

| Mode | Intended behavior |
|---|---|
| Auto | The backend selects the appropriate retrieval/tool path. |
| Web Search | Prefer current external information. |
| Knowledge Base | Search uploaded, user-owned documents through RAG. |
| Cache | Prefer cached/contextual material when available. |
| Deep Research | Use multi-step planning/deeper search behavior. |
| Hybrid | Combine web search with knowledge-base evidence. |

### 2.4 Workspace knowledge base and document RAG

The Workspace page is a document management and RAG dashboard. Users can:

- Upload files.
- Inspect document indexing state, size, and timestamp.
- View index/readiness status and total storage.
- Retry a failed indexing job.
- Rename/update eligible document metadata.
- Download or delete a document.
- Use indexed content as evidence in chats.

Accepted file types in the UI include:

- PDF, DOC, DOCX
- XLS, XLSX
- PPT, PPTX
- TXT, Markdown, JSON, CSV
- PNG, JPG/JPEG, BMP, GIF, TIFF, WebP, HEIC, HEIF

The standard ingestion pipeline is:

```text
Upload
  -> validate size/type and inspect archives
  -> optional ClamAV scan
  -> parse/extract text
  -> split into chunks
  -> create or reuse embeddings
  -> write chunks/vectors to ChromaDB
  -> update BM25 index
  -> optionally run asynchronous GraphRAG extraction
  -> mark document ready or failed
```

Retrieval is hybrid:

- Dense similarity search in ChromaDB.
- BM25 lexical retrieval.
- Optional reranking.
- Per-user filtering to prevent one user retrieving another user's data.
- Retrieval and embedding caches.
- A maximum assembled context of roughly 12,000 characters before passing evidence to the model.
- Optional Neo4j graph evidence for entity/relationship-aware retrieval.

### 2.5 Mission Mode / multi-agent workspace

Mission Mode is intended for requests such as research-plus-implementation, data-analysis-plus-report generation, or document creation with multiple evidence sources.

User-visible Mission Mode capabilities:

- Explicit Mission Mode activation from chat.
- Live mission status banner.
- Plan DAG visualization.
- Agent-level status, duration, and artifact visibility.
- Critic score and retry awareness.
- Downloadable generated artifacts.
- Artifact filtering/preview/deletion.
- Human approval or rejection of a pending risky action.
- Server-sent-event progress updates with reconnect support.
- Persistence of mission output back into normal chat history.

Mission lifecycle:

```text
User request
  -> Supervisor classification and plan
  -> Parallel dispatch to selected agents
  -> Result collection
  -> Critic quality and citation check
  -> Retry/re-plan if score is low and retry budget remains
  -> Human approval gate if risky work is pending
  -> Final synthesis
  -> Save response, trace, and artifacts
```

The critic passes at a configured score of `0.65` or higher. A low score can trigger at most **two** re-plan/retry cycles. If synthesis fails, the system falls back to the merged specialist output instead of failing the whole mission.

### 2.6 Specialized Mission Mode agents

| Agent | Responsibility | Typical output |
|---|---|---|
| `web_research` | Searches current web sources and extracts/summarizes material. | Cited research findings. |
| `code` | Generates code and can use guarded sandbox execution. | Code, explanations, execution results. |
| `rag` | Searches the user's uploaded documents. | Evidence-grounded document answer. |
| `data_analysis` | Analyzes data files for patterns and statistics. | Findings, data insight, charts/context where supported. |
| `document` | Generates business documents. | DOCX reports or PPTX presentations saved as artifacts. |
| `vision` | Analyzes images through a multimodal model, with OCR fallback. | Image explanation, extracted text, observations. |
| `critic` | Evaluates quality/hallucination/citation coverage. | Score, feedback, pass/retry signal. |

The supervisor runs selected specialists with `asyncio.gather`, so independent work can execute concurrently. Agent failures are recorded per task where possible; one failed specialist is not necessarily a complete mission failure.

### 2.7 AI Resume Studio

The resume feature is a separate structured workflow rather than an unstructured chat prompt.

Users can:

- Upload an existing PDF, DOCX, DOC, or TXT resume.
- Start with an empty structured resume.
- Start from/paste LaTeX.
- Parse and normalize the resume into structured fields.
- Review parsing confidence by section.
- Edit personal details, headline, summary, skills, experience, bullets, projects, education, achievements, certifications, and languages.
- Add/remove skill groups, experiences, and bullets.
- Upload/paste a job description and analyze it.
- Tailor/rewrite a resume for a job description.
- Calculate ATS compatibility.
- Review an ATS metric breakdown and recommendations.
- Compare before/after content in inline and side-by-side diff views.
- Apply one-click AI suggestions, including action-verb improvements and ATS optimization.
- Switch templates, including Classic ATS, Modern, Minimal, Executive, and Academic styles.
- See a live rendered preview.
- Restore historical snapshots after a tailoring/suggestion cycle.
- Export PDF, DOCX, Markdown, JSON, and LaTeX.
- Generate LaTeX from structured state.
- Parse LaTeX back into structured resume state.
- Compile LaTeX to PDF, preview the PDF, download `.tex`, copy LaTeX, and open it in Overleaf.

### 2.8 Analytics, quality, and observability

The Analytics page exposes operational and AI-quality information, including:

- Total HTTP requests, users, conversations, and agent inferences.
- Average latency and estimated inference cost.
- Overall quality, answer confidence, faithfulness, and context relevancy.
- Quality-gate verdict distribution.
- Model-tier/cost distribution.
- Intent-classification distribution.
- Indexed chunks, source-document count, retrieval confidence, and graph-evidence count.
- Knowledge-graph entity/relationship counts when Neo4j is enabled.
- Data-drift status and dimensions, including PSI/KS-style measurements where available.
- Health of database, vector store, cache, search providers, and other dependencies.
- Recent request telemetry: model, tier, intent, latency, estimated cost, confidence, and evidence verdict.

The chat UI also has a developer HUD for per-request execution telemetry, such as model latency and chunks used.

### 2.9 Proactive intelligence

The backend includes a proactive alert engine. It can scan for and broadcast:

- Cross-document entity conflicts/inconsistencies.
- Temporal anomalies.
- Data-drift alerts.
- Hallucination spikes.
- Cost spikes.
- Morning briefings.

The frontend includes a notification bell and alert panel. Users can read alerts, see an unread count, mark them read, and trigger a scan.

### 2.10 Settings, personalization, accessibility, and data controls

Available settings include:

- Theme: system, dark, or light.
- Contrast: system/default/high contrast.
- Accent color.
- Font size.
- Compact layout.
- UI/response-language preference.
- Custom instructions.
- Response style and preferred coding language.
- Higher-intelligence preference for complex questions.
- Generation settings: temperature, maximum output tokens, streaming.
- Feature settings: semantic memory, RAG, tool calling, web search, developer HUD.
- In-app notifications, mission-completion alerts, browser notification permission.
- Voice dictation and text-to-speech testing.
- Keyboard-shortcut reference.
- Semantic-memory create/list/delete/clear actions.
- Storage/usage/status views.
- Workspace data export and conversation deletion.
- Shared-link and archived-chat controls.
- Git status/commit-assistant settings.

**Careful interview wording:** Some Settings controls are persisted preferences or UI feature flags. Do not claim that a toggle alone proves an entire backend product workflow is fully implemented. For example, a PR-review preference toggle exists, but the source audit does not establish a complete PR-posting/review automation flow.

### 2.11 Provider, model, and MCP management

The Settings UI contains API-key management for Alibaba/DashScope, OpenAI, Google Gemini, Anthropic, DeepSeek, GLM/Zhipu, Groq, OpenRouter, Tavily, SerpAPI, and Exa.

Provider features include:

- Add, replace, delete, and mask/reveal a stored key.
- Encrypt keys at rest.
- Verify provider connectivity and list/select usable models where supported.
- Model filtering/selection in chat.
- Provider health/metrics.
- Model routing based on task complexity/cost tiers.
- Retries and circuit-breaker behavior.

The advanced-tool LLM fallback chain is implemented as:

```text
Gemini -> OpenAI -> Groq -> OpenRouter
```

Transient failures such as rate limits, 5xx errors, and timeouts can fall through to the next provider. Permanent problems such as invalid credentials or explicit quota/auth failures should stop rather than repeatedly trying unsuitable providers.

MCP support includes:

- Remote server configuration.
- HTTP JSON-RPC and Server-Sent Events transport options.
- Remote server testing.
- Enable/disable, update, and delete actions.
- HTTP/SSE/stdio MCP client capability in backend code.
- Semantic tool routing and a scheduler abstraction.

### 2.12 Tools, utilities, and developer capabilities

The tool registry includes capabilities for:

- Web search.
- Guarded Python sandbox execution.
- Translation with a direct/LLM fallback.
- Summarization in TL;DR, bullet, detailed, and executive styles.
- User-document semantic search.
- Long-text chunking and synthesis.
- List database tables.
- Describe a table schema.
- Run read-only SQL (`SELECT`, `PRAGMA`, `EXPLAIN`, `WITH` style queries only).

The local calculator-style MCP server also contains capabilities for:

- Safe arithmetic calculation.
- Expense recording/listing/summarization.
- Reminder creation/listing.
- Email dispatch.

The separate web MCP server supports web search, fetch, and extraction.

Developer/operations APIs include:

- Git repository status and conventional commit-message suggestion.
- Health, liveness, readiness, and provider-health checks.
- Prometheus-style metrics, provider metrics, and workspace usage.
- GenAI evaluation summary/recent/run endpoints.
- Knowledge-graph status, quality, stats, entities, entity lookup, retrieval, and document extraction.
- Admin user and audit-log endpoints.

---

## 3. Technology stack: what, why, and how it is used

### 3.1 Frontend

| Technology | Why it is used | How it is used in this project |
|---|---|---|
| React 18 | Component-based interactive UI. | Pages, chat components, settings, resume studio, dashboards. |
| TypeScript | Safer contracts for UI state/API data. | Frontend source is TypeScript/TSX. |
| Vite | Fast dev server and production bundling. | `npm run dev`, `npm run build`, production static bundle. |
| React Router | Route-level navigation and auth guards. | Login, chat, workspace, settings, resume, analytics, shared chat routes. |
| Zustand | Lightweight global UI/application state. | Auth, chat, UI preferences, alerts, resume state. |
| Tailwind CSS | Fast, consistent responsive styling. | Main styling system across pages/components. |
| Radix UI | Accessible UI primitives. | Dialogs, dropdowns, selects, tabs, switches, toasts, tooltips. |
| react-markdown + remark/rehype | Rich model-response rendering. | Markdown/GFM, math with KaTeX, raw/rendered content support. |
| Mermaid | Diagram rendering in assistant answers. | Mermaid blocks are rendered in chat. |
| react-syntax-highlighter | Readable generated code. | Syntax-highlighted code blocks. |
| Monaco Editor packages | Editor capability dependency. | Available in dependencies; do not claim a specific shipped Monaco screen without verifying the relevant usage. |
| Framer Motion | UI animation capability. | Installed for animated interaction/UI polish. |
| TanStack React Query | Data-fetch/cache capability dependency. | Installed; the audited screens prominently use custom API helpers and Zustand, so do not overstate it as the universal data layer. |

### 3.2 Backend

| Technology | Why it is used | How it is used in this project |
|---|---|---|
| Python 3.11 | Backend language/runtime with mature AI/document ecosystem. | Target runtime in requirements/Docker/Render configuration. |
| FastAPI | Typed, async HTTP API framework. | Authentication, chat, documents, missions, analytics, resume, health, and admin routes. |
| Uvicorn | ASGI server. | Runs FastAPI application. |
| Pydantic / pydantic-settings | Input validation and typed configuration. | API schemas and environment-based settings. |
| SQLAlchemy + Alembic | ORM and schema migrations. | Users, chats, messages, documents, keys, memory, telemetry, audits, MCP config, evaluations. |
| PostgreSQL | Production relational database. | Docker Compose production-style relational store. Required by config for staging/production. |
| SQLite + aiosqlite | Simple local/development store and checkpoint fallback. | Development database and some LangGraph checkpoint behavior. |
| Redis | Cache and rate-limiting support. | Per-IP rate limits, cache support, graceful fallback when absent. |
| LangGraph | Explicit agent/state-machine orchestration. | Regular agent workflow and Mission Mode supervisor graph. |
| LangChain family | Shared LLM/message/tool abstractions. | Supports agent and retrieval implementation. |
| ChromaDB | Vector retrieval store. | User document chunks and dense similarity search. |
| BM25 | Lexical retrieval complement. | Hybrid retrieval with Chroma dense results. |
| Neo4j | Graph database. | Optional GraphRAG entity/relationship evidence. |
| OpenAI client / provider adapters | Model-provider calls. | OpenAI plus registry/fallback pattern for configured providers. |
| Tavily, SerpAPI, Exa, DuckDuckGo | External search choices. | Configurable prioritized web-search providers. |
| python-docx / python-pptx / ReportLab | Document generation and parsing. | Resume export and Mission Mode document artifacts. |
| pypdf / openpyxl / Pillow / OpenCV | File and media processing. | Document parsing and image-related processing. |
| pytesseract / Poppler | OCR/PDF image support. | Optional Tesseract OCR fallback. |
| cryptography / passlib / python-jose | Security primitives. | Encrypted keys, password hashing, JWTs. |
| httpx / tenacity | Async HTTP and retry building blocks. | Provider/search API calls and resilient network interactions. |

### 3.3 Deployment stack

| Component | Current design |
|---|---|
| Frontend | Multi-stage Node build, then nginx static serving. |
| Backend | Python 3.11 slim Docker image, FastAPI/Uvicorn, non-root `appuser`. |
| Database | PostgreSQL 15 in Docker Compose; SQLite allowed for development only. |
| Cache | Redis 7, memory limit 256 MB, LRU eviction policy in Docker Compose. |
| Graph database | Optional Neo4j 5 Community container with APOC plugin. |
| Persistence | Named Docker volumes for relational data, Redis, vector store, uploads, Neo4j data/logs. |
| Cloud blueprint | Render YAML for cloud deployment. |
| Health | Docker health checks for PostgreSQL, Redis, backend, and frontend. |

---

## 4. Architecture and request flows

### 4.1 High-level architecture

```text
Browser
  React + TypeScript + Vite + Zustand + Tailwind
       |
       | HTTPS / REST + streamed Server-Sent Events
       v
FastAPI application
  |- Auth and user management
  |- Chat and agent workflow
  |- Mission Mode job queue + supervisor
  |- Document ingestion + retrieval
  |- Resume services
  |- Analytics / metrics / monitoring
  |- MCP / tools / provider management
       |
       +--> PostgreSQL or SQLite (transactional records)
       +--> Redis (cache/rate-limit when available)
       +--> ChromaDB + BM25 (document retrieval)
       +--> Neo4j, optional (GraphRAG)
       +--> LLM providers
       +--> Search providers
       +--> Object/filesystem artifact and upload storage
```

### 4.2 Standard chat flow

```text
1. Browser sends authenticated message to /api/v1/chats/{chat_id}/messages.
2. Backend persists or initializes chat/message context.
3. Agent graph classifies intent and complexity.
4. It may load/write semantic memory.
5. It may plan, rewrite a query, retrieve documents, search web, call tools, or use graph evidence.
6. Retrieved evidence is graded/reranked and bounded before generation.
7. The selected provider/model generates a response.
8. Evidence/citation checks and reflection/retry logic can run.
9. The answer, source information, execution trace, telemetry, and message are returned/persisted.
10. The UI progressively renders the streamed/final answer and sources.
```

The regular LangGraph workflow contains nodes for classification, memory write, planning, query rewriting, web retrieval, document retrieval, document grading, response generation, tool execution/planning, reflection, parallel-tool execution, and evidence checking. It is an agentic workflow with conditional routing rather than a single `prompt -> completion` request.

### 4.3 Document upload and indexing flow

```text
1. Authenticate user and receive multipart file.
2. Enforce configured upload-size limit (default 20 MB).
3. Validate file type and inspect supported archives for suspicious expansion.
4. Optionally scan through ClamAV.
5. Save upload metadata and source file.
6. Parse/extract text and chunk it.
7. Build/reuse embeddings and store Chroma vectors under the user/document identity.
8. Update BM25 lexical index.
9. Start optional graph extraction in the background.
10. Expose ready/processing/failed status and permit failed-index retry.
```

### 4.4 Mission Mode flow

```text
1. POST /mission/run returns a job id quickly.
2. Frontend subscribes to /mission/{id}/stream using SSE.
3. In-process job worker obtains a queued job.
4. Supervisor classifies the task as simple or multi-agent mission.
5. For a mission, it plans and dispatches agents in parallel.
6. Results and artifacts are collected.
7. Critic assesses the result.
8. If quality is below threshold and retry budget remains, re-plan with critic feedback.
9. If risky action is proposed, wait for HITL approval/rejection.
10. Synthesizer produces final answer; result can be persisted to chat.
```

### 4.5 Why SSE instead of WebSockets for Mission progress?

The implementation uses server-sent events because Mission Mode is primarily server-to-client progress delivery. SSE is simpler for one-way event streams, works naturally with HTTP infrastructure, and supports reconnection/`Last-Event-ID` style recovery. The downside is that it does not provide a bidirectional channel; approval/rejection remains ordinary authenticated POST endpoints. WebSockets would be a reasonable alternative if the product required high-frequency two-way collaboration, live cursors, or more interactive task control.

---

## 5. Data model and ownership boundaries

### Core persistent entities

The project contains models/schemas for at least:

- User
- API key
- Chat
- Message
- Document
- Semantic memory
- Telemetry
- Evaluation result
- Audit log
- MCP server configuration
- Proactive alert records

### Ownership model

The intended isolation boundary is the authenticated user. Examples:

- Chat/document/memory APIs use the current authenticated user.
- Artifact download/deletion checks artifact ownership before returning/changing a file.
- Session artifact listing filters artifacts to the current owner.
- Retrieval combines `user_id` with query filters so users should not retrieve another user's chunks.
- Cache invalidation is designed per user rather than globally flushing all retrieval results.

### Important interview point

Say that multi-tenant isolation is implemented as **application-level ownership checks and per-user data filters**. Do not claim database row-level security unless it is separately added and verified; no source evidence establishes PostgreSQL RLS policies.

---

## 6. Reliability, fallback behavior, and failure scenarios

This section is especially useful for “what happens if X fails?” interview questions.

### 6.1 LLM provider failure

**What can fail:** rate limits, timeouts, transient 5xx errors, an unavailable model, invalid API key, quota exhaustion.

**Current handling:**

- Provider registry/metrics/circuit-breaker components exist.
- The advanced-tool fallback chain tries Gemini, then OpenAI, Groq, then OpenRouter for retryable/transient failures.
- Authentication/invalid-request/quota-style errors are treated as non-retryable where distinguishable.
- If no provider/model is configured, the UI locks the composer and points the user to provider configuration.
- If synthesis fails in Mission Mode, the system falls back to merged specialist output rather than discarding all work.
- If supervisor classification fails, it defaults to a simpler execution choice rather than crashing the request path.

**Trade-off:** automatic fallback improves availability but can change response quality, latency, pricing, model behavior, or tool/vision support. Production systems should expose the actual model/provider used, which this project partly does through telemetry.

### 6.2 Web-search provider failure

**What can fail:** Tavily/SerpAPI/Exa credentials, provider outage, timeout, quota, malformed response.

**Current handling:**

- Configurable provider priority: Tavily, SerpAPI, Exa, then DuckDuckGo by default.
- Provider calls have timeouts.
- On failure, the unified search service tries the next provider.
- Successful results can be cached so repeat queries and correction/retry loops do not repeatedly spend search quota.
- If all providers fail, the failure is logged and the agent should answer with degraded/no web evidence rather than inventing sources.

**Trade-off:** fallback improves continuity, but source quality and ranking differ across providers. Answers should identify citations and not claim up-to-date research if web retrieval failed.

### 6.3 Redis failure

**What can fail:** Redis container unavailable, connection refused, timeout, key eviction.

**Current handling:**

- Redis is optional for several paths.
- The rate limiter is documented as soft/fail-open so an unavailable cache should not make the entire application unavailable.
- Cache writes/reads in search/retrieval paths are generally non-fatal.
- In Docker Compose, Redis has a 256 MB memory cap with `allkeys-lru` eviction.

**Trade-off and risk:** fail-open protects availability but weakens abuse protection during a Redis outage. For a high-risk public deployment, use an external gateway/WAF rate limiter or a durable distributed rate-limit store so the application does not fail open under attack.

### 6.4 PostgreSQL failure

**What can fail:** database not reachable, invalid credentials, pool exhaustion, migration failure, storage saturation.

**Current handling:**

- Docker Compose makes backend startup depend on a healthy PostgreSQL service.
- Alembic migrations are part of deployment/entrypoint flow.
- Production/staging configuration rejects SQLite because it is unsafe for concurrent production writes.
- Health endpoints expose system state.

**Operational response:** alert on connection/pool errors, use managed PostgreSQL with backups and point-in-time recovery, run migrations as a controlled deployment step, and tune database pools per worker count.

### 6.5 SQLite failure or concurrency issue

**Reality:** SQLite is acceptable for local development but not for multiple production workers or high write concurrency.

**Current protection:** the config explicitly terminates startup in staging/production when SQLite is configured.

**Interview answer:** SQLite was chosen for frictionless local development, tests, and some checkpoint fallbacks. PostgreSQL is the correct production replacement because it handles concurrent writers, backups, failover, and connection pooling much better.

### 6.6 ChromaDB/vector retrieval failure

**What can fail:** embedding API failure, Chroma local storage issue, corrupt collection, expensive query, cache failure, BM25 update/query failure.

**Current handling:**

- Embedding and retrieval caches reduce repeat work.
- Blocking Chroma I/O is moved to the default thread pool to avoid blocking the async event loop.
- BM25 update/query problems are logged as non-fatal where possible.
- Dense retrieval failure can still leave lexical retrieval or non-RAG response paths available.
- Document status can be marked failed and retried.
- Retrieval context is capped to approximately 12,000 characters to bound prompt size/cost.

**Trade-off:** local Chroma is simple and inexpensive but is not ideal for high-scale, multi-node deployments. A scalable alternative is a managed vector system or a horizontally scalable Postgres/vector, OpenSearch, Weaviate, Qdrant, Pinecone, or Milvus deployment, depending on constraints.

### 6.7 Neo4j/GraphRAG failure

**Current design:** Neo4j GraphRAG is optional. Vector/BM25 RAG remains the primary retrieval system.

**Handling:** Graph extraction is started in the background; failure to start or run graph extraction is logged and should not block primary document ingestion or normal RAG.

**Trade-off:** GraphRAG can answer relationship/path/entity questions that chunk retrieval may miss, but it adds operational cost, schema/extraction complexity, and another dependency. It is justified only when relationship-aware questions materially improve user outcomes.

### 6.8 OCR/vision failure

**Current design:** the vision agent prefers a multimodal model where supported and can use Tesseract OCR as a fallback. Tesseract is auto-detected/configurable. Heavy neural OCR packages are optional and excluded from the baseline cloud build because of resource cost.

**Failure behavior:** if OCR is optional and unavailable, the application can still work for text-native documents and model-supported images; scanned-content quality may degrade. If `REQUIRE_OCR` is configured, startup can fail rather than silently deliver incomplete capability.

### 6.9 File-upload and indexing failure

**Current handling:**

- Default configured upload limit: 20 MB.
- Archive checks cap decompressed ZIP content at 200 MB and compression ratio at 100:1 to reduce ZIP-bomb risk.
- Optional ClamAV scanning has a timeout; ClamAV connection/time-out errors are currently **fail-open**.
- Initial ingestion waits only a limited time (15 seconds in the upload route) before allowing indexing to continue in the background.
- Documents have processing/ready/failed states and failed indexing can be retried.
- Deletion attempts to remove relational metadata, vectors, and local file content.

**Risk to state clearly:** ClamAV fail-open favors availability over strict security. For a regulated/high-security environment, use fail-closed scanning, quarantine uploads until a positive scan result, and object-storage lifecycle controls.

### 6.10 Mission worker/job queue failure

**Current design:** Mission jobs use an in-process `asyncio.Queue` and one background worker. The source explicitly says this should be replaced by Redis Streams or Celery for production.

**Implications:**

- A process restart can lose in-memory queued jobs/events.
- Multiple web instances do not automatically share the queue.
- One worker limits mission throughput.
- HITL pending requests are in an in-memory dictionary, so they are also process-local.
- Job progress/event fan-out is not a durable distributed event log.

**Current mitigating behavior:** supervisor checkpoints attempt to use SQLite-backed saver in execution; when that fails, memory-based checkpointing/fallback remains available. SSE consumers have bounded wait/reconnect behavior.

**Production fix:** use Celery/RQ/Dramatiq/Temporal or a managed task queue, a shared durable job store, Redis/Kafka/NATS event fan-out, durable HITL state, idempotency keys, retry/dead-letter policies, and worker autoscaling.

### 6.11 Critic failure or low-quality result

**Current handling:**

- Critic failure is non-fatal; it is logged.
- Low critic score below `0.65` triggers planning feedback and re-execution up to two times.
- The retry limit prevents infinite loops and uncontrolled spend.
- Deterministic checks and optional RAGAS evaluation add a second quality layer outside the critic alone.

**Trade-off:** evaluation adds latency and cost. A bounded retry budget is a deliberate safety/cost control, but it means some imperfect results are accepted after the maximum retry count.

### 6.12 SSE connection failure

**Current handling:** Mission Mode has job-status polling fallback and reconnect-oriented SSE behavior. The server maintains events with a bounded waiting loop.

**User impact:** a browser refresh or intermittent network should not necessarily mean the user loses a completed persisted result, but live incremental visibility may be interrupted.

**Production improvement:** persist every state transition/event with monotonically increasing sequence numbers, authorize streams, use a durable pub/sub system, and let clients resume from the last acknowledged sequence.

---

## 7. Scale, performance, and “what if many users arrive?”

### 7.1 Current capacity characteristics — do not overclaim

There is no repository evidence of a completed load test proving a precise user/concurrency number. Do **not** say “it supports N users” without running representative tests.

The current source/configuration contains these relevant facts:

- Backend cloud Docker command uses **one Uvicorn worker** to avoid OOM on a 512 MB Render free-tier environment.
- Mission jobs use a single, in-process `asyncio.Queue` worker.
- Local Chroma storage, filesystem artifact storage, in-memory HITL requests, and SQLite checkpoint fallbacks are convenient but not horizontally shared by default.
- Rate limiting is set around **100 requests per minute per IP** and fails open if the cache/rate-limit backend is unavailable.
- Default upload size is **20 MB**.
- Retrieval context is capped near **12,000 characters**.
- Search provider calls use timeouts and caches.

This is suitable for local development, demos, limited internal use, and a small initial deployment. It needs architectural upgrades before claiming robust high-scale multi-tenant SaaS operation.

### 7.2 What happens if 100, 1,000, or 10,000 users arrive?

#### Around 100 active users

Likely bottlenecks are external model/search quotas, the single FastAPI worker, document ingestion CPU, and one Mission worker. Caching and provider fallback help, but the right next step is to measure latency, queue depth, error rate, cost, and provider throttling under realistic traffic.

Recommended changes:

- Move from free-tier/single-worker deployment to container replicas.
- Use managed PostgreSQL and managed Redis.
- Add connection pooling and configured resource limits.
- Centralize logs/metrics/traces.
- Move artifacts/uploads to object storage.
- Add an API gateway rate limiter and per-user quotas.

#### Around 1,000 active users

The in-process mission queue and local state become unacceptable bottlenecks/availability risks. Horizontal replicas require shared coordination.

Recommended changes:

- Replace in-process jobs with Celery/Temporal/Dramatiq/RQ plus Redis/RabbitMQ/Kafka.
- Store jobs, agent events, HITL approvals, and idempotency state durably.
- Use a shared vector database or managed vector-service deployment.
- Put uploads/artifacts in S3/GCS/Azure Blob with signed URLs.
- Scale FastAPI behind a load balancer with multiple workers/replicas.
- Implement backpressure, priority queues, tenant quotas, and per-provider concurrency limits.
- Use background worker pools specialized by workload: document ingestion, embeddings, missions, export/LaTeX compilation.

#### Around 10,000+ active users

This becomes a platform-engineering problem, not just an application-server scaling problem.

Recommended architecture:

```text
CDN / WAF / API gateway
  -> stateless frontend deployment
  -> stateless API replicas
  -> durable event/job system
  -> autoscaled specialist workers
  -> managed PostgreSQL (HA, read replicas, backups)
  -> managed Redis cluster
  -> managed/vector search cluster
  -> object storage + malware/quarantine pipeline
  -> observability stack + SLOs + incident response
```

Add:

- Multi-region or at least zonal high availability based on requirements.
- Tenant isolation and audit boundaries.
- Durable rate limiting and DDoS protection.
- Cost budgets, token quotas, and model-policy enforcement.
- Capacity testing, chaos testing, DR drills, and SLA/SLO measurement.

### 7.3 Cost control strategies already present

- Complexity-based model routing/cost tracking components.
- Multi-provider fallback rather than dependence on one expensive provider.
- Cache for embeddings, retrieval, and web search.
- Bounded RAG context.
- Bounded critic retry count.
- Optional neural ML dependencies excluded from constrained cloud image.
- Telemetry/analytics for estimated cost and model usage.

### 7.4 Additional cost controls recommended

- Per-user/token budgets and hard usage caps.
- Request deduplication/idempotency for retries.
- Semantic cache for equivalent prompts.
- Batch embeddings and ingestion jobs.
- Explicit model policy by task class and tenant plan.
- Cost-aware routing based on expected answer quality, not only request complexity.
- Artifact retention and lifecycle policies.

---

## 8. Security and privacy model

### Existing protections

- Password hashing through Passlib/bcrypt.
- JWT access/refresh authentication.
- Encrypted provider-key storage using cryptographic utilities.
- Explicit CORS configuration.
- OAuth redirect allow-listing.
- Per-IP rate limiting.
- Request IDs, trace IDs, span IDs, structured access logs.
- Health/readiness/liveness routes.
- Read-only SQL endpoint restrictions.
- User ownership checks on artifacts and user-filtered retrieval.
- Upload size limits, type checks, ZIP-bomb checks, optional ClamAV scan.
- Non-root Docker containers.
- Production rejection of SQLite configuration.
- Restricted JWT algorithm allow-list.

### Security gaps / honest limitations to discuss

- ClamAV errors currently fail open; security-focused deployment should quarantine/fail closed.
- The in-memory mission queue/HITL store is not durable or distributed.
- Application-level user filters are not the same as database RLS or formal tenant isolation.
- Secret rotation, KMS/HSM usage, centralized secrets manager, data-retention schedule, formal DLP, and production WAF/CDN configuration are not established by the inspected source.
- Users can configure broad external capabilities; production requires a strong tool-policy layer, allowlists, permission scopes, and audit review.
- Python sandbox safety needs defense in depth: isolated containers/VMs, strict CPU/memory/network/filesystem limits, no host credentials, and short execution timeouts.

### How to answer “How do you protect user data?”

Use this balanced answer:

> The application authenticates users with JWTs, isolates most data access through user ownership checks and per-user retrieval filters, encrypts stored API keys, limits risky database queries to read-only operations, and includes file validation plus optional malware scanning. In a production hardening phase, I would strengthen this with managed secrets, database row-level security or equivalent tenancy controls, object-store encryption and retention policies, fail-closed scanning, a durable audit trail, gateway-level rate limiting, and isolated tool execution.

---

## 9. Key design decisions, trade-offs, and alternatives

### Why FastAPI?

**Choice:** FastAPI with async endpoints.

**Why:** AI apps spend time waiting on LLMs, search providers, databases, streams, and file I/O. Async APIs make it natural to support many waiting requests without tying a thread to each network call. FastAPI also gives schema validation and OpenAPI-friendly APIs.

**Trade-off:** async does not magically make CPU-heavy parsing, OCR, local embeddings, or document conversion cheap. Blocking workloads must be moved to workers/thread pools/processes. This project already offloads blocking Chroma I/O to a thread executor, but high-volume ingestion still needs worker separation.

**Alternative:** Django is attractive for a larger traditional admin/ORM product, while Go/Node can be viable for high-throughput APIs. Python remains a strong choice here because the AI, document, and orchestration ecosystem is central.

### Why React + TypeScript + Vite?

**Choice:** React for component composition; TypeScript for safer UI/API work; Vite for quick development/builds.

**Why:** The product has many highly interactive panels—chat streaming, task DAGs, source drawers, modals, settings, charts, resume editing. React's component ecosystem fits this well.

**Trade-off:** Client state can become fragmented between local React state, Zustand, server persistence, and streams. Good API contracts and a clear state ownership model matter.

**Alternative:** Next.js could add server rendering/SEO benefits, but this authenticated workspace is primarily application-like rather than content/SEO-first.

### Why LangGraph instead of a single prompt call?

**Choice:** explicit state graphs with conditional routing and checkpoints.

**Why:** This product needs a traceable sequence that can choose tools/retrieval, assess quality, retry, delegate work, and persist execution state. A graph makes transitions explicit and testable.

**Trade-off:** more nodes increase complexity, latency, observability needs, and failure modes. A simple question should not pay the full multi-agent cost, so the supervisor can delegate simple requests to a simpler path.

**Alternative:** a direct function-calling loop is simpler for smaller applications; a workflow engine such as Temporal is stronger for durable long-running production tasks.

### Why hybrid RAG (dense + BM25)?

**Choice:** combine semantic vector similarity and lexical BM25 ranking.

**Why:** dense retrieval understands paraphrases/meaning, while BM25 is strong for exact identifiers, acronyms, code-like terms, and rare keywords. Combining them improves recall across different query types.

**Trade-off:** more storage/indexing/query complexity and tuning requirements. Need evaluation to choose weights, top-k, and reranking policy.

**Alternative:** vector-only is simpler but can miss exact terms; keyword-only misses semantic paraphrases. A managed hybrid search engine can simplify operations at larger scale.

### Why optional Neo4j GraphRAG?

**Choice:** add graph enrichment only when configured.

**Why:** a graph helps answer questions about relationships, paths, connected entities, and cross-document consistency that chunk retrieval may miss.

**Trade-off:** another database, extraction pipeline, data-quality issue, and operational cost. Keeping it optional ensures basic RAG remains usable.

### Why multiple model and search providers?

**Choice:** provider registry and fallback chains.

**Why:** avoids single-vendor outage/quota dependence, supports cost/performance trade-offs, and lets users bring their own keys.

**Trade-off:** provider behavior, model capabilities, safety, cost, and SDK semantics differ. A routing layer needs consistent normalized errors, capability metadata, model policy, observability, and tests.

### Why a critic/retry loop?

**Choice:** critic scores mission outputs, and low scores may trigger re-planning.

**Why:** multi-step work can fail silently when research is weak, citations are insufficient, or the synthesis misses requirements. Critique provides a quality-control feedback loop.

**Trade-off:** it increases latency and token usage and can produce evaluator/model bias. The bounded two-retry limit controls runaway cost and loops.

### Why human-in-the-loop gating?

**Choice:** risky actions can pause for explicit approval.

**Why:** code execution, file write, and external calls should not be silently performed by an autonomous agent.

**Trade-off:** it adds latency and needs durable state at scale. Current in-memory HITL state is appropriate for prototype/single-instance use but should be moved to shared durable storage in production.

---

## 10. Production-readiness assessment

### Strong implementation signals

- Authentication, password reset, OAuth routes, and provider-key encryption exist.
- Docker Compose includes PostgreSQL, Redis, optional Neo4j, health checks, volumes, and non-root containers.
- Production settings reject SQLite.
- RAG includes hybrid retrieval, caches, per-user filtering, reranking hooks, and bounded context.
- Web search has fallback providers and timeouts.
- Document uploads include several defenses and retry/status handling.
- Metrics, telemetry, request IDs, trace context, provider metrics, analytics, drift detection, evaluation code, and proactive alerting are present.
- The test suite includes categories for auth, agent behavior, analytics, document pipeline, enterprise platform, RAG, resume builder, web-search modes, MCP, and production E2E scenarios.
- Benchmark harness/datasets exist for agentic, RAG, CRAG, self-RAG, MCP tool, LLM QA, and web-search behavior.

### Important limitations before calling it enterprise-scale production

- Mission queue and HITL state are process-local/in-memory.
- Base cloud configuration runs one Uvicorn worker for a constrained environment.
- Local Chroma/filesystem artifacts are not a multi-replica distributed storage design.
- Redis rate limiting can fail open.
- ClamAV scan failures can fail open.
- Capacity numbers and SLOs have not been established by the audited code alone.
- Optional services/keys determine whether advanced capabilities actually work.
- AI quality metrics and critic scores are useful signals, not absolute guarantees of truth.

### Best concise assessment

> The repository is production-minded and significantly beyond a demo: it has authentication, persistence, migrations, health checks, deployment manifests, validation, logs, telemetry, fallback paths, tests, and quality workflows. However, its Mission Mode execution model and some storage/security fallbacks are still single-instance oriented. It is strong for local deployment, demos, internal use, and an early hosted product; high-availability multi-tenant scale needs a distributed queue, shared state/storage, stricter security posture, load testing, and operational SLOs.

---

## 11. Interview-ready answers

### Q: What problem does this project solve?

**Answer:**

It solves the fragmentation between chat assistants, document search, research tools, resume builders, data analysis, and developer workflows. Instead of making users move information between separate tools, it gives them one authenticated workspace where an AI can use chat history, uploaded knowledge, live web research, structured agents, generated artifacts, and quality/observability signals.

### Q: What makes it different from a normal chatbot?

**Answer:**

It has persistent user data, hybrid RAG over uploads, configurable web research, multimodal input, tool invocation, Mission Mode with parallel specialists, critic/retry logic, HITL gating, artifact management, a resume-authoring product, analytics, and provider/operations controls. A regular question can take a lightweight path; a complex task can become an observable multi-agent workflow.

### Q: Explain the architecture in simple terms.

**Answer:**

The React frontend is the interactive workspace. It calls a FastAPI backend for authentication, chat, documents, resume functions, monitoring, and configuration. The backend stores transactional data in PostgreSQL/SQLite, keeps documents in a ChromaDB/BM25 retrieval layer, optionally uses Neo4j for graph evidence, calls LLM/search providers, and streams Mission Mode progress over SSE. Redis improves caching and rate limiting when available.

### Q: Why use a multi-agent design?

**Answer:**

Because one model prompt is not optimal for every kind of work. Web research, code execution, data analysis, document generation, image understanding, and document retrieval need different tools, constraints, and prompts. A supervisor decomposes complex work, dispatches specialized agents in parallel, merges their results, then gives a critic a chance to detect weak work before final synthesis.

### Q: How do you avoid hallucinations?

**Answer:**

No system fully eliminates hallucinations, so this project reduces it through evidence retrieval, citations, source display, document grading/reranking, graph evidence where configured, critic scoring, deterministic evaluation checks, RAGAS-oriented evaluation code, and bounded retry/replan loops. The correct claim is risk reduction and observability, not perfect factual guarantees.

### Q: How do you ensure user-document isolation?

**Answer:**

The application authenticates requests, stores document ownership, filters artifacts by the current user, and combines `user_id` with retrieval filters so a user should search only their own chunks. For a stricter enterprise posture, I would add database RLS/tenant policies, security tests for cross-tenant retrieval, and formal authorization scopes.

### Q: How would you scale Mission Mode?

**Answer:**

The current `asyncio.Queue` worker is intentional for simplicity but is not horizontally scalable. I would replace it with a durable distributed queue/workflow engine, persist job state and HITL approvals, publish events through a shared bus, run autoscaled workers per specialization, make handlers idempotent, store artifacts in object storage, and use a managed database/vector layer. This allows multiple API replicas to serve the same job system safely.

### Q: What happens if a model provider is unavailable?

**Answer:**

The app can use provider registry/circuit-breaker behavior and advanced-tool fallbacks across Gemini, OpenAI, Groq, and OpenRouter for transient errors. Permanent auth/quota failures should not be blindly retried. The UI also shows telemetry/model information, and the system should return a transparent degraded response rather than pretend it had a successful model call.

### Q: Why use both ChromaDB and BM25?

**Answer:**

Dense vectors retrieve semantic paraphrases while BM25 retrieves exact technical terms, IDs, and rare words. Combining them improves recall for mixed enterprise documents. Reranking and evidence grading aim to improve precision after retrieval.

### Q: What are the biggest risks or limitations?

**Answer:**

The most important current limits are the single-process Mission queue and HITL state, local Chroma/filesystem storage for a multi-replica world, fail-open behavior around Redis/ClamAV availability, external-provider dependency, and the absence of demonstrated production-scale load/SLO evidence. These are known next-stage platform improvements, not hidden weaknesses.

### Q: What would you improve first with more time?

**Answer:**

First, make long-running work durable and distributed: queue, event stream, HITL, artifacts, and checkpoints. Second, move to shared managed storage/services and add SLO-driven observability. Third, harden security with fail-closed upload scanning, secrets management, stronger tenancy controls, sandbox isolation, and policy enforcement. Fourth, add performance/load/chaos tests and a cost policy layer.

### Q: How do you control cost and latency?

**Answer:**

The design uses model routing, caching, hybrid retrieval with bounded context, provider fallback, timeouts, selected rather than always-on agents, a retry cap, telemetry, and estimated-cost tracking. A mature deployment would add tenant budgets, prompt/result caching, batch embeddings, model policies, and workload queues.

### Q: What was the hardest engineering challenge?

**Answer template:**

> The difficult part is not sending one prompt to an LLM; it is coordinating unreliable external systems while keeping user experience understandable. The design has to decide when to use web/document evidence, handle provider/search failures, prevent long tasks from blocking HTTP, expose progress, preserve results, keep data user-scoped, and stop risky actions for human review. Mission Mode, hybrid retrieval, SSE progress, quality checks, and fallback layers address different parts of that systems problem.

### Q: How would you test this product?

**Answer:**

Test at several levels: unit tests for parsers, routing, sanitization, and security constraints; integration tests for auth, document ingestion, RAG, provider fallbacks, MCP, resume flow, mission lifecycle, and storage; end-to-end browser tests for user journeys; benchmark datasets for answer/retrieval quality; and load/chaos tests for concurrency, queue failure, provider outage, Redis outage, database failover, and large-file ingestion. Evaluate not only correctness but citation coverage, latency, cost, data isolation, and recovery behavior.

---

## 12. API surface summary

All main APIs are under `/api/v1` unless noted otherwise.

| Group | Representative endpoints/capability |
|---|---|
| Auth | register, login, refresh, logout, current user, Google/GitHub OAuth, forgot/reset password. |
| Chats | create/list/load/update/delete chats, delete message, post message, shared chat, share settings. |
| Documents | list, upload, delete, download, retry indexing, update allowed status/metadata. |
| Memories | list/create/delete semantic memories. |
| API keys/providers | list/create/delete encrypted keys; list/refresh providers. |
| Preferences | get/update stored preferences. |
| Mission | start job, stream events, poll status, list missions, persist completed mission to chat. |
| Artifacts/HITL | list/get/download/delete artifacts; list/approve/reject human-approval requests. |
| Resume | analyze resume/JD, tailor, ATS, diff, suggestions, export/render, LaTeX preview/parse/compile. |
| Analytics | overview, quality, routing, retrieval, graph, telemetry. |
| Monitoring | drift, health, performance. |
| Proactive | alert stream/list/unread count/mark read/scan. |
| Evaluation | summary, recent results, invoke evaluation. |
| Graph | graph status/quality/stats/entities/entity/retrieve/extract document. |
| Tools | translate, summarize, database list/describe/read-only query. |
| Git | repository status and commit-message suggestion. |
| MCP | list/test/create/update/delete remote MCP server configuration. |
| Metrics/health | Prometheus-style metrics, provider metrics, usage, health, liveness, readiness. |
| Admin | users and audit logs. |

---

## 13. Repository map for follow-up technical questions

```text
AI Assistan Chatbot/
├── frontend/
│   ├── src/pages/                 # Chat, Workspace, Settings, Resume, Analytics, auth screens
│   ├── src/components/chat/       # Composer, sources, sharing, answer canvas, context menu
│   ├── src/components/agents/     # Mission banner, DAG, trace, artifacts, cost dashboard
│   ├── src/components/resume/     # Upload/edit/ATS/diff/templates/versions/export/LaTeX
│   ├── src/store/                 # Zustand stores
│   └── src/services/              # API, Mission, provider-key, resume API clients
├── backend/
│   ├── app/api/                   # FastAPI route modules
│   ├── app/agent/                 # Standard agent graph and nodes
│   ├── app/agents/                # Mission Mode supervisor, specialists, queue, artifact store
│   ├── app/retrieval/             # Chroma, BM25, reranking
│   ├── app/graph/                 # Optional Neo4j GraphRAG
│   ├── app/providers/             # Provider registry/adapters/circuit breaker/metrics
│   ├── app/tools/                 # Advanced, local, MCP, semantic-router tools
│   ├── app/resume/                # Structured AI resume services and routes
│   ├── app/proactive/             # Alert scanners, storage, broadcaster
│   ├── app/evaluation/            # RAGAS/deterministic/evaluation store
│   ├── app/monitoring/            # Drift detector
│   ├── app/models/                # SQLAlchemy persistence models
│   └── tests/                     # Test coverage by feature category
├── docker-compose.yml             # Full local multi-service environment
├── Dockerfile                     # Root/container setup
├── render.yaml                    # Render cloud blueprint
└── README.md                      # Architecture and product overview
```

---

## 14. AI assistant prompt to use with this file

When attaching this document to an AI chatbot, use a prompt like this:

```text
Use the attached project knowledge base as the source of truth. Answer my interview question about this project clearly and confidently, but do not overclaim. Separate: (1) what is implemented in the repository, (2) what is optional or configuration-dependent, and (3) what would be a recommended future production improvement. Explain technical choices, trade-offs, failure behavior, and scale implications when relevant. My question is: [PASTE QUESTION]
```

For behavioral/project-explanation interviews, add:

```text
Make the answer sound like I personally designed and built the project. Use first person where appropriate, include a concise opening and technical depth, and state limitations honestly as deliberate next-stage improvements rather than pretending they are solved.
```

---

## 15. Final truthfulness checklist for answers generated from this document

Before answering an interview question, an AI should verify:

- Is the claim backed by code/configuration, or is it merely a recommendation?
- Does the capability require an API key, Redis, Neo4j, Tesseract, an MCP server, or another optional service?
- Is the behavior production-ready, or only suitable for a single instance/development environment?
- If describing scale, has a measured throughput number actually been provided? If not, discuss architecture and testing plan rather than inventing capacity.
- If describing safety, has a fail-open path been acknowledged where applicable?
- If describing AI quality, is the response framed as mitigation and measurement rather than a guarantee?
- If describing a UI toggle, is there verified backend execution behind it?
- If describing privacy/isolation, avoid claiming row-level security, compliance certification, or encryption beyond what source evidence supports.

This disciplined framing is what makes the project explanation credible in a technical interview.
