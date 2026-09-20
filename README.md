# Enterprise GenAI Intelligence Platform v2.0

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3+-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://reactjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5+-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic_Workflow-FF6F00?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)
[![Neo4j](https://img.shields.io/badge/Neo4j-GraphRAG-008CC1?style=for-the-badge&logo=neo4j&logoColor=white)](https://neo4j.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Store-FC521F?style=for-the-badge)](https://www.trychroma.com)
[![Redis](https://img.shields.io/badge/Redis-Cache_%26_Rate_Limiting-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![Docker](https://img.shields.io/badge/Docker-Full_Stack_Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com)
[![Pytest](https://img.shields.io/badge/Pytest-286_Passing-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](https://docs.pytest.org)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

> A production-grade, enterprise-scale Agentic AI platform featuring **14-node LangGraph autonomous workflows**, **Neo4j Knowledge Graph RAG (GraphRAG)**, **BM25 + Dense Hybrid Retrieval with Cross-Encoder Reranking**, **Complexity-Based LLM/SLM Routing & Cost Tracking**, **Statistical Data Drift Detection (PSI & KS tests)**, **RAGAS & Deterministic Quality Evaluations**, **Domain Intelligence Overlays**, and **Zero-Trust Security**.

---

## 📑 Table of Contents

- [What Is This Platform?](#-what-is-this-platform)
- [System Architecture](#-system-architecture)
- [Key Capabilities & Innovations](#-key-capabilities--innovations)
  - [1. 14-Node LangGraph Agentic Workflow](#1-14-node-langgraph-agentic-workflow)
  - [2. Hybrid Retrieval Engine & Neo4j GraphRAG](#2-hybrid-retrieval-engine--neo4j-graphrag)
  - [3. Intelligent LLM/SLM Routing & Cost Accounting](#3-intelligent-llmslm-routing--cost-accounting)
  - [4. Statistical Data Drift Monitoring (PSI + KS)](#4-statistical-data-drift-monitoring-psi--ks)
  - [5. GenAI Evaluation & Quality Gates (RAGAS)](#5-genai-evaluation--quality-gates-ragas)
  - [6. Business Domain Intelligence Overlays](#6-business-domain-intelligence-overlays)
  - [7. Model Context Protocol (MCP) & Extensible Tools](#7-model-context-protocol-mcp--extensible-tools)
  - [8. Zero-Trust Security & Production Hardening](#8-zero-trust-security--production-hardening)
- [Enterprise Analytics Dashboard](#-enterprise-analytics-dashboard)
- [Screenshots & UI Showcase](#-screenshots--ui-showcase)
- [Tech Stack](#-tech-stack)
- [Repository Structure](#-repository-structure)
- [Quick Start Guide](#-quick-start-guide)
  - [Prerequisites](#prerequisites)
  - [Option A: Full Stack with Docker Compose](#option-a-full-stack-with-docker-compose-recommended)
  - [Option B: Local Development Setup](#option-b-local-development-setup)
- [Environment Configuration](#-environment-configuration)
- [REST API Reference](#-rest-api-reference)
- [Testing & Quality Assurance](#-testing--quality-assurance)
- [Production Deployment](#-production-deployment)
- [Component Version Tracking](#-component-version-tracking)
- [Contributing & Code Standards](#-contributing--code-standards)
- [License](#-license)

---

## 💡 What Is This Platform?

Standard RAG chatbots struggle in production: they suffer from vector search blind spots, lack relationship understanding, query expensive frontier models for trivial tasks, hallucinate without guardrails, and fail silently when data distributions shift.

The **Enterprise GenAI Intelligence Platform v2.0** solves this by uniting:
1. **Multi-Agent Orchestration**: Adaptive LangGraph state machine with Self-RAG retry loops, CRAG corrective evaluation, and structured self-reflection.
2. **GraphRAG + Hybrid RAG**: Bridges unstructured document chunks (ChromaDB + BM25 + Cross-Encoder) with structured entity-relationship graphs (Neo4j).
3. **Dynamic Routing**: Transparent complexity scoring routes queries across Small Language Models (SLM) and Large Language Models (LLM) to minimize cost and latency.
4. **Real-Time Statistical Telemetry**: Population Stability Index (PSI) and Kolmogorov-Smirnov (KS) tests run continuously on live traffic to detect model and data drift.
5. **No Synthetic Metrics**: Every metric, graph count, evaluation score, and drift warning reflects real database records and live execution traces.

---

## 🏗 System Architecture

### High-Level Architecture Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Client Browser / Frontend                             │
│       React 18 + TypeScript + Vite + Tailwind CSS + Lucide Icons + KaTeX        │
└───────────────────────────────────────┬─────────────────────────────────────────┘
                                        │ HTTPS / SSE (EventSource) / REST
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     FastAPI Gateway & Security Middleware                       │
│  • Request ID & W3C Trace Context (traceparent) Propagation                     │
│  • Redis Token-Bucket Rate Limiting (100 req/min, fail-open resilience)         │
│  • Zero-Trust Input Sanitizer, Magic-Byte MIME Inspector, Anti-Path Traversal   │
│  • Strict CORS, HSTS, CSP, and X-Content-Type Security Headers                  │
└───────────────────────────────────────┬─────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│               14-Node LangGraph Agentic Orchestration Engine                    │
│                                                                                 │
│   [Classify Intent] ──► [Clarification / Memory Write]                          │
│          │                                                                      │
│          ▼                                                                      │
│   [Plan & Tool Router] ──► [Parallel Tool Execution (Sandbox / Web / MCP)]      │
│          │                                                                      │
│          ▼                                                                      │
│   [Retrieval Decision] ──► [Hybrid Retrieval: ChromaDB + Neo4j GraphRAG + BM25] │
│          │                                                                      │
│          ▼                                                                      │
│   [CRAG Document Grader] ──► [Self-RAG Fallback / Retry Loop]                   │
│          │                                                                      │
│          ▼                                                                      │
│   [Complexity Scorer & Model Router] ──► [LLM / SLM Provider with Circuit Breaker]
│          │                                                                      │
│          ▼                                                                      │
│   [Evidence Checker / Hallucination Verification]                               │
│          │                                                                      │
│          ▼                                                                      │
│   [Structured Reflection & Self-Correction] ──► [Output SSE Stream]             │
└───────────────────────────────────────┬─────────────────────────────────────────┘
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             ▼                          ▼                          ▼
┌─────────────────────────┐┌─────────────────────────┐┌─────────────────────────┐
│   Data & Knowledge Base ││    LLM Providers Hub    ││ Observability & Drift   │
│ • ChromaDB (Dense)      ││ • Groq (Llama 8B/70B)   ││ • TelemetryRecord DB    │
│ • BM25 Lexical Index    ││ • Google Gemini         ││ • PSI & KS Drift Engine │
│ • Neo4j (Entity Graph)  ││ • OpenAI (GPT-4o)       ││ • RAGAS Evaluator       │
│ • Cross-Encoder Reranker││ • OpenRouter Multi-LLM  ││ • Prometheus & Cache    │
└─────────────────────────┘└─────────────────────────┘└─────────────────────────┘
```

---

## 🚀 Key Capabilities & Innovations

### 1. 14-Node LangGraph Agentic Workflow

The core reasoning engine is built on LangGraph with state isolation, typed transitions, and fine-grained cycle limits:

```mermaid
graph TD
    START([User Query]) --> CI[classify_intent_node]
    CI -->|Ambiguous Query| CL[clarification_node] --> END_NODE([END])
    CI -->|Direct Fact| MW[memory_write_node] --> END_NODE
    CI -->|General / Complex / Tools| PL[plan_node]
    PL --> TP[tool_planner_node]
    TP --> PE[parallel_tool_execution_node]
    PE --> CR[check_retrieval_node]
    CR -->|needs_retrieval=True| RC[retrieve_context_node<br/>ChromaDB + Neo4j + BM25]
    CR -->|needs_retrieval=False| GD[grade_documents_node]
    RC --> GD
    GD -->|Confidence < 0.5 & retries left| RC
    GD -->|Validated Chunks| GR[generate_response_node<br/>Router + Provider LLM]
    GR -->|Has Tool Calls| ET[execute_tools_node]
    GR -->|No Tool Calls| EC[evidence_checker_node<br/>Hallucination Check]
    ET --> RF[reflect_node]
    EC --> RF
    RF -->|Needs Improvement & Iter < 1| GR
    RF -->|Pass| END_NODE
```

- **classify_intent_node**: Determines intent, whitelisted tools, and private document boundaries without LLM invocation when regex rules match.
- **tool_planner_node & parallel_tool_execution_node**: Asynchronously schedules and executes multiple tools in parallel (e.g., executing Python scripts while fetching web data).
- **grade_documents_node (CRAG)**: Evaluates whether retrieved chunks actually answer the query. Prevents private-document leakage by barring external search fallbacks on private queries.
- **evidence_checker_node**: Validates that generated statements are directly supported by retrieved evidence to prevent hallucinations.
- **reflect_node**: Assesses answer completeness and structure; triggers self-correction if quality criteria are not satisfied.

---

### 2. Hybrid Retrieval Engine & Neo4j GraphRAG

The retrieval pipeline combines dense vector embeddings, sparse lexical search, cross-encoder reranking, and knowledge graph traversals:

```
                                  User Query
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
   ┌──────────────────────────┐              ┌──────────────────────────┐
   │  ChromaDB Dense Search   │              │   BM25 Lexical Search    │
   │ (all-MiniLM-L6-v2 Embed) │              │  (Tokenized Sparse Index)│
   └─────────────┬────────────┘              └─────────────┬────────────┘
                 │                                         │
                 └────────────────────┬────────────────────┘
                                      ▼
                        ┌──────────────────────────┐
                        │ Reciprocal Rank Fusion   │
                        │        (RRF Rank)        │
                        └─────────────┬────────────┘
                                      ▼
                        ┌──────────────────────────┐
                        │  Cross-Encoder Reranker  │
                        │ (ms-marco-MiniLM-L-6-v2) │
                        └─────────────┬────────────┘
                                      ▼
                        ┌──────────────────────────┐
                        │ Neo4j Knowledge Graph    │
                        │ 2-Hop Relationship Paths │
                        │  & Entity Neighborhoods  │
                        └─────────────┬────────────┘
                                      ▼
                        Authoritative Context Chunks
```

- **Neo4j GraphRAG**: Automatically extracts typed entities (`Person`, `Organization`, `Policy`, `Claim`, `Product`, `Supplier`, etc.) and directional relationships (`OWNS`, `CLAIMED_ON`, `SUPPLIED_BY`, `RESULTED_IN`) during ingestion with full chunk provenance.
- **2-Hop Neighborhood Search**: Discovers multi-hop relationships invisible to flat vector search (e.g., identifying when two different claims reference the same supplier or claimant address).
- **RRF & Local Reranking**: Replaces expensive LLM reranking calls with a fast, CPU-friendly local Cross-Encoder model.

---

### 3. Intelligent LLM/SLM Routing & Cost Accounting

Queries are dynamically classified and routed to the most cost-effective model tier:

| Tier | Candidate Models | Use Cases | Cost Profile |
|---|---|---|---|
| **`slm`** | `llama-3.1-8b-instant`, `gemini-2.5-flash-lite` | Direct lookups, basic summarization, simple Q&A | Minimal (< \$0.0001 / query) |
| **`llm-medium`** | `llama-3.3-70b-versatile`, `gemini-2.5-flash` | Multi-step reasoning, document synthesis, coding | Balanced |
| **`llm-strong`** | `gpt-4o`, `gemini-1.5-pro` | Deep analytical investigation, complex fraud, ambiguous data | High capability |

- **Deterministic Complexity Scorer**: Analyzes token length, multi-part questions, analytical keywords (`investigate`, `anomaly`, `compare and contrast`), and code generation needs.
- **User Override Respected**: If the user selects a specific model in the chat UI, the router respects their choice while continuing to log cost and complexity telemetry.
- **Cost Accounting**: Tracks input/output tokens and calculates estimated USD cost per query, aggregate expenditure by tier, and average cost per turn.

---

### 4. Statistical Data Drift Monitoring (PSI + KS)

The platform features built-in statistical observability that runs on genuine database telemetry:

- **Population Stability Index (PSI)**:
  $$\text{PSI} = \sum \left( \% \text{Current} - \% \text{Baseline} \right) \times \ln\left(\frac{\% \text{Current}}{\% \text{Baseline}}\right)$$
  - $\text{PSI} < 0.1$: Distribution Stable (Normal)
  - $0.1 \le \text{PSI} < 0.2$: Moderate Shift (Warning)
  - $\text{PSI} \ge 0.2$: Significant Drift Detected
- **Kolmogorov-Smirnov (KS) Two-Sample Test**:
  - Compares the empirical cumulative distributions of response latency and confidence scores to flag statistically significant shifts ($p < 0.05$).
- **Monitored Dimensions**: Query complexity, answer confidence, retrieval chunk volumes, and response latency.

---

### 5. GenAI Evaluation & Quality Gates (RAGAS)

Quality evaluation operates on a two-tier model:

1. **Deterministic Quality Gates (Zero-Cost, < 1ms)**:
   - *Response Length*: Flags truncated or empty responses.
   - *Citation Coverage*: Measures what ratio of retrieved chunks are referenced in the output.
   - *Hedging & Calibration*: Analyzes uncertainty markers vs. unwarranted overconfidence.
   - *Topic Overlap*: Validates keyword alignment between question and response.
   - *Structural Completeness*: Verifies that responses terminate with complete sentences.
2. **RAGAS LLM-Judge Evaluation**:
   - Evaluates **Faithfulness**, **Answer Relevancy**, and **Context Recall** via opt-in asynchronous assessment.

---

### 6. Business Domain Intelligence Overlays

Set `DOMAIN_MODE` in `.env` to inject domain-specific instructions and entity tracking rules:

- **`claims`**: Insurance claims investigation, anomaly detection, policy coverage verification, temporal discrepancy flagging.
- **`warranty`**: Product failure patterns, serial number analysis, supplier quality metrics, batch-level recall risk.
- **`fraud`**: Financial transaction anomalies, velocity spikes, collusion detection, identity mismatches (flags for human review without defamatory assertions).
- **`enterprise`**: General corporate knowledge extraction, cross-document synthesis, and evidence-grounded summarization.

---

### 7. Model Context Protocol (MCP) & Extensible Tools

- **Remote MCP Support**: Integrates with external tools via Model Context Protocol over SSE and HTTP.
- **Sandboxed Python Code Execution**: Runs mathematical analysis, data processing, and algorithms in a time-bounded sub-process sandbox.
- **Resilient Web Search**: Cascading web search engine with multi-tier fallback: Tavily $\to$ SerpAPI $\to$ Exa $\to$ DuckDuckGo (zero configuration required).

---

### 8. Zero-Trust Security & Production Hardening

- **JWT Authentication**: Validates both `iss` (issuer) and `aud` (audience) claims with SHA-256 token blacklisting for immediate logout invalidation.
- **Encrypted API Key Vault**: User-supplied provider keys are encrypted at rest using AES-256 GCM.
- **Redis Token-Bucket Rate Limiter**: Enforces 100 req/min per IP with graceful fail-open behavior if Redis is temporarily unreachable.
- **File Upload Protection**: Enforces MIME magic-byte verification, disallows executable/ELF/shebang files, mitigates ZIP bombs, and scans for known signatures.
- **Prompt Injection Defense**: Scans ingested files and user inputs for adversarial jailbreak sequences.
- **W3C Distributed Tracing**: Attaches `traceparent` headers (`trace_id`, `span_id`) across all request logs and SSE streams.

---

## 📊 Enterprise Analytics Dashboard

Navigate to `/analytics` in the web application to view real-time system metrics:

- **System Overview**: Total HTTP requests, success/error rates, avg/p95 latency, total estimated USD expenditure.
- **Quality & Accuracy**: RAGAS faithfulness and answer relevancy, hallucination rate, and pass/fail gate metrics.
- **Intelligent Routing Distribution**: SLM vs. LLM-Medium vs. LLM-Strong request volume and cost breakdown.
- **Retrieval Performance**: Retrieval engagement rate, average chunks utilized, and Neo4j graph evidence usage.
- **Statistical Drift Telemetry**: Live PSI and KS values across query complexity, answer confidence, and latency.
- **System Health Status**: Neo4j connection state, ChromaDB collection count, and Redis status.

---

## 🖼 Screenshots & UI Showcase

<div align="center">

<img width="1919" height="1077" alt="Dashboard Overview" src="https://github.com/user-attachments/assets/c3789c67-3ec3-4172-9206-bd29e7480979" />
<br/><br/>
<img width="1919" height="1070" alt="Agent Chat Interface" src="https://github.com/user-attachments/assets/a8152484-0b2d-4255-b545-3035cdf17e32" />
<br/><br/>
<img width="1919" height="1070" alt="Knowledge Base & Document AI" src="https://github.com/user-attachments/assets/d47bb8d1-7a31-40c1-a270-8af46f66ad60" />
<br/><br/>
<img width="1919" height="1072" alt="Execution Trace & Dev HUD" src="https://github.com/user-attachments/assets/fe9ae77c-3d65-4103-8c4c-9491c5adde8f" />
<br/><br/>
<img width="1918" height="1072" alt="Model Routing & Tiers" src="https://github.com/user-attachments/assets/e2bcc44d-5603-4744-8b02-69a0c8469014" />
<br/><br/>
<img width="1919" height="1079" alt="Document Upload & Extraction" src="https://github.com/user-attachments/assets/54ab2a3c-c570-4c8f-b2b0-2902c5e01016" />
<br/><br/>
<img width="1919" height="1070" alt="Tool Integration & MCP" src="https://github.com/user-attachments/assets/bbeff630-7591-49dc-814a-0eac530fac56" />
<br/><br/>
<img width="1917" height="1072" alt="Realtime Streaming & LaTeX Support" src="https://github.com/user-attachments/assets/9d9e4453-d997-4ea3-9b35-6dcf3439a244" />
<br/><br/>
<img width="1919" height="1065" alt="Interactive Markdown & Code Rendering" src="https://github.com/user-attachments/assets/46a07944-2d14-47ef-932b-c56901222272" />
<br/><br/>
<img width="1919" height="1067" alt="Memory & Personalization Hub" src="https://github.com/user-attachments/assets/1b615035-7eb1-485b-b335-4d06f0f093b8" />
<br/><br/>
<img width="1919" height="1064" alt="Settings & API Key Vault" src="https://github.com/user-attachments/assets/d4a0881a-95b2-4e12-9fba-cfe3aa336bb8" />
<br/><br/>
<img width="1919" height="1070" alt="Dark / Light Modern Theme" src="https://github.com/user-attachments/assets/2ca8bb05-2857-4d4c-91f6-b0b943dee8a3" />
<br/><br/>
<img width="1905" height="1074" alt="Authentication & Security" src="https://github.com/user-attachments/assets/25220bab-a12e-49b4-bbe6-d515141c1bb4" />
<br/><br/>
<img width="1919" height="1057" alt="Responsive Mobile / Tablet Layout" src="https://github.com/user-attachments/assets/d46a966b-f188-43ef-957e-4f7dd90b7920" />
<br/><br/>
<img width="1919" height="1046" alt="Resume AI Studio" src="https://github.com/user-attachments/assets/4366463a-8fb3-45a2-b3d1-31e9ebb0866b" />

</div>

---

## 🛠 Tech Stack

| Layer | Technologies |
|---|---|
| **Backend API** | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0 (Async), Alembic, Uvicorn |
| **Agent & Workflow** | LangGraph, LangChain Core, StateGraph, Custom Tool Planner & Evidence Verifier |
| **Knowledge Graph** | Neo4j Community 5.x, Cypher Query Language, Neo4j Async Python Driver |
| **Vector & Search** | ChromaDB, BM25 (`rank_bm25`), Sentence-Transformers (`all-MiniLM-L6-v2`, `ms-marco-MiniLM-L-6-v2`) |
| **LLM Providers** | Groq (`llama-3.1-8b`, `llama-3.3-70b`), Google Gemini (`gemini-2.5-flash`), OpenAI (`gpt-4o`), OpenRouter |
| **Monitoring & Eval** | Custom PSI & KS Drift Engines, RAGAS, Prometheus Client, W3C Trace Context |
| **Database & Caching** | PostgreSQL 16 (or SQLite in local dev), Redis 7 (Alpine), SQLAlchemy WAL Mode |
| **Frontend Web App** | React 18, TypeScript, Vite, Tailwind CSS, Lucide React, Zustand, KaTeX Math |
| **Container & CI** | Docker, Docker Compose, Pytest, Pytest-Asyncio, Nginx Reverse Proxy |

---

## 📂 Repository Structure

```
.
├── .env.template                     # Template with all configuration keys
├── docker-compose.yml                # Full-stack composition (Backend, Frontend, Postgres, Redis, Neo4j)
├── render.yaml                       # Production cloud deployment blueprint
├── README.md                         # Complete platform documentation
│
├── backend/                          # FastAPI Application & AI Core
│   ├── Dockerfile                    # Secure, non-root multi-stage Dockerfile
│   ├── entrypoint.sh                 # Database migration & server entrypoint
│   ├── requirements.txt              # Production Python dependencies
│   ├── pytest.ini                    # Pytest configuration
│   │
│   ├── alembic/                      # Database schema migration scripts
│   │   ├── env.py                    # Alembic environment runner
│   │   └── versions/                 # Version migration definitions
│   │
│   ├── app/                          # Core application package
│   │   ├── main.py                   # FastAPI initialization, middleware & routes
│   │   │
│   │   ├── agent/                    # LangGraph Reasoning Engine
│   │   │   ├── graph.py              # 14-node StateGraph machine definition
│   │   │   ├── nodes.py              # Node logic (Intent, Planner, CRAG, Generator, Reflector)
│   │   │   ├── state.py              # Typed AgentState schema
│   │   │   ├── prompts.py            # Prompts, tools whitelist & sanitizers
│   │   │   └── domain_prompts.py     # Domain overlays (Claims, Warranty, Fraud)
│   │   │
│   │   ├── api/                      # REST API Endpoints
│   │   │   ├── auth.py               # Authentication & JWT tokens
│   │   │   ├── chat.py               # SSE chat streaming & conversation management
│   │   │   ├── documents.py          # Document upload, chunking & indexing
│   │   │   ├── analytics.py          # Real-time metrics & dashboard endpoints
│   │   │   ├── monitoring.py         # Statistical drift (PSI/KS) & health
│   │   │   ├── graph.py              # Neo4j GraphRAG inspection endpoints
│   │   │   ├── evaluation.py         # Response quality evaluation endpoints
│   │   │   ├── health.py             # Liveness & readiness probes
│   │   │   └── api_keys.py           # Provider API key management & validation
│   │   │
│   │   ├── core/                     # Infrastructure & Core Services
│   │   │   ├── config.py             # Pydantic Settings & environment loader
│   │   │   ├── database.py           # Async engine, session management & schema migrations
│   │   │   ├── security.py           # JWT encryption, bcrypt & API key vault
│   │   │   └── redis_client.py       # Redis connection & rate limiting
│   │   │
│   │   ├── graph/                    # Knowledge Graph Pipeline
│   │   │   ├── neo4j_client.py       # Async Neo4j driver connection wrapper
│   │   │   ├── entity_extractor.py   # LLM structured entity & relationship extraction
│   │   │   ├── extraction_pipeline.py# Async chunk ingestion pipeline
│   │   │   ├── graph_retriever.py    # 2-hop neighborhood & relationship path search
│   │   │   ├── graph_store.py        # Neo4j Cypher upsert queries
│   │   │   └── graph_quality.py      # Graph health & provenance metrics
│   │   │
│   │   ├── routing/                  # Intelligent Model Routing & Cost
│   │   │   ├── complexity_analyzer.py# Deterministic query complexity scorer
│   │   │   ├── model_router.py       # Tier selection engine (SLM / Medium / Strong)
│   │   │   ├── model_profiles.py     # Model pricing & capabilities registry
│   │   │   └── cost_tracker.py       # Token-level USD cost accounting
│   │   │
│   │   ├── monitoring/               # Observability & Drift
│   │   │   └── drift_detector.py     # Population Stability Index & KS tests
│   │   │
│   │   ├── evaluation/               # GenAI Evaluation Framework
│   │   │   ├── evaluator.py          # Unified evaluation orchestration
│   │   │   ├── deterministic_checks.py# Zero-cost rule-based quality gates
│   │   │   ├── ragas_evaluator.py    # RAGAS LLM-judge integration & fallback
│   │   │   └── eval_store.py         # Evaluation persistence & aggregation
│   │   │
│   │   ├── retrieval/                # Multi-Modal Retrieval
│   │   │   ├── vector_store.py       # ChromaDB vector store wrapper
│   │   │   ├── bm25_index.py         # BM25 sparse lexical index
│   │   │   └── reranker.py           # Cross-encoder reranking model
│   │   │
│   │   ├── models/                   # SQLAlchemy Database Models
│   │   │   ├── user.py               # User accounts & preferences
│   │   │   ├── chat.py               # Conversations & messages
│   │   │   ├── document.py           # Ingested documents & metadata
│   │   │   ├── telemetry.py          # 20+ dimension request telemetry table
│   │   │   └── evaluation.py         # Persisted evaluation records
│   │   │
│   │   └── tools/                    # Tool Implementations
│   │       ├── local_tools.py        # Python sandbox & Tavily/DDG search
│   │       ├── mcp_client.py         # Custom Stdio & SSE MCP client
│   │       └── registry.py           # Dynamic tool discovery & dispatch
│   │
│   └── tests/                        # Pytest Test Suite (286+ Passing Tests)
│       ├── test_enterprise_platform.py # Tests for Routing, Drift, Graph, Eval
│       ├── test_agent.py             # Agent flow & LangGraph execution tests
│       ├── test_rag.py               # Vector search & chunking tests
│       ├── test_security.py          # JWT, RBAC & sanitization tests
│       └── ...                       # Additional unit & integration tests
│
└── frontend/                         # React 18 + Vite Web Application
    ├── nginx.conf                    # Production Nginx reverse proxy configuration
    ├── package.json                  # Frontend dependencies & scripts
    ├── vite.config.ts                # Vite bundler configuration
    └── src/
        ├── pages/                    # Page Views
        │   ├── ChatPage.tsx          # Agent chat interface & streaming UI
        │   ├── AnalyticsPage.tsx     # Enterprise Observability HUD
        │   ├── WorkspacePage.tsx     # Document management & upload
        │   └── SettingsPage.tsx      # Provider keys, preferences & settings
        ├── store/                    # Zustand State Stores
        │   ├── chatStore.ts          # Active conversations & streaming state
        │   └── authStore.ts          # Authentication session state
        └── services/                 # API Client & SSE Handlers
            └── api.ts                # Axios client with interceptors
```

---

## ⚡ Quick Start Guide

### Prerequisites

- **Python**: Version 3.11 or higher
- **Node.js**: Version 18 or higher (with npm)
- **Docker & Docker Compose**: (Optional, for containerized deployment)
- **API Key**: At least one LLM key (Groq is free at [console.groq.com](https://console.groq.com))

---

### Option A: Full Stack with Docker Compose (Recommended)

Starts all services including PostgreSQL, Redis, Neo4j, Backend, and Frontend:

```bash
# 1. Clone the repository
git clone https://github.com/Mannu-Thakur/Agentic_AI_assistant.git
cd Agentic_AI_assistant

# 2. Copy and configure the environment variables
cp .env.template .env
# Edit .env and supply your GROQ_API_KEY and NEO4J_PASSWORD

# 3. Launch the complete stack
docker compose up --build -d

# 4. Check status
docker compose ps
```

**Access Endpoints:**
- 🌐 **Frontend Web App**: [http://localhost:5173](http://localhost:5173) (or `http://localhost:80`)
- ⚙️ **Backend API**: [http://localhost:8000](http://localhost:8000)
- 📖 **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- 🕸️ **Neo4j Browser**: [http://localhost:7474](http://localhost:7474)

---

### Option B: Local Development Setup

#### 1. Backend Setup

```bash
cd backend

# Create and activate Python virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create local environment file
cp ../.env.template .env
# Set GROQ_API_KEY in .env

# Run database migrations and start development server
python -m uvicorn app.main:app --reload --port 8000
```

#### 2. Frontend Setup

In a new terminal:

```bash
cd frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## ⚙️ Environment Configuration

Create a `.env` file in the root directory (based on `.env.template`):

| Variable | Description | Default / Example |
|---|---|---|
| `SECRET_KEY` | JWT signing secret key | `CHANGE_ME_IN_PRODUCTION` |
| `DATABASE_URL` | SQLite or PostgreSQL connection string | `sqlite:///./sql_app.db` |
| `GROQ_API_KEY` | Groq API Key (Free high-speed inference) | `gsk_...` |
| `GEMINI_API_KEY` | Google Gemini API Key | `AIza...` |
| `OPENAI_API_KEY` | OpenAI API Key (GPT-4o) | `sk-...` |
| `OPENROUTER_API_KEY`| OpenRouter API Key | `sk-or-...` |
| `NEO4J_URI` | Neo4j Bolt protocol URI (enables GraphRAG) | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | `your_secure_password` |
| `GRAPHRAG_ENABLED` | Toggle GraphRAG entity retrieval | `true` |
| `DOMAIN_MODE` | Business domain overlay (`claims`, `warranty`, `fraud`, `enterprise`) | `claims` |
| `REDIS_HOST` | Redis cache hostname | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `TAVILY_API_KEY` | Tavily Web Search Key (falls back to DuckDuckGo if blank)| `tvly-...` |
| `FRONTEND_URL` | Frontend URL for CORS and password reset links | `http://localhost:5173` |

---

## 📡 REST API Reference

### Analytics & Observability
- `GET /api/v1/analytics/overview` — System-wide metrics (HTTP counts, latency p95, agent requests, total cost).
- `GET /api/v1/analytics/quality` — Aggregated RAGAS faithfulness, relevancy, and deterministic quality scores.
- `GET /api/v1/analytics/routing` — Model tier distribution (`slm`, `llm-medium`, `llm-strong`) and cost breakdown.
- `GET /api/v1/analytics/retrieval` — RAG retrieval engagement, chunk volume, and graph evidence usage.
- `GET /api/v1/analytics/graph` — Knowledge graph health metrics and entity distribution.
- `GET /api/v1/analytics/telemetry` — Paginated recent request telemetry entries (20+ fields).

### Monitoring & Drift Detection
- `GET /api/v1/monitoring/drift` — Live Population Stability Index (PSI) and Kolmogorov-Smirnov (KS) drift report.
- `GET /api/v1/monitoring/health` — Multi-component health check (Neo4j, ChromaDB, Redis, VectorStore).
- `GET /api/v1/monitoring/performance` — Historical model latency and confidence trends.
- `GET /api/v1/health/liveness` — Kubernetes liveness probe.
- `GET /api/v1/health/readiness` — Kubernetes readiness probe.
- `GET /api/v1/metrics` — Prometheus metrics exposition endpoint.

### Knowledge Graph (GraphRAG)
- `GET /api/v1/graph/status` — Neo4j connection status and configuration.
- `GET /api/v1/graph/stats` — Node and relationship counts in the active database.
- `GET /api/v1/graph/quality` — Orphan count, missing provenance, low-confidence entity statistics.
- `GET /api/v1/graph/entities` — Search graph entities by keyword or type.
- `POST /api/v1/graph/extract/{doc_id}` — Trigger asynchronous entity extraction for an ingested document.

### GenAI Evaluation
- `GET /api/v1/evaluation/summary` — Aggregate quality gate statistics (pass rate, hallucination rate).
- `GET /api/v1/evaluation/recent` — Recent evaluation records with detailed breakdowns.
- `POST /api/v1/evaluation/evaluate` — Run on-demand evaluation (deterministic checks + optional RAGAS).

### Chat & Streaming
- `POST /api/v1/chat/stream` — Real-time Server-Sent Events (SSE) agent message stream.
- `GET /api/v1/chat/conversations` — List user chat conversations.
- `DELETE /api/v1/chat/conversations/{id}` — Delete a specific conversation.
- `DELETE /api/v1/chat/conversations` — Clear all user conversations.
- `POST /api/v1/chat/share` — Create a shareable public link for a conversation.

### Documents & Knowledge Base
- `POST /api/v1/documents/upload` — Upload document (PDF, DOCX, CSV, TXT, images with OCR) and index embeddings.
- `GET /api/v1/documents/list` — List ingested workspace documents with parsing status.
- `DELETE /api/v1/documents/{id}` — Delete document and remove associated vector and graph embeddings.

### Authentication & Keys
- `POST /api/v1/auth/register` — Register a new user account.
- `POST /api/v1/auth/login` — Authenticate and receive JWT access & refresh tokens.
- `POST /api/v1/auth/refresh` — Refresh expired access token.
- `GET /api/v1/auth/me` — Retrieve current authenticated user profile.
- `POST /api/v1/api-keys/validate` — Validate custom provider credentials before saving.

---

## 🧪 Testing & Quality Assurance

The codebase includes an extensive automated test suite covering routing logic, drift computation, agent graphs, security headers, document parsing, and database models.

```bash
cd backend

# Run the complete test suite
pytest tests/ -v

# Run enterprise platform tests specifically (Routing, Drift, Graph, Eval)
pytest tests/test_enterprise_platform.py -v

# Run with test coverage report
pytest --cov=app --cov-report=term-missing
```

### Test Suite Status

```
============================== test session starts ==============================
collected 289 items

tests/test_enterprise_platform.py ...............................         [ 10%]
tests/test_agent.py ....................................                  [ 23%]
tests/test_rag.py ....................                                    [ 30%]
tests/test_security.py .........................                          [ 38%]
tests/test_system_hardening.py ...................................        [ 50%]
tests/test_tools.py .................                                     [ 56%]
tests/test_web_search_workflow.py ...........                             [ 60%]
...
====================== 286 passed, 3 skipped in 103s =======================
```

---

## 🚢 Production Deployment

### Docker Deployment with Alembic Migrations

The production Docker container automatically runs database migrations on startup using `backend/entrypoint.sh` before starting the Uvicorn application server:

```bash
docker compose -f docker-compose.yml up -d --build
```

### Cloud Deployment (Render / Cloud Run / Kubernetes)

A production blueprint is provided in `render.yaml`:
- **Backend Service**: Python 3.11 with 512MB RAM optimization, non-root execution (`appuser`), and health probes configured to `/api/v1/health/readiness`.
- **Frontend Service**: Static SPA site with Vite production build.
- **Managed Databases**: Connected to Render PostgreSQL and Redis instances.

---

## 📌 Component Version Tracking

All configurable components carry explicit semantic versions embedded into request telemetry records for auditability:

| Component | Current Version | Description |
|---|---|---|
| **Platform** | `2.0.0` | Global platform release |
| **Agent Graph** | `3.0.0` | 14-node LangGraph state machine |
| **Prompt Templates** | `3.1.0` | System prompts and domain overlays |
| **Routing Logic** | `1.0.0` | Complexity analyzer and tier routing |
| **Retrieval Engine**| `3.0.0` | Hybrid BM25 + dense + cross-encoder reranker |
| **Evaluation** | `1.0.0` | Deterministic checks and RAGAS integration |
| **Knowledge Graph** | `1.0.0` | Neo4j GraphRAG extraction & 2-hop retrieval |
| **Drift Detection** | `1.0.0` | PSI & KS statistical drift monitors |

---

## 🤝 Contributing & Code Standards

Contributions are welcome! Please follow these guidelines:
- **Architecture**: Keep agent nodes pure, modular, and typed using `AgentState`.
- **Comments & Documentation**: Every module must include top-level architectural docstrings, type annotations, and inline rationale for non-obvious logic.
- **Fail-Open Resilience**: External dependencies (Neo4j, Redis, RAGAS, external search engines) must degrade gracefully without crashing the core agent loop.
- **Tests**: Include unit tests under `backend/tests/` for any new features or bug fixes.

---

## 📄 License

This project is open-source software licensed under the [MIT License](LICENSE).
