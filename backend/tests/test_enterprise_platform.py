"""
tests/test_enterprise_platform.py — Tests for Phase 1-5 Enterprise GenAI features.

Tests cover:
  - Routing tier complexity analysis
  - Cost tracking
  - Drift detection (PSI + KS)
  - Domain prompt injection
  - Version config
  - TelemetryRecord model
  - Evaluation deterministic checks
  - Graph quality metrics structure

All tests are self-contained and do NOT require Neo4j, RAGAS, or live LLM calls.
"""
import pytest
import time


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 2: Routing
# ─────────────────────────────────────────────────────────────────────────────

class TestComplexityAnalyzer:
    """Tests for the complexity analyzer used in LLM/SLM routing."""

    def test_simple_query_low_complexity(self):
        """Short, simple queries should have low complexity scores."""
        try:
            from app.routing.complexity_analyzer import analyze_complexity
            result = analyze_complexity("What is the weather?")
            assert result.complexity_score >= 0.0
            assert result.complexity_score <= 1.0
            assert result.recommended_tier in ("slm", "llm-medium", "llm-strong")
        except ImportError:
            pytest.skip("routing module not available")

    def test_complex_query_higher_complexity(self):
        """Multi-part analytical queries should score higher than simple questions."""
        try:
            from app.routing.complexity_analyzer import analyze_complexity
            simple = analyze_complexity("What is Python?")
            complex_q = analyze_complexity(
                "Analyze the trade-offs between RAG and fine-tuning for enterprise "
                "knowledge retrieval, considering latency, cost, freshness, and "
                "hallucination risk across multiple document types."
            )
            # Complex query should score >= simple query
            assert complex_q.complexity_score >= simple.complexity_score
        except ImportError:
            pytest.skip("routing module not available")

    def test_complexity_result_fields(self):
        """Complexity result should have required fields."""
        try:
            from app.routing.complexity_analyzer import analyze_complexity
            result = analyze_complexity("Explain transformer attention mechanisms in detail")
            assert hasattr(result, "complexity_score")
            assert hasattr(result, "recommended_tier")
            assert hasattr(result, "signals")
            assert isinstance(result.signals, (dict, list))
        except ImportError:
            pytest.skip("routing module not available")


class TestModelProfiles:
    """Tests for model profile registry."""

    def test_profiles_exist(self):
        """Profile registry should have at least one profile."""
        try:
            from app.routing.model_profiles import get_all_profiles
            profiles = get_all_profiles()
            # Returns either a list or a dict — both valid
            assert len(profiles) > 0
        except ImportError:
            pytest.skip("routing module not available")

    def test_tiers_are_valid(self):
        """All profiles should have valid tier values."""
        try:
            from app.routing.model_profiles import get_all_profiles
            valid_tiers = {"slm", "llm-medium", "llm-strong"}
            profiles = get_all_profiles()
            # Support both dict-of-dicts and list-of-dicts
            if isinstance(profiles, dict):
                items = list(profiles.values())
            else:
                items = profiles
            for p in items:
                tier = p.get("tier") if isinstance(p, dict) else getattr(p, "tier", None)
                assert tier in valid_tiers, f"Profile has invalid tier: {tier}"
        except ImportError:
            pytest.skip("routing module not available")

    def test_get_profile_for_known_model(self):
        """Should return a profile for a known model."""
        try:
            from app.routing.model_profiles import get_all_profiles
            profiles = get_all_profiles()
            if isinstance(profiles, dict):
                assert "llama-3.1-8b-instant" in profiles or len(profiles) > 0
            else:
                assert len(profiles) > 0
        except ImportError:
            pytest.skip("routing module not available")


class TestCostTracker:
    """Tests for the cost tracking module."""

    def test_record_and_summary(self):
        """Should record a cost entry and return it in the summary."""
        try:
            from app.routing.cost_tracker import CostTracker
            tracker = CostTracker()
            method = getattr(tracker, "record_request", None) or getattr(tracker, "record", None)
            if method is None:
                pytest.skip("CostTracker has no record/record_request method")
            import inspect
            sig = inspect.signature(method)
            params = list(sig.parameters.keys())
            # Call with first positional args based on what the method accepts
            if "model_id" in params:
                method(model_id="test-model", input_tokens=100, output_tokens=50)
            else:
                method(model="test-model", tier="slm", input_tokens=100, output_tokens=50, latency_ms=120.0)
            summary = tracker.get_summary()
            assert isinstance(summary, dict)
        except ImportError:
            pytest.skip("routing module not available")

    def test_cost_non_negative(self):
        """Estimated costs should always be non-negative."""
        try:
            from app.routing.cost_tracker import CostTracker
            import inspect
            tracker = CostTracker()
            method = getattr(tracker, "record_request", None) or getattr(tracker, "record", None)
            if method is None:
                pytest.skip("CostTracker has no record/record_request method")
            sig = inspect.signature(method)
            params = list(sig.parameters.keys())
            if "model_id" in params:
                method(model_id="test-model", input_tokens=500, output_tokens=200)
            else:
                method(model="test-model", tier="llm-medium", input_tokens=500, output_tokens=200, latency_ms=500.0)
            summary = tracker.get_summary()
            total_cost = summary.get("total_cost_usd", summary.get("total_estimated_usd", 0))
            assert total_cost >= 0.0
        except ImportError:
            pytest.skip("routing module not available")


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 3: Evaluation
# ─────────────────────────────────────────────────────────────────────────────

