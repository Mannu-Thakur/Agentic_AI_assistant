"""
app/agents/vision_agent.py — Image Analysis & Generation Agent

Capabilities
------------
  • Image analysis / description via vision-capable LLMs (Gemini, GPT-4o)
  • OCR text extraction using existing Tesseract pipeline
  • Base64 image input support
  • Saves analysis report as artifact

task_input keys
---------------
  query         : str   — What to analyse / what question about the image
  image_base64  : str   — Base64-encoded image (optional)
  image_path    : str   — Local file path to image (optional)
  image_url     : str   — URL to image (optional)
  user_id       : str
  session_id    : str
  active_model  : str
  api_keys      : dict
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict, List, Optional

from app.agents.registry import BaseAgent, AgentResult, agent_registry
from app.agents.artifacts import artifact_store
from app.agents.node_helpers import call_llm_simple, _get_provider_and_key

logger = logging.getLogger("agents.vision")

# Vision-capable model fragments
_VISION_MODELS = [
    "gemini", "gpt-4o", "gpt-4-vision", "claude-3", "claude-4",
    "llama-3.2", "llava", "pixtral", "qwen-vl", "qwen2-vl",
]


def _model_supports_vision(model: str) -> bool:
    m = model.lower()
    return any(v in m for v in _VISION_MODELS)


def _load_image_base64(task_input: Dict[str, Any]) -> Optional[str]:
    """Load image as base64 from base64 string, path, or URL."""
    # Already base64
    b64 = task_input.get("image_base64", "")
    if b64:
        return b64

    # From file path
    path = task_input.get("image_path", "")
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    # From URL
    url = task_input.get("image_url", "")
    if url:
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=10) as resp:
                return base64.b64encode(resp.read()).decode()
        except Exception as exc:
            logger.warning(f"[VisionAgent] URL load failed: {exc}")

    return None


def _guess_mime(b64: str, task_input: Dict) -> str:
    """Guess MIME type from base64 header or file extension."""
    if b64.startswith("/9j/"):
        return "image/jpeg"
    if b64.startswith("iVBOR"):
        return "image/png"
    if b64.startswith("R0lGOD"):
        return "image/gif"
    path = task_input.get("image_path", "") or task_input.get("image_url", "")
    if path.lower().endswith(".png"):
        return "image/png"
    if path.lower().endswith(".gif"):
        return "image/gif"
    if path.lower().endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


async def _analyse_with_vision_llm(
    model: str,
    api_keys: Dict[str, str],
    query: str,
    image_b64: str,
    mime: str,
) -> str:
    """Send image + query to a vision LLM, return description text."""
    from langchain_core.messages import HumanMessage, SystemMessage

    provider, api_key = _get_provider_and_key(model, api_keys)

    # Build multimodal message
    content: List[Any] = [
        {"type": "text", "text": query},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{image_b64}"},
        },
    ]

    messages = [
        SystemMessage(content="You are an expert image analyst. Describe and analyse images accurately and in detail."),
        HumanMessage(content=content),
    ]

    resp = await provider.generate(
        messages=messages,
        model=model,
        api_key=api_key,
        temperature=0.2,
        max_tokens=2000,
        tools=[],
    )

    if hasattr(resp, "content"):
        out = resp.content
    elif isinstance(resp, dict):
        out = resp.get("content", str(resp))
    else:
        out = str(resp)

    if isinstance(out, list):
        out = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in out)

    return out.strip()


async def _ocr_fallback(image_b64: str) -> str:
    """Use Tesseract OCR as fallback when vision model is unavailable."""
    try:
        import base64
        import tempfile
        from PIL import Image
        import pytesseract
        import io

        img_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_bytes))
        text = pytesseract.image_to_string(img)
        return f"**OCR extracted text:**\n\n{text.strip()}" if text.strip() else "No text found in image."
    except Exception as exc:
        return f"*(Vision analysis unavailable and OCR failed: {exc})*"


@agent_registry.register("vision")
class VisionAgent(BaseAgent):
    """
    Analyses images using vision-capable LLMs (Gemini, GPT-4o).
    Falls back to Tesseract OCR if no vision model is available.
    Saves a structured analysis report as an artifact.
    """

    name = "vision"
    description = (
        "Analyses images, diagrams, screenshots, and documents using vision AI. "
        "Can describe content, extract text (OCR), answer questions about images, "
        "detect objects, read charts/graphs, and analyse visual data."
    )
    capabilities = [
        "image_analysis", "ocr", "vision", "screenshot_analysis",
        "chart_reading", "diagram_understanding",
    ]

    async def run(
        self,
        task_input: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        query      = task_input.get("query", "Describe this image in detail.")
        user_id    = task_input.get("user_id", "anon")
        session_id = task_input.get("session_id", "default")
        from app.core.config import settings
        model      = task_input.get("active_model", settings.GEMINI_MODEL)
        api_keys   = task_input.get("api_keys", {})

        logger.info(f"[VisionAgent] query={query[:60]!r} model={model}")

        # ── Step 1: Load image ────────────────────────────────────────────────
        image_b64 = _load_image_base64(task_input)
        if not image_b64:
            return AgentResult(
                agent_name=self.name,
                success=False,
                error="No image provided. Set image_base64, image_path, or image_url in task input.",
            )

        mime = _guess_mime(image_b64, task_input)

        # ── Step 2: Analyse ───────────────────────────────────────────────────
        analysis = ""
        mode_used = "unknown"

        # Try vision LLM first
        if _model_supports_vision(model):
            try:
                analysis = await _analyse_with_vision_llm(model, api_keys, query, image_b64, mime)
                mode_used = f"vision_llm:{model}"
            except Exception as exc:
                logger.warning(f"[VisionAgent] Vision LLM failed: {exc}, trying OCR")

        # Vision LLM failed or not available — try the configured Gemini model.
        if not analysis:
            fallback_model = settings.GEMINI_MODEL
            if fallback_model != model and _model_supports_vision(fallback_model):
                try:
                    analysis = await _analyse_with_vision_llm(
                        fallback_model, api_keys, query, image_b64, mime
                    )
                    mode_used = f"vision_llm:{fallback_model}"
                except Exception as exc:
                    logger.warning(f"[VisionAgent] Fallback vision LLM failed: {exc}")

        # Final fallback: OCR
        if not analysis:
            analysis = await _ocr_fallback(image_b64)
            mode_used = "ocr_fallback"

        # ── Step 3: Save artifact ─────────────────────────────────────────────
        artifact_info: Optional[Dict] = None
        try:
            report = (
                f"# Image Analysis Report\n\n"
                f"**Query:** {query}\n"
                f"**Model:** {mode_used}\n\n"
                f"## Analysis\n\n{analysis}"
            )
            art = await artifact_store.create(
                artifact_type="report",
                content=report,
                agent=self.name,
                user_id=user_id,
                session_id=session_id,
                description=query[:120],
                metadata={"mode": mode_used, "mime": mime},
            )
            artifact_info = art.to_dict()
        except Exception as exc:
            logger.warning(f"[VisionAgent] Artifact save failed: {exc}")

        return AgentResult(
            agent_name=self.name,
            success=True,
            content=analysis,
            artifacts=[artifact_info] if artifact_info else [],
            metadata={"mode": mode_used, "mime": mime},
        )
