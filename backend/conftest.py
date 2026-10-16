"""
backend/conftest.py — Root-level pytest configuration.

Excludes live-server integration scripts (realtime_* and test_production_e2e*)
from automatic collection. These scripts require a running backend server and
are meant to be executed manually with `python <script>.py`, not via pytest.

Without this, running `python -m pytest backend/` would collect them and fail
with "connection refused" because no local server is running.
"""

collect_ignore = [
    "realtime_complex_test.py",
    "realtime_list_expenses_test.py",
    "realtime_semantic_pipeline_test.py",
    "realtime_stream_test.py",
    "test_production_e2e.py",
    "test_production_e2e_asgi.py",
    "test_adversarial_remediation.py",
    "test_phase2_runtime_events.py",
    "test_zero_trust_pipeline.py",
    "verify_production_readiness.py",
    "verify_rag_crag_selfrag.py",
    "verify_semantic_rag_web_mcp.py",
    "smoke_test_prod.py",
]