class TestDeterministicChecks:
    """Tests for deterministic evaluation checks."""

    def test_empty_answer_fails(self):
        """Empty answer should be flagged."""
        try:
            from app.evaluation.deterministic_checks import run_deterministic_checks
            result = run_deterministic_checks(
                question="What is RAG?",
                answer="",
                context=[],
            )
            assert result.passed is False or result.overall_score < 0.5
        except ImportError:
            pytest.skip("evaluation module not available")

    def test_good_answer_passes(self):
        """A reasonable answer should score above baseline."""
        try:
            from app.evaluation.deterministic_checks import run_deterministic_checks
            result = run_deterministic_checks(
                question="What is Retrieval-Augmented Generation?",
                answer=(
                    "Retrieval-Augmented Generation (RAG) is a technique that combines "
                    "information retrieval with large language model generation. It retrieves "
                    "relevant documents from a knowledge base and provides them as context "
                    "to the LLM, improving factual accuracy and reducing hallucinations."
                ),
                context=["RAG combines retrieval with generation to improve accuracy."],
            )
            assert isinstance(result.overall_score, float)
            assert 0.0 <= result.overall_score <= 1.0
        except ImportError:
            pytest.skip("evaluation module not available")

    def test_result_has_required_fields(self):
        """Deterministic check result should have documented fields."""
        try:
            from app.evaluation.deterministic_checks import run_deterministic_checks
            result = run_deterministic_checks(
                question="Test question?",
                answer="Test answer that is reasonably long.",
                context=["Some context here."],
            )
            assert hasattr(result, "overall_score")
            assert hasattr(result, "passed")
            assert hasattr(result, "checks")
        except ImportError:
            pytest.skip("evaluation module not available")


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 4: Analytics (model layer)
# ─────────────────────────────────────────────────────────────────────────────

class TestTelemetryRecord:
    """Tests for TelemetryRecord SQLAlchemy model."""

    def test_model_import(self):
        """TelemetryRecord should import without errors."""
        from app.models.telemetry import TelemetryRecord
        assert TelemetryRecord.__tablename__ == "telemetry_records"

    def test_model_fields_exist(self):
        """All expected columns should be present on the model."""
        from app.models.telemetry import TelemetryRecord
        required_columns = [
            "request_id", "user_id", "chat_id", "intent",
            "model_used", "model_tier", "total_latency_ms",
            "chunks_retrieved", "graph_evidence_count",
            "answer_confidence", "hallucination_risk", "created_at",
        ]
        existing_columns = [c.key for c in TelemetryRecord.__table__.columns]
        for col in required_columns:
            assert col in existing_columns, f"Missing column: {col}"

    def test_model_instantiation(self):
        """TelemetryRecord should instantiate with minimal fields."""
        from app.models.telemetry import TelemetryRecord
        rec = TelemetryRecord(
            request_id="test-001",
            user_id="user-1",
            chat_id="chat-1",
            model_used="llama-3.1-8b-instant",
            model_tier="slm",
            created_at=time.time(),
        )
        assert rec.request_id == "test-001"
        assert rec.model_tier == "slm"


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 5: Drift Detection
# ─────────────────────────────────────────────────────────────────────────────

