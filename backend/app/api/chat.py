import asyncio
import json
import os
import traceback
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.auth import get_current_user
from app.schemas.auth import UserOut
from app.schemas.chat import (
    ChatOut, MessageOut, MessageCreate, ChatCreate, ChatUpdate,
    ChatShareUpdate, SharedChatOut, SharedMessageOut,
)
from app.models.chat import Chat, Message, SharedLink
from app.services.chat_service import ChatService
from app.agent.graph import agent_graph
from langchain_core.messages import HumanMessage, AIMessage
from app.agent.prompts import INTENT_NORMAL_CHAT

import logging

logger = logging.getLogger("api.chat")

def resolve_provider_from_model(model: str) -> str:
    m = (model or "").lower().strip()
    if m.startswith("openrouter/"):
        return "openrouter"
    if "gemini" in m:
        return "google"
    if "llama" in m or "mixtral" in m or "gemma" in m or "groq" in m:
        return "groq"
    if "google" in m:
        return "google"
    if "gpt" in m or "o1-" in m:
        return "openai"
    if "claude" in m:
        return "anthropic"
    if "deepseek" in m:
        return "deepseek"
    if "glm" in m:
        return "glm"
    if "qwen" in m:
        return "alibaba"
    return "google"

router = APIRouter(prefix="/chats", tags=["Chat & Messages"])

