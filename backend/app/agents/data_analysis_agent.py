"""
app/agents/data_analysis_agent.py — Data Analysis Agent

Capabilities
------------
  • CSV / Excel / JSON data analysis via Python + pandas
  • Statistical summary generation
  • Chart description (without matplotlib to avoid heavy deps)
  • Structured insight extraction via LLM
  • Artifact export of analysis reports

task_input keys
---------------
  query        : str   — Analysis question or description
  data         : str   — Raw CSV data string (optional)
  data_path    : str   — Path to CSV/Excel file (optional)
  user_id      : str
  session_id   : str
  active_model : str
  api_keys     : dict
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.agents.registry import BaseAgent, AgentResult, agent_registry
from app.agents.artifacts import artifact_store
from app.agents.node_helpers import call_llm_simple

logger = logging.getLogger("agents.data_analysis")


@agent_registry.register("data_analysis")
class DataAnalysisAgent(BaseAgent):
    """
    Analyzes structured data (CSV/Excel) and generates statistical summaries,
    insights, and chart descriptions using pandas + LLM synthesis.
    """

    name = "data_analysis"
    description = (
        "Analyzes CSV, Excel, or JSON data. Generates statistical summaries, "
        "identifies trends and outliers, and produces structured insights and "
        "chart descriptions saved as Markdown reports."
    )
    capabilities = [
        "data_analysis", "statistics", "csv_processing",
        "trend_analysis", "data_insights", "excel_analysis",
    ]

    async def run(
        self,
        task_input: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        query      = task_input.get("query", "")
        data_str   = task_input.get("data", "")
        data_path  = task_input.get("data_path", "")
        user_id    = task_input.get("user_id", "anon")
        session_id = task_input.get("session_id", "default")
        from app.core.config import settings
        model      = task_input.get("active_model", settings.GEMINI_MODEL)
        api_keys   = task_input.get("api_keys", {})

        logger.info(f"[DataAnalysisAgent] Query: {query[:60]!r}")

        # ── Step 1: Load data ─────────────────────────────────────────────────
        stats_summary = ""
        df_info = ""

        if data_str or data_path:
            try:
                import pandas as pd
                import io

                if data_str:
                    df = pd.read_csv(io.StringIO(data_str))
                elif data_path:
                    if data_path.endswith(".xlsx") or data_path.endswith(".xls"):
                        df = pd.read_excel(data_path)
                    else:
                        df = pd.read_csv(data_path)

                # Generate statistical summary
                stats_summary = df.describe(include="all").to_string()
                df_info = (
                    f"Shape: {df.shape[0]} rows × {df.shape[1]} columns\n"
                    f"Columns: {', '.join(df.columns.tolist())}\n"
                    f"Dtypes:\n{df.dtypes.to_string()}\n"
                    f"Null counts:\n{df.isnull().sum().to_string()}\n"
                )
            except ImportError:
                df_info = "(pandas not available — providing LLM-only analysis)"
            except Exception as exc:
                df_info = f"(Data loading error: {exc})"

        # ── Step 2: LLM analysis ──────────────────────────────────────────────
        analysis_prompt = f"Analyze the following and answer the query.\n\n**Query:** {query}\n"
        if df_info:
            analysis_prompt += f"\n**Data Info:**\n{df_info}"
        if stats_summary:
            analysis_prompt += f"\n**Statistical Summary:**\n{stats_summary[:2000]}"
        analysis_prompt += (
            "\n\nProvide:\n"
            "1. Key insights and patterns\n"
            "2. Notable statistics or outliers\n"
            "3. Suggested visualizations (describe chart types and axes)\n"
            "4. Data quality observations\n"
            "5. Actionable recommendations\n"
            "\nFormat with clear headings and bullet points."
        )

        try:
            analysis = await call_llm_simple(
                prompt=analysis_prompt,
                model=model,
                api_keys=api_keys,
                system="You are an expert data analyst. Provide clear, actionable insights.",
                temperature=0.2,
            )
        except Exception as exc:
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=f"Analysis LLM failed: {exc}",
            )

        # ── Step 3: Save report artifact ──────────────────────────────────────
        report_content = f"# Data Analysis Report\n\n**Query:** {query}\n\n"
        if df_info:
            report_content += f"## Dataset Info\n```\n{df_info}\n```\n\n"
        report_content += f"## Analysis\n\n{analysis}"

        artifact_info: Optional[Dict] = None
        try:
            art = await artifact_store.create(
                artifact_type="report",
                content=report_content,
                agent=self.name,
                user_id=user_id,
                session_id=session_id,
                description=query[:120],
                metadata={"query": query, "has_data": bool(data_str or data_path)},
            )
            artifact_info = art.to_dict()
        except Exception as exc:
            logger.warning(f"[DataAnalysisAgent] Artifact save failed: {exc}")

        return AgentResult(
            agent_name=self.name,
            success=True,
            content=analysis,
            artifacts=[artifact_info] if artifact_info else [],
            metadata={
                "has_data": bool(data_str or data_path),
                "query": query,
            },
        )
