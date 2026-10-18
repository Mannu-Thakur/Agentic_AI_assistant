# Production Readiness Issue Tracker

Updated: 2026-10-18

## Status rules

- **Closed (local):** the source fix is present and the relevant local regression suite passes. This is not evidence of a live staging integration.
- **Open (release gate):** release evidence still requires live credentials, deployment infrastructure, or an independent review result.

## Closed findings

### PR-01 — Fallback selection and intent routing drift

**Status:** Closed (local).

The configured provider models and fallback mappings are covered by the updated fallback tests. Deprecated Gemini and Groq IDs map forward to supported models; retired Groq models are removed from the active routing profiles and frontend pickers. Intent tool access is request-scoped, and remote MCP tools are named and routed from the runtime registry instead of being assumed to exist from a static prompt list. Document QA and vision rely on their graph paths rather than advertising tools those paths do not call.

**Evidence:** `backend/tests/test_model_fallback.py`, `backend/tests/test_intent_routing.py`, `backend/tests/test_remote_mcp_e2e.py`; included in the full backend test run.

### SEC-01 — Public database inspection and MCP connection-test exposure

**Status:** Closed in source; keep covered by deployment checks.

Database inspection now requires an active admin and an explicit disabled-by-default feature flag. MCP server management and connection testing require an authenticated user and apply outbound URL validation.

**Evidence:** `backend/app/api/database_query.py`, `backend/app/api/mcp_servers.py`, `backend/app/core/config.py`.

### SEC-02 — Host-process code execution and unavailable local stdio tools

**Status:** Closed (fail-closed behavior).

Python execution is disabled by default and requires a configured sandbox URL and shared secret. The application sends execution requests to the isolated sandbox service; local stdio MCP startup is disabled where the runtime cannot safely support it.

**Evidence:** `backend/app/tools/local_tools.py`, `backend/app/sandbox_service.py`, `backend/Dockerfile.sandbox`, `backend/tests/test_tools.py`.

### SEC-03 — Remote MCP SSRF and DNS rebinding

**Status:** Closed (local regression coverage).

Outbound MCP URLs are validated, redirects are disabled, environment proxy settings are ignored, and each TCP connection resolves and pins a public address before connecting while preserving the origin hostname for TLS verification.

**Evidence:** `backend/app/tools/network_safety.py`, `backend/app/tools/mcp_client.py`, `backend/tests/test_network_safety.py`.

### SEC-04 — Approval results could report failed tool calls as completed

**Status:** Closed (local regression coverage).

Tool execution now carries an explicit failure state through the approval endpoint. Indeterminate remote failures are recorded as failed and return an error response instead of being classified by a brittle message-prefix check.

**Evidence:** `backend/app/tools/registry.py`, `backend/app/api/tool_approvals.py`, `backend/tests/test_tool_approval_failures.py`.

### TEN-01 — User boundaries for artifacts, missions, and provider credentials

**Status:** Implemented; multi-account staging verification remains open under REL-02.

Artifact paths and metadata are scoped to owner and session, API reads and deletes check ownership, mission jobs are persisted with user/session identity, and provider keys use the encrypted key service.

**Evidence:** `backend/app/agents/artifacts.py`, `backend/app/api/artifacts.py`, `backend/app/agents/job_queue.py`, `backend/app/services/provider_key_service.py`.

### OPS-01 — Mission execution lifecycle and recovery

**Status:** Implemented and covered by the local suite.

Mission jobs are persisted, user-scoped, and expose reconnectable status/progress endpoints. Queue and storage failures are handled through the job lifecycle.

**Evidence:** `backend/app/agents/job_queue.py`, `backend/app/api/mission.py`, `backend/app/models/mission_job.py`.

## Open release gates

### REL-01 — Live provider availability and failover

**Status:** Open.

The earlier bounded provider probe recorded an OpenAI HTTP 429 and no configured alternate provider key at that time. That observation may have changed. Before release, run provider health checks with the exact staging credentials and prove at least two independent providers can generate a response and fail over.

### REL-02 — Credentialed staging end-to-end coverage

**Status:** Open.

The local suite establishes mocked/control-flow behavior. It does not demonstrate the full live flows for document upload → parse → embedding → retrieval, current web search, vision/OCR, remote MCP read and approved side effects, or sandbox execution in the deployed environment. Validate those paths with a disposable tenant and non-production credentials.

### REV-01 — Independent security scan and architecture review

**Status:** Open; manual review completed, formal result unavailable.

The independent architecture reviewer stopped at the platform usage limit, and no completed security-scan report was available to verify. The local review found and fixed the DNS-rebinding gap above, but that is not a substitute for the pending independent review.

### UX-01 — Frontend bundle size

**Status:** Follow-up.

The production build succeeds, but Vite reports `frontend/dist/assets/index-CsLku0zN.js` at about 1.37 MB minified. Consider code-splitting the largest optional diagram/editor dependencies.

## Validation snapshot

- Backend: **339 passed, 7 warnings** (full suite after the model-catalog and DNS-pinning changes; 124.22s).
- Frontend: `npm run build` passed; one large-chunk warning is tracked as UX-01 (bundle about 1.37 MB minified).
- Python syntax compilation: passed with `python -m compileall -q backend/app`.
- Whitespace validation: `git diff --check` passed. Git emitted a local fsmonitor IPC warning and line-ending notices; the command exited successfully.

## Release decision

**Not ready to claim production-ready yet.** The verified code fixes and local regression suite are in place. Close REL-01, REL-02, and REV-01 against the actual release environment before treating production readiness as established. UX-01 is a performance follow-up rather than a security blocker.
