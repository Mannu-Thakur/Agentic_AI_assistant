#!/usr/bin/env python3
"""
benchmarks/run_benchmarks.py — CLI entry point for the Omni AI benchmark framework.

Usage:
    python -m benchmarks.run_benchmarks --capability all --concurrency 4
    python -m benchmarks.run_benchmarks --capability rag --n 10 --smoke
    python -m benchmarks.run_benchmarks --capability mcp --report --model gemini-2.5-flash

Capabilities: all | llm | mcp | rag | self_rag | crag | web | agentic
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Ensure backend/ is on sys.path when run from anywhere ────────────────────
_HERE = Path(__file__).resolve().parent          # benchmarks/
_BACKEND = _HERE.parent                          # backend/
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from benchmarks.config import load_config, CAPABILITY_META
from benchmarks.harness import (
    BenchmarkRunner,
    SuiteResult,
    load_dataset,
    save_results,
    OmniClient,
)

# ── Try to import rich for pretty output (optional) ──────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import print as rprint
    _RICH = True
    console = Console()
except ImportError:
    _RICH = False
    console = None  # type: ignore[assignment]


# ─────────────────────────────────────────────────────────────────────────────
#  Scorer imports
# ─────────────────────────────────────────────────────────────────────────────

def _load_scorer(capability: str):
    """Dynamically import the scorer function for a capability."""
    from benchmarks.scorers import SCORER_REGISTRY
    scorer = SCORER_REGISTRY.get(capability)
    if scorer is None:
        raise ValueError(
            f"Unknown capability '{capability}'. "
            f"Available: {list(SCORER_REGISTRY.keys())}"
        )
    return scorer


# ─────────────────────────────────────────────────────────────────────────────
#  Printing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _status_emoji(score: float) -> str:
    if score >= 0.85:
        return "🟢"
    elif score >= 0.70:
        return "🟡"
    elif score >= 0.60:
        return "🟠"
    else:
        return "🔴"


def _print_banner() -> None:
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║          OMNI AI  —  PRODUCTION BENCHMARK FRAMEWORK             ║
║   Evaluating: LLM QA · MCP · RAG · Self-RAG · CRAG ·           ║
║               Web Search · Agentic Reasoning                     ║
╚══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def _print_suite_summary(suite: SuiteResult, cap_meta: dict) -> None:
    print(f"\n  ── {cap_meta['name']} Results ──────────────────────────────")
    print(f"  Cases:      {suite.total_cases}  (errors: {suite.error_count})")
    print(f"  Mean Score: {suite.mean_score:.3f}  ± {suite.std_score:.3f}")
    print(f"  Min/Max:    {suite.min_score:.3f} / {suite.max_score:.3f}")
    print(f"  Pass Rate:  {suite.pass_rate*100:.1f}%  (threshold ≥0.60)")
    print(f"  Latency:    P50={suite.p50_latency_ms}ms  P95={suite.p95_latency_ms}ms  P99={suite.p99_latency_ms}ms")


def _print_final_summary(all_suites: dict[str, SuiteResult]) -> None:
    print("\n" + "=" * 68)
    print("  FINAL BENCHMARK SUMMARY")
    print("=" * 68)
    header = f"  {'Capability':<22} {'Score':>7} {'Pass%':>7} {'P50ms':>7} {'Status'}"
    print(header)
    print("  " + "-" * 64)

    overall_scores = []
    for cap, suite in all_suites.items():
        meta   = CAPABILITY_META.get(cap, {})
        name   = meta.get("name", cap)
        emoji  = _status_emoji(suite.mean_score)
        print(
            f"  {name:<22} {suite.mean_score:>7.3f} "
            f"{suite.pass_rate*100:>6.1f}% {suite.p50_latency_ms:>6}ms  {emoji}"
        )
        overall_scores.append(suite.mean_score)

    if overall_scores:
        import statistics
        overall = statistics.mean(overall_scores)
        print("  " + "-" * 64)
        print(f"  {'OVERALL MEAN':<22} {overall:>7.3f}  {_status_emoji(overall)}")
    print("=" * 68 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
#  Core run logic
# ─────────────────────────────────────────────────────────────────────────────

async def run_capability(
    capability: str,
    config,
    n: int = 0,
    concurrency: int = 4,
    model: str = "gemini-2.0-flash",
    output_dir: Path = None,
) -> SuiteResult:
    """Run benchmark for one capability. Returns SuiteResult."""
    meta   = CAPABILITY_META.get(capability, {})
    ds_name = meta.get("dataset", f"{capability}.jsonl")
    dataset_path = config.datasets_dir / ds_name

    print(f"\n{'─'*68}")
    print(f"  Running: {meta.get('name', capability)}")
    print(f"  Dataset: {dataset_path.name}")
    print(f"  Source:  {', '.join(meta.get('source_benchmarks', ['custom']))}")
    print(f"  Metric:  {meta.get('primary_metric', 'score')}")
    print(f"{'─'*68}")

    cases  = load_dataset(dataset_path)

    if n > 0:
        cases = cases[:n]
        print(f"  [smoke/limit] Running {len(cases)} / {n} cases")
    else:
        limit = config.capability_limit(capability)
        if limit > 0:
            cases = cases[:limit]

    print(f"  Total cases to run: {len(cases)}\n")

    scorer = _load_scorer(capability)
    runner = BenchmarkRunner(config, scorer)

    suite  = await runner.run_suite(
        cases,
        capability=capability,
        concurrency=concurrency,
        model=model,
    )

    _print_suite_summary(suite, meta)

    # Save results
    if output_dir:
        ts   = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = output_dir / f"{capability}_{ts}.jsonl"
        save_results(suite, path)

    return suite


async def main(args: argparse.Namespace) -> int:
    config = load_config()
    _print_banner()

    # ── Health check ──────────────────────────────────────────────────────────
    print("  Checking backend health…")
    try:
        async with OmniClient(config) as client:
            health = await client.check_health()
        status = health.get("status", "unknown")
        print(f"  Backend status: {status}")
        if status not in ("ok", "healthy", "UP"):
            print(f"  ⚠ Backend may not be healthy: {health}")
    except Exception as exc:
        print(f"\n  ✗ Backend unreachable at {config.base_url}: {exc}")
        print("  → Start the backend first: uvicorn app.main:app --reload --port 8000")
        return 1

    # ── Determine capabilities to run ─────────────────────────────────────────
    if args.capability == "all":
        capabilities = ["llm", "mcp", "rag", "self_rag", "crag", "web", "agentic"]
    else:
        capabilities = [args.capability]

    n = 1 if args.smoke else args.n

    # ── Output directory ──────────────────────────────────────────────────────
    out_dir = None
    if not args.no_save:
        out_dir = config.results_dir
        out_dir.mkdir(parents=True, exist_ok=True)

    # ── Run benchmarks ────────────────────────────────────────────────────────
    all_suites: dict[str, SuiteResult] = {}
    t_start = time.monotonic()

    for cap in capabilities:
        try:
            suite = await run_capability(
                capability  = cap,
                config      = config,
                n           = n,
                concurrency = args.concurrency,
                model       = args.model,
                output_dir  = out_dir,
            )
            all_suites[cap] = suite
        except FileNotFoundError as exc:
            print(f"\n  ✗ Skipping '{cap}': {exc}")
        except Exception as exc:
            print(f"\n  ✗ '{cap}' failed: {exc}")

    total_elapsed = time.monotonic() - t_start
    print(f"\n  Total elapsed: {total_elapsed:.1f}s")

    # ── Final summary table ───────────────────────────────────────────────────
    if all_suites:
        _print_final_summary(all_suites)

    # ── Generate report ───────────────────────────────────────────────────────
    if args.report and all_suites and out_dir:
        print("  Generating benchmark report…")
        try:
            from benchmarks.report.generate_report import generate_markdown_report
            report_path = config.report_dir / "benchmark_report.md"
            # Collect all result files
            result_files = list(out_dir.glob("*.jsonl"))
            generate_markdown_report(result_files, report_path)
            print(f"  Report → {report_path}")
        except Exception as exc:
            print(f"  ⚠ Report generation failed: {exc}")

    return 0


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_benchmarks",
        description="Omni AI Production Benchmark Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Smoke test (1 case per capability, ~5 min)
  python -m benchmarks.run_benchmarks --smoke

  # Full RAG benchmark
  python -m benchmarks.run_benchmarks --capability rag

  # Full suite with report
  python -m benchmarks.run_benchmarks --capability all --concurrency 4 --report

  # 10-case MCP test
  python -m benchmarks.run_benchmarks --capability mcp --n 10
        """,
    )
    p.add_argument(
        "--capability",
        choices=["all", "llm", "mcp", "rag", "self_rag", "crag", "web", "agentic"],
        default="all",
        help="Which capability benchmark to run (default: all)",
    )
    p.add_argument(
        "--concurrency", type=int, default=4,
        help="Number of concurrent test cases (default: 4)",
    )
    p.add_argument(
        "--n", type=int, default=0,
        help="Limit to N cases per capability (0 = use dataset default limit)",
    )
    p.add_argument(
        "--smoke", action="store_true",
        help="Smoke test mode: run 1 case per capability (overrides --n)",
    )
    p.add_argument(
        "--report", action="store_true",
        help="Generate markdown benchmark report after run",
    )
    p.add_argument(
        "--model", default="gemini-2.0-flash",
        help="LLM model to use for chat (default: gemini-2.0-flash)",
    )
    p.add_argument(
        "--no-save", action="store_true",
        help="Do not save results to disk",
    )
    return p


if __name__ == "__main__":
    parser = build_parser()
    args   = parser.parse_args()
    sys.exit(asyncio.run(main(args)))