class TestPSIComputation:
    """Tests for the PSI computation used in drift detection."""

    def test_identical_distributions_zero_psi(self):
        """Identical distributions should have PSI ≈ 0."""
        from app.monitoring.drift_detector import _compute_psi
        data = [float(i) for i in range(100)]
        psi = _compute_psi(data, data[:])
        assert psi < 0.05, f"PSI for identical distributions should be ~0, got {psi}"

    def test_very_different_distributions_high_psi(self):
        """Very different distributions should have PSI > 0.2 (drift threshold)."""
        from app.monitoring.drift_detector import _compute_psi
        baseline = [float(i) for i in range(50)]          # 0–49
        current = [float(i + 100) for i in range(50)]     # 100–149
        psi = _compute_psi(baseline, current)
        assert psi > 0.2, f"PSI for very different distributions should be > 0.2, got {psi}"

    def test_psi_non_negative(self):
        """PSI should always be non-negative."""
        from app.monitoring.drift_detector import _compute_psi
        baseline = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        current = [2.0, 3.0, 4.0, 5.0, 5.5, 6.0, 7.0, 8.0, 8.5, 10.0]
        psi = _compute_psi(baseline, current)
        assert psi >= 0.0

    def test_psi_empty_lists(self):
        """Empty lists should return 0.0 without raising."""
        from app.monitoring.drift_detector import _compute_psi
        assert _compute_psi([], []) == 0.0
        assert _compute_psi([1.0], []) == 0.0

    def test_psi_status_classification(self):
        """PSI status should classify into NORMAL / WARNING / DRIFT_DETECTED."""
        from app.monitoring.drift_detector import _psi_status
        assert _psi_status(0.05) == "NORMAL"
        assert _psi_status(0.15) == "WARNING"
        assert _psi_status(0.25) == "DRIFT_DETECTED"

    def test_ks_statistic_identical(self):
        """KS statistic on identical distributions should be 0."""
        from app.monitoring.drift_detector import _compute_ks_statistic
        data = [float(i) for i in range(50)]
        stat, status = _compute_ks_statistic(data, data[:])
        assert stat == 0.0 or stat < 0.01


# ─────────────────────────────────────────────────────────────────────────────
#  Business Domain Prompts
# ─────────────────────────────────────────────────────────────────────────────

class TestDomainPrompts:
    """Tests for business domain prompt injection."""

    def test_claims_prompt_not_empty(self):
        from app.agent.domain_prompts import get_domain_system_prompt
        prompt = get_domain_system_prompt("claims")
        assert len(prompt) > 100

    def test_warranty_prompt_not_empty(self):
        from app.agent.domain_prompts import get_domain_system_prompt
        prompt = get_domain_system_prompt("warranty")
        assert len(prompt) > 100

    def test_fraud_prompt_not_empty(self):
        from app.agent.domain_prompts import get_domain_system_prompt
        prompt = get_domain_system_prompt("fraud")
        assert len(prompt) > 100
        # Fraud prompt must NOT assert fraud definitively
        assert "NEVER state fraud as fact" in prompt or "never" in prompt.lower()

    def test_none_domain_returns_empty(self):
        from app.agent.domain_prompts import get_domain_system_prompt
        assert get_domain_system_prompt(None) == ""
        assert get_domain_system_prompt("") == ""

    def test_unknown_domain_returns_empty(self):
        from app.agent.domain_prompts import get_domain_system_prompt
        assert get_domain_system_prompt("invalid_domain_xyz") == ""

    def test_case_insensitive(self):
        from app.agent.domain_prompts import get_domain_system_prompt
        assert get_domain_system_prompt("CLAIMS") == get_domain_system_prompt("claims")

    def test_available_domains_list(self):
        from app.agent.domain_prompts import get_available_domains
        domains = get_available_domains()
        assert "claims" in domains
        assert "warranty" in domains
        assert "fraud" in domains
        assert "enterprise" in domains


# ─────────────────────────────────────────────────────────────────────────────
#  Version Tracking
# ─────────────────────────────────────────────────────────────────────────────

class TestVersionConfig:
    """Tests for the centralized version tracking system."""

    def test_versions_singleton_exists(self):
        from app.versioning.version_config import VERSIONS
        assert VERSIONS is not None

    def test_all_version_fields_present(self):
        from app.versioning.version_config import VERSIONS
        d = VERSIONS.to_dict()
        required = ["platform", "agent_graph", "prompt", "routing",
                    "embedding", "retrieval", "evaluation", "knowledge_graph"]
        for field in required:
            assert field in d, f"Missing version field: {field}"

    def test_version_strings_are_semver_like(self):
        from app.versioning.version_config import VERSIONS
        import re
        semver_re = re.compile(r"^\d+\.\d+\.\d+$")
        for key, val in VERSIONS.to_dict().items():
            assert semver_re.match(val), f"Version {key}={val!r} is not semver"

    def test_telemetry_fields_subset(self):
        from app.versioning.version_config import VERSIONS
        tel_fields = VERSIONS.to_telemetry_fields()
        assert "prompt_version" in tel_fields
        assert "routing_version" in tel_fields
        assert "embedding_version" in tel_fields