@router.get("", response_model=List[ChatOut])
async def list_chats(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
  return await ChatService.get_user_chats(db, current_user.id)

@router.post("", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
async def create_chat(
    schema: ChatCreate,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
  return await ChatService.create_chat(db, current_user.id, schema.title)


@router.get("/shared/{share_id}", response_model=SharedChatOut)
async def get_shared_chat(
    share_id: str,
    db: AsyncSession = Depends(get_db)
):
  from sqlalchemy import select as sa_select
  from app.models.chat import SharedLink, Chat, Message

  shared_link = await ChatService.get_shared_link_by_id(db, share_id)
  if not shared_link:
    raise HTTPException(status_code=404, detail="Shared chat not found or access restricted")

  chat_res = await db.execute(sa_select(Chat).where(Chat.id == shared_link.chat_id))
  chat = chat_res.scalar_one_or_none()

  is_live = chat and getattr(chat, "is_live_share", False)

  if is_live:
    raw_msgs = await ChatService.get_chat_messages(db, shared_link.chat_id)
    messages = [
      SharedMessageOut(
        id=m.id,
        role=m.role,
        content=m.content,
        created_at=m.created_at
      )
      for m in raw_msgs
      if m.role not in ("system", "tool")
    ]
  else:
    messages = [
      SharedMessageOut(
        id=m["id"],
        role=m["role"],
        content=m["content"],
        created_at=m["created_at"]
      )
      for m in (shared_link.snapshot_messages or [])
      if isinstance(m, dict) and m.get("role") not in ("system", "tool")
    ]

  return {
    "id": share_id,
    "title": shared_link.title,
    "is_live_share": bool(is_live),
    "messages": messages
  }


@router.get("/{chat_id}", response_model=List[MessageOut])
async def get_chat_history(
    chat_id: str,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
  try:
    chat = await ChatService.get_chat_by_id(db, chat_id, current_user.id)
    if not chat:
      raise HTTPException(status_code=404, detail="Conversation session not found")
    return await ChatService.get_chat_messages(db, chat_id)
  except HTTPException:
    raise
  except Exception as exc:
    logger.error(f"Error fetching chat history for chat_id={chat_id}: {exc}\n{traceback.format_exc()}")
    raise HTTPException(status_code=500, detail="Failed to retrieve conversation history. Please try again.")


@router.patch("/{chat_id}", response_model=ChatOut)
async def update_chat(
    chat_id: str,
    schema: ChatUpdate,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
  chat = await ChatService.get_chat_by_id(db, chat_id, current_user.id)
  if not chat:
    raise HTTPException(status_code=404, detail="Conversation session not found")
  if schema.title is not None:
    updated = await ChatService.update_chat_title(db, chat_id, current_user.id, schema.title)
    if updated:
      return updated
  return chat


@router.delete("/all")
async def delete_all_chats(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
  count = await ChatService.delete_all_chats(db, current_user.id)
  return {"detail": f"Successfully deleted {count} chats", "count": count}

@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
  success = await ChatService.delete_chat(db, chat_id, current_user.id)
  if not success:
    raise HTTPException(status_code=404, detail="Conversation session not found")
  return {"detail": "Chat deleted successfully"}

@router.delete("/{chat_id}/messages/{message_id}")
async def delete_message(
    chat_id: str,
    message_id: str,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
  chat = await ChatService.get_chat_by_id(db, chat_id, current_user.id)
  if not chat:
    raise HTTPException(status_code=404, detail="Conversation session not found")
  deleted_count = await ChatService.delete_single_message(db, chat_id, message_id)
  return {"detail": "Message deleted", "deleted_count": deleted_count}

@router.post("/{chat_id}/messages")
async def stream_agent_message(
    chat_id: str,
    schema: MessageCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
  logger.info(f"stream_agent_message: chat_id={chat_id}")

  # ── Per-user rate limit (200 req/min per user ID) ─────────────────────────
  # Complements the per-IP limit (100/min) in the global middleware.
  # Fails open if Redis is unavailable so chat is never blocked by cache outage.
  from app.core.redis_client import rate_limit_check as _rate_limit_check
  _user_rl_key = f"ratelimit:user:{current_user.id}"
  _user_allowed = await _rate_limit_check(_user_rl_key, limit=200, window_seconds=60)
  if not _user_allowed:
      logger.warning(f"[RateLimit] User {current_user.id} exceeded 200 req/min on chat")
      raise HTTPException(
          status_code=429,
          detail="Too many requests. You have exceeded the per-user rate limit (200/min). Please slow down.",
      )

  try:
    chat = await ChatService.get_chat_by_id(db, chat_id, current_user.id)
    if not chat:
      raise HTTPException(status_code=404, detail="Conversation session not found")

    await ChatService.delete_messages_after(db, chat_id, schema.parent_message_id)

    import re as _re
    clean_save_content = _re.sub(r"\[System Context:[^\]]*\]\n?", "", schema.content)
    clean_save_content = _re.sub(r"\[User Location Context:[^\]]*\]\n?", "", clean_save_content).strip() or schema.content

    images_payload = (
        [img.model_dump() for img in schema.images] if schema.images else None
    )

    # Guard: verify parent_message_id still exists after the delete above.
    # When the user edits the very first message, delete_messages_after removes
    # ALL messages, so parent_message_id no longer exists in the DB.
    # Passing a stale FK causes a ForeignKeyViolationError (HTTP 500).
    safe_parent_id: Optional[str] = None
    if schema.parent_message_id:
      from sqlalchemy.future import select as _select
      _ref = await db.execute(
          _select(Message.id).where(Message.id == schema.parent_message_id)
      )
      if _ref.scalar_one_or_none():
        safe_parent_id = schema.parent_message_id

    user_msg = await ChatService.save_message(
        db=db,
        chat_id=chat_id,
        role="user",
        content=clean_save_content,
        parent_id=safe_parent_id,
        images=images_payload,
    )

    is_first_message = chat.title in ("New Chat", "", None)

    from sqlalchemy.future import select
    from app.models.user import ApiKey
    from app.core.security import decrypt_api_key
    from app.services.document_service import DocumentService

    # ── Parallelize all pre-flight DB queries for minimum latency ─────────────
    db_keys_result, db_messages, memories, user_docs = await asyncio.gather(
        db.execute(select(ApiKey).where(ApiKey.user_id == current_user.id)),
        ChatService.get_chat_messages(db, chat_id),
        ChatService.get_user_memories(db, current_user.id),
        DocumentService.get_user_documents(db, current_user.id, chat_id=chat_id),
    )
    api_keys = db_keys_result.scalars().all()

    # ── Decrypt user API keys & resolve provider ──────────────────────────────
    user_keys = {}
    for k in api_keys:
      prov = (getattr(k, "provider_name", "") or "").lower()
      enc_val = getattr(k, "encrypted_api_key", None)
      if enc_val:
        try:
          user_keys[prov] = decrypt_api_key(enc_val)
        except Exception:
          user_keys[prov] = enc_val

    # ── Merge request header keys (x-api-keys) if present ─────────────────────
    x_api_keys_header = request.headers.get("x-api-keys")
    if x_api_keys_header:
      try:
        header_keys = json.loads(x_api_keys_header)
        for hk, hv in header_keys.items():
          if hk and hv:
            user_keys[hk.lower()] = hv
      except Exception:
        pass

    # ── Real-time provider resolution: look up which provider owns this model ──
    resolved_prov = None
    for k in api_keys:
        if k.status == "VERIFIED" and k.available_models:
            prov_name = (getattr(k, "provider_name", "") or "").lower()
            if prov_name == "gemini":
                prov_name = "google"
            if schema.model in k.available_models:
                resolved_prov = prov_name
                break
    # Fallback: keyword-based inference if model not found in any provider's live list
    if not resolved_prov:
        resolved_prov = resolve_provider_from_model(schema.model)

    final_key = user_keys.get(resolved_prov) or getattr(settings, f"{resolved_prov.upper()}_API_KEY", None)
    if not final_key and resolved_prov == "google":
        final_key = user_keys.get("gemini")

    key_found = bool(final_key and not str(final_key).startswith("mock_"))

    # ── Auto Key Fallback: if requested provider key missing, fallback to any valid available key ──
    if not key_found:
        available_fallback = None
        if (user_keys.get("openai") or settings.OPENAI_API_KEY) and not str(settings.OPENAI_API_KEY or "").startswith("mock_"):
            available_fallback = ("openai", user_keys.get("openai") or settings.OPENAI_API_KEY, "gpt-4o-mini")
        elif (user_keys.get("google") or user_keys.get("gemini") or settings.GEMINI_API_KEY) and not str(settings.GEMINI_API_KEY or "").startswith("mock_"):
            available_fallback = ("google", user_keys.get("google") or user_keys.get("gemini") or settings.GEMINI_API_KEY, "gemini-2.5-flash")
        elif (user_keys.get("groq") or settings.GROQ_API_KEY) and not str(settings.GROQ_API_KEY or "").startswith("mock_"):
            available_fallback = ("groq", user_keys.get("groq") or settings.GROQ_API_KEY, "llama-3.3-70b-versatile")
        elif (user_keys.get("openrouter") or settings.OPENROUTER_API_KEY) and not str(settings.OPENROUTER_API_KEY or "").startswith("mock_"):
            available_fallback = ("openrouter", user_keys.get("openrouter") or settings.OPENROUTER_API_KEY, "meta-llama/llama-3.1-8b-instruct:free")
        
        if available_fallback:
            resolved_prov, final_key, schema.model = available_fallback
            key_found = True
            logger.info(f"Auto-fallback active: using provider {resolved_prov} with model {schema.model}")

    # ── Chat history trimming ──────────────────────────────────────
    _MAX_HISTORY_MESSAGES = 60       # 30 turn pairs
    _MAX_HISTORY_CHARS    = 60_000   # ~15k tokens at 4 chars/token

    # Step 1: apply hard turn cap — take the N most recent messages
    db_messages_trimmed = list(db_messages[-_MAX_HISTORY_MESSAGES:]) if len(db_messages) > _MAX_HISTORY_MESSAGES else list(db_messages)

    # Step 2: apply character budget — drop oldest messages until under budget
    _total_chars = sum(len(m.content or "") for m in db_messages_trimmed)
    while _total_chars > _MAX_HISTORY_CHARS and len(db_messages_trimmed) > 2:
        removed = db_messages_trimmed.pop(0)
        _total_chars -= len(removed.content or "")

    if len(db_messages_trimmed) < len(db_messages):
        logger.info(
            f"[HistoryTrim] Trimmed chat history: {len(db_messages)} → "
            f"{len(db_messages_trimmed)} messages (chars={_total_chars})"
        )

    langchain_messages = []
    for msg in db_messages_trimmed:
      if msg.role == "user":
        langchain_messages.append(HumanMessage(content=msg.content))
      elif msg.role == "assistant":
        langchain_messages.append(AIMessage(content=msg.content))

    _IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".heic", ".heif"}
    uploaded_file_paths = [
        doc.storage_path
        for doc in user_docs
        if doc.storage_path
        and doc.status in ("ready", "pending")
        and not any(doc.storage_path.lower().endswith(ext) for ext in _IMAGE_EXTENSIONS)
    ]

    initial_state = {
        "messages": langchain_messages,
        "active_model": schema.model,
        "user_id": current_user.id,
        "chat_id": chat_id,
        "retrieved_documents": [],
        "metrics": {},
        "response_text": "",
        "steps": [],
        "images": [{"base64": img.base64, "mimeType": img.mimeType} for img in (schema.images or [])],
        "intent":               INTENT_NORMAL_CHAT,
        "allowed_tools":        [],
        "is_private_doc_query": False,
        "no_doc_answer":        False,
        "memory_write_content":  None,
        "memory_write_category": None,
        "uploaded_file_paths":   uploaded_file_paths,
        "tool_calls":            [],
        "tool_dag":              None,
        "tool_execution_results": None,
        "reflection_feedback":   None,
        "reflection_passed":     True,
        "iteration_count":       0,
        "source_documents":      [],
        "detected_language":     None,
        "language_mode":         None,
        "generation_mode":       None,
        "execution_trace":       [],
        "semantic_status":       {},
        "memory_status":         {},
        "web_status":            {},
        "inconsistencies":       [],
    }
  except HTTPException:
    raise
  except Exception as preflight_err:
    err_detail = str(preflight_err) or "Failed to initialize response generator"
    logger.error(f"Error during stream_agent_message preflight setup: {preflight_err}\n{traceback.format_exc()}")
    async def sse_preflight_error():
      yield f"data: {json.dumps({'event': 'error', 'detail': err_detail})}\n\n"
      yield "data: [DONE]\n\n"
    return StreamingResponse(sse_preflight_error(), media_type="text/event-stream")

  async def sse_event_stream():
    # BUG-8: use INFO not ERROR for normal lifecycle events
    logger.info("STREAM GENERATOR STARTED")
    try:
      # BUG-2 FIX: Run PromptInjectionGuard before the graph is invoked.
      # Catches jailbreak / system-prompt-override patterns early and blocks
      # the request without touching the LLM at all.
      try:
        from app.middleware.security import PromptInjectionGuard
        _is_suspicious, _reason = PromptInjectionGuard.inspect_prompt(schema.content)
        if _is_suspicious:
          logger.warning(
            f"[PromptInjectionGuard] Blocked request. Reason: {_reason} | "
            f"user={current_user.id} chat={chat_id}"
          )
          _block_msg = (
            "I'm sorry, but I can't process that request. "
            "It appears to contain patterns that may violate usage policies."
          )
          yield f"data: {json.dumps({'event': 'chunk', 'text': _block_msg})}\n\n"
          yield "data: [DONE]\n\n"
          return
      except ImportError:
        pass  # Guard module not present — non-fatal, continue

      if not key_found:
          err_msg = f"Authentication failed - Missing or invalid API key for provider {(resolved_prov or 'unknown').upper()}. Configure it in Settings."
          logger.error(f"YIELDING AUTH ERROR: {err_msg}")
          try:
              from app.core.database import AsyncSessionLocal
              async with AsyncSessionLocal() as err_db:
                  await ChatService.save_message(
                      db=err_db,
                      chat_id=chat_id,
                      role="assistant",
                      content=f"⚠️ **{err_msg}**",
                      parent_id=user_msg.id,
                  )
          except Exception as _err_save_ex:
              logger.warning(f"Could not persist auth error message: {_err_save_ex}")

          yield f"data: {json.dumps({'event': 'error', 'detail': err_msg})}\n\n"
          yield "data: [DONE]\n\n"
          return

      queue = asyncio.Queue()
      metrics_store = {}

      async def on_token_callback(token: str):
        await queue.put({"event": "chunk", "text": token})

      async def on_step_callback(step_name: str):
        await queue.put({"event": "step", "step": step_name})

      async def on_metrics_callback(metrics: dict):
        metrics_store.update(metrics)
        await queue.put({"event": "metrics", "metrics": metrics})

      # BUG-5d FIX: Instantiate RequestTelemetry per-request and pass it through
      # config so graph nodes can call record_routing / record_llm / record_evidence.
      # finalize() is called after graph completion and emits a structured JSON log.
      _request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
      _telemetry = None
      try:
        from app.core.telemetry import RequestTelemetry
        _telemetry = RequestTelemetry(
          request_id=_request_id,
          user_id=str(current_user.id),
          chat_id=chat_id,
        )
      except Exception as _tel_init_err:
        logger.warning(f"RequestTelemetry init failed (non-fatal): {_tel_init_err}")

      config = {
          "configurable": {
              "user_id": current_user.id,
              "chat_id": chat_id,
              "memories": memories,
              "on_token": on_token_callback,
              "on_step": on_step_callback,
              "on_metrics": on_metrics_callback,
              "telemetry": _telemetry,  # BUG-5d: nodes read this via config["configurable"]["telemetry"]
              # Always pass the primary resolved key for google/gemini (they share a key)
              "gemini_api_key": (final_key if resolved_prov in ["google", "gemini"] else None) or user_keys.get("gemini") or user_keys.get("google"),
              "google_api_key": (final_key if resolved_prov in ["google", "gemini"] else None) or user_keys.get("google") or user_keys.get("gemini"),
              # Pass the resolved key for its provider, plus all other user keys
              "groq_api_key":       (final_key if resolved_prov == "groq" else None) or user_keys.get("groq"),
              "openrouter_api_key": (final_key if resolved_prov == "openrouter" else None) or user_keys.get("openrouter"),
              "openai_api_key":     (final_key if resolved_prov == "openai" else None) or user_keys.get("openai"),
              "anthropic_api_key":  (final_key if resolved_prov == "anthropic" else None) or user_keys.get("anthropic"),
              "deepseek_api_key":   (final_key if resolved_prov == "deepseek" else None) or user_keys.get("deepseek"),
              "alibaba_api_key":    (final_key if resolved_prov == "alibaba" else None) or user_keys.get("alibaba"),
              "glm_api_key":        (final_key if resolved_prov == "glm" else None) or user_keys.get("glm"),
              "uploaded_file_paths": uploaded_file_paths,
              # ── Search provider keys ───────────────────────────────────────────────────
              # Full merged dict (DB-decrypted + x-api-keys header) so that
              # unified_web_search() in nodes.py can pick Tavily/SerpAPI/Exa.
              "api_keys": user_keys,
          }
      }

      logger.info("STARTING GRAPH TASK...")
      task = asyncio.create_task(agent_graph.ainvoke(initial_state, config))

      # Send initial process step event to frontend
      yield f"data: {json.dumps({'event': 'step', 'step': 'Reading query & context...'})}\n\n"

      # ── MASTER TIMEOUT GUARD ─────────────────────────────────────────────────
      # If the LLM or any pipeline node hangs silently (no error, no chunks),
      # we must cancel the task so the frontend doesn't show "Thinking" forever.
      # 120 s is generous enough for multi-step MCP + RAG + reflection chains.
      GRAPH_TIMEOUT_SECONDS = 120

      # GAP-1 FIX: Check for client disconnect inside the queue loop.
      # When the browser tab closes mid-stream, cancel the graph task to avoid
      # wasting LLM tokens and compute.
      graph_deadline = asyncio.get_event_loop().time() + GRAPH_TIMEOUT_SECONDS
      while not task.done() or not queue.empty():
        try:
          # ── Hard-deadline check ───────────────────────────────────────────
          remaining = graph_deadline - asyncio.get_event_loop().time()
          if remaining <= 0:
            logger.error(
                f"Graph task exceeded {GRAPH_TIMEOUT_SECONDS}s hard timeout "
                f"for chat_id={chat_id} — cancelling."
            )
            task.cancel()
            yield f"data: {json.dumps({'event': 'error', 'detail': 'Request timed out. The model took too long to respond. Please try again.'})}\n\n"
            return

          # Check if client disconnected mid-stream
          if await request.is_disconnected():
            logger.info(f"Client disconnected for chat_id={chat_id} — cancelling graph task")
            task.cancel()
            return

          # Event-driven queue fetch with deadline-aware timeout
          get_task = asyncio.create_task(queue.get())
          done_set, _ = await asyncio.wait(
              [get_task, task],
              return_when=asyncio.FIRST_COMPLETED,
              timeout=min(remaining, 30.0),   # wake up at least every 30s to check deadline
          )

          if get_task in done_set:
            chunk = get_task.result()
            yield f"data: {json.dumps(chunk)}\n\n"
            queue.task_done()
            # Each yielded chunk refreshes the deadline (model IS responding)
            graph_deadline = asyncio.get_event_loop().time() + GRAPH_TIMEOUT_SECONDS
          elif task in done_set:
            # Graph task completed — cancel pending queue get if not finished
            if not get_task.done():
              get_task.cancel()

            # Drain any remaining buffered tokens instantly
            while not queue.empty():
              chunk = queue.get_nowait()
              yield f"data: {json.dumps(chunk)}\n\n"
              queue.task_done()
            break
          else:
            # asyncio.wait timed out (neither queue nor task finished in 30s window)
            # Loop will re-check hard deadline at top of next iteration.
            if not get_task.done():
              get_task.cancel()
        except Exception as err:
          logger.error(f"ERROR IN QUEUE LOOP: {err}")
          yield f"data: {json.dumps({'event': 'error', 'detail': str(err)})}\n\n"
          break

      logger.info("GRAPH TASK COMPLETED, SAVING ASSISTANT MESSAGE...")
      try:
        final_state = await task
        logger.info(f"FINAL STATE KEYS: {list(final_state.keys()) if isinstance(final_state, dict) else final_state}")
        response_content = final_state.get("response_text", "").strip() if isinstance(final_state, dict) else ""
        if not response_content:
          logger.warning(f"No response content generated for chat_id={chat_id} — omitting DB persistence.")
          yield f"data: {json.dumps({'event': 'error', 'detail': 'Generation failed — no output produced.'})}\n\n"
          yield "data: [DONE]\n\n"
          return

        # BUG-5d FIX: Finalize telemetry — attaches cache hit/miss stats
        # and emits the structured JSON "agent_request" log line.
        if _telemetry is not None:
          try:
            from app.core.cache_service import get_all_cache_stats
            _telemetry.attach_cache_stats(get_all_cache_stats())
            _tel_payload = _telemetry.finalize()
            logger.debug(f"Telemetry finalized: total_latency_ms={_tel_payload.get('total_latency_ms')}ms")
          except Exception as _tel_fin_err:
            logger.warning(f"Telemetry finalize failed (non-fatal): {_tel_fin_err}")

        # Compile full runtime execution trace & Dev HUD metrics
        if isinstance(final_state, dict):
            metrics_store.update({
                "model_used": schema.model,
                "latency_ms": getattr(_telemetry, "total_latency_ms", 0) if _telemetry else 0,
                "cost_estimate": 0.0,
                "tokens_input": getattr(_telemetry, "token_estimate", 0) if _telemetry else 0,
                "tokens_output": len(response_content) // 4,
                "execution_trace": final_state.get("execution_trace", []),
                "semantic_status": final_state.get("semantic_status", {}),
                "memory_status": final_state.get("memory_status", {}),
                "web_status": final_state.get("web_status", {}),
                "inconsistencies": final_state.get("inconsistencies", []),
                "source_documents": final_state.get("source_documents", []),
                "retrieved_context": final_state.get("retrieved_documents", []),
                "steps": final_state.get("steps", []),
                "generation_mode": final_state.get("generation_mode"),
            })

        # Yield runtime telemetry metrics payload to frontend right before DB save
        yield f"data: {json.dumps({'event': 'metrics', 'metrics': metrics_store})}\n\n"

        try:
          from app.core.database import AsyncSessionLocal, get_db
          get_db_override = request.app.dependency_overrides.get(get_db)
          tc_payload = final_state.get("tool_calls") if isinstance(final_state, dict) else None
          if tc_payload:
            metrics_store["tool_calls"] = tc_payload

          if get_db_override:
            async for test_db in get_db_override():
              await ChatService.save_message(
                  db=test_db,
                  chat_id=chat_id,
                  role="assistant",
                  content=response_content,
                  parent_id=user_msg.id,
                  tool_calls=tc_payload or None,
                  developer_metrics=metrics_store or None
              )
              if is_first_message:
                auto_title = ChatService.generate_short_descriptive_title(schema.content)
                await ChatService.update_chat_title(test_db, chat_id, current_user.id, auto_title)
                # BUG-8 FIX: was logger.error() — not an error
                logger.info(f"YIELDING TITLE EVENT: {auto_title}")
                yield f"data: {json.dumps({'event': 'title', 'title': auto_title})}\n\n"
              break
          else:
            async with AsyncSessionLocal() as save_db:
              await ChatService.save_message(
                  db=save_db,
                  chat_id=chat_id,
                  role="assistant",
                  content=response_content,
                  parent_id=user_msg.id,
                  tool_calls=tc_payload or None,
                  developer_metrics=metrics_store or None
              )

              if is_first_message:
                auto_title = ChatService.generate_short_descriptive_title(schema.content)
                await ChatService.update_chat_title(save_db, chat_id, current_user.id, auto_title)
                # BUG-8 FIX: was logger.error() — not an error
                logger.info(f"YIELDING TITLE EVENT: {auto_title}")
                yield f"data: {json.dumps({'event': 'title', 'title': auto_title})}\n\n"

          from app.services.memory_service import MemoryService
          background_tasks.add_task(
              MemoryService.extract_and_save_memories,
              user_id=current_user.id,
              chat_id=chat_id,
              user_content=schema.content,
              assistant_content=response_content
          )
        except Exception as save_err:
          logger.error(f"Failed to persist assistant message: {save_err}")
      except Exception as err:
        logger.error(f"ERROR IN FINAL STATE PROCESSING: {traceback.format_exc()}")
        yield f"data: {json.dumps({'event': 'error', 'detail': str(err)})}\n\n"

      # BUG-8 FIX: was logger.error() — not an error
      logger.info("YIELDING DONE")
      yield "data: [DONE]\n\n"
    except Exception as stream_err:
      logger.error(f"CRITICAL UNCAUGHT EXCEPTION IN sse_event_stream: {traceback.format_exc()}")
      yield f"data: {json.dumps({'event': 'error', 'detail': str(stream_err)})}\n\n"
      yield "data: [DONE]\n\n"

  # BUG-8 FIX: was logger.error() — not an error
  logger.info(">>> RETURNING STREAMING RESPONSE <<<")
  return StreamingResponse(sse_event_stream(), media_type="text/event-stream")


@router.post("/{chat_id}/share", response_model=ChatOut)
async def share_chat(
    chat_id: str,
    schema: ChatShareUpdate,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
  chat = await ChatService.toggle_chat_share(
    db, chat_id, current_user.id,
    schema.is_shared,
    is_live=schema.is_live or False
  )
  if not chat:
    raise HTTPException(status_code=404, detail="Conversation session not found")
  return chat
