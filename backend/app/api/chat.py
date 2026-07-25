import asyncio
import json
import os
import traceback
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
    if "gemini" in m or "google" in m:
        return "google"
    if "llama" in m or "mixtral" in m:
        return "groq"
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
  chat = await ChatService.get_chat_by_id(db, chat_id, current_user.id)
  if not chat:
    raise HTTPException(status_code=404, detail="Conversation session not found")
  return await ChatService.get_chat_messages(db, chat_id)


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
  chat = await ChatService.get_chat_by_id(db, chat_id, current_user.id)
  if not chat:
    raise HTTPException(status_code=404, detail="Conversation session not found")

  await ChatService.delete_messages_after(db, chat_id, schema.parent_message_id)

  images_payload = (
      [img.model_dump() for img in schema.images] if schema.images else None
  )
  user_msg = await ChatService.save_message(
      db=db,
      chat_id=chat_id,
      role="user",
      content=schema.content,
      parent_id=schema.parent_message_id,
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

  final_key = user_keys.get(resolved_prov)
  # Extra fallback: google/gemini alias
  if not final_key and resolved_prov in ("google", "gemini"):
      final_key = user_keys.get("gemini") or user_keys.get("google")

  # Fallback to system settings if not provided by user keys
  from app.core.config import settings
  if not final_key:
      if resolved_prov in ("google", "gemini") and settings.GEMINI_API_KEY:
          final_key = settings.GEMINI_API_KEY
      elif resolved_prov == "openrouter" and settings.OPENROUTER_API_KEY:
          final_key = settings.OPENROUTER_API_KEY
      elif resolved_prov == "groq" and settings.GROQ_API_KEY:
          final_key = settings.GROQ_API_KEY
      elif resolved_prov == "openai" and settings.OPENAI_API_KEY:
          final_key = settings.OPENAI_API_KEY

  key_found = bool(final_key and not str(final_key).startswith("mock_"))

  langchain_messages = []

  for msg in db_messages:
    if msg.role == "user":
      langchain_messages.append(HumanMessage(content=msg.content))
    elif msg.role == "assistant":
      langchain_messages.append(AIMessage(content=msg.content))

  uploaded_file_paths = [
      doc.storage_path
      for doc in user_docs
      if doc.storage_path and os.path.exists(doc.storage_path)
      and doc.status in ("ready", "pending")
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
  }

  async def sse_event_stream():
    logger.error("STREAM GENERATOR STARTED")
    try:
      if not key_found:
          err_msg = f"Authentication failed - Missing or invalid API key for provider {(resolved_prov or 'unknown').upper()}. Configure it in Settings."
          logger.error(f"YIELDING AUTH ERROR: {err_msg}")
          yield f"data: {json.dumps({'event': 'error', 'detail': err_msg})}\n\n"
          yield "data: [DONE]\n\n"
          return

      queue = asyncio.Queue()
      metrics_store = {}

      async def on_token_callback(token: str):
        await queue.put({"event": "chunk", "text": token})

      async def on_metrics_callback(metrics: dict):
        metrics_store.update(metrics)
        await queue.put({"event": "metrics", "metrics": metrics})

      config = {
          "configurable": {
              "user_id": current_user.id,
              "chat_id": chat_id,
              "memories": memories,
              "on_token": on_token_callback,
              "on_metrics": on_metrics_callback,
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
          }
      }

      logger.info("STARTING GRAPH TASK...")
      task = asyncio.create_task(agent_graph.ainvoke(initial_state, config))

      while not task.done() or not queue.empty():
        try:
          chunk = await asyncio.wait_for(queue.get(), timeout=0.005)  # 5ms poll — 20x faster first token
          yield f"data: {json.dumps(chunk)}\n\n"
          queue.task_done()
        except asyncio.TimeoutError:
          continue
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
          response_content = "*[No response generated — please try again]*"

        try:
          from app.core.database import AsyncSessionLocal, get_db
          get_db_override = request.app.dependency_overrides.get(get_db)
          if get_db_override:
            async for test_db in get_db_override():
              await ChatService.save_message(
                  db=test_db,
                  chat_id=chat_id,
                  role="assistant",
                  content=response_content,
                  parent_id=user_msg.id,
                  developer_metrics=metrics_store or None
              )
              if is_first_message:
                auto_title = ChatService.generate_short_descriptive_title(schema.content)
                await ChatService.update_chat_title(test_db, chat_id, current_user.id, auto_title)
                logger.error(f"YIELDING TITLE EVENT: {auto_title}")
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
                  developer_metrics=metrics_store or None
              )

              if is_first_message:
                auto_title = ChatService.generate_short_descriptive_title(schema.content)
                await ChatService.update_chat_title(save_db, chat_id, current_user.id, auto_title)
                logger.error(f"YIELDING TITLE EVENT: {auto_title}")
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

      logger.error("YIELDING DONE")
      yield "data: [DONE]\n\n"
    except Exception as stream_err:
      logger.error(f"CRITICAL UNCAUGHT EXCEPTION IN sse_event_stream: {traceback.format_exc()}")
      yield f"data: {json.dumps({'event': 'error', 'detail': str(stream_err)})}\n\n"
      yield "data: [DONE]\n\n"

  logger.error(">>> RETURNING STREAMING RESPONSE <<<")
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
