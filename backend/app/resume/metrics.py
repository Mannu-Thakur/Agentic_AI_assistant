"""
app/resume/metrics.py — Document AI Telemetry, Observability & Structured Logging.

Tracks:
  - Total Parse Time (ms)
  - Parser Selection (pdf_native, pdf_ocr, docx, txt, image_ocr)
  - OCR Triggered & OCR Confidence
  - LLM Usage & Fallback Triggered
  - Schema Validation Failures
  - Section Extraction Confidence Distribution
"""

from __future__ import annotations
import time
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("app.resume.metrics")


@dataclass
class ParseTelemetry:
    """Dataclass storing execution metrics for a single Document AI parse request."""
    request_id: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    parse_duration_ms: float = 0.0
    file_ext: str = ""
    raw_text_length: int = 0
    parser_selection: str = ""      # "pdf_native", "pdf_ocr", "docx", "txt", "image_ocr"
    resume_layout: str = "single_column"  # "single_column", "two_column"
    ocr_triggered: bool = False
    ocr_confidence: float = 1.0
    llm_used: bool = False
    llm_model: str = ""
    llm_fallback_triggered: bool = False
    overall_confidence: float = 0.0
    section_confidences: Dict[str, float] = field(default_factory=dict)
    low_confidence_fields: List[str] = field(default_factory=list)
    validation_failures: List[str] = field(default_factory=list)

    def finalize(self):
        """Finalize telemetry calculations and log telemetry record."""
        self.end_time = time.time()
        self.parse_duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        
        telemetry_dict = {
            "event": "document_ai_parse_completed",
            "duration_ms": self.parse_duration_ms,
            "parser": self.parser_selection,
            "layout": self.resume_layout,
            "ocr_used": self.ocr_triggered,
            "llm_used": self.llm_used,
            "overall_confidence": self.overall_confidence,
            "section_confidences": self.section_confidences,
            "low_conf_count": len(self.low_confidence_fields),
        }
        logger.info(f"[DocumentAI Metrics] {json.dumps(telemetry_dict)}")


def log_parse_metrics(telemetry: ParseTelemetry):
    """Log parse metrics to structured logger."""
    telemetry.finalize()
