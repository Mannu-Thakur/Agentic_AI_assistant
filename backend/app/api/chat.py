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
    m = model.lower().strip()
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
  logger.error(f">>> ENTERED STREAM_AGENT_MESSAGE for chat_id={chat_id} <<<")
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

  # Pre-fetch context and API keys using request db session BEFORE creating SSE stream
  db_messages = await ChatService.get_chat_messages(db, chat_id)
  langchain_messages = []
  for msg in db_messages:
    if msg.role == "user":
      langchain_messages.append(HumanMessage(content=msg.content))
    elif msg.role == "assistant":
      langchain_messages.append(AIMessage(content=msg.content))

  from sqlalchemy.future import select
  from app.models.user import ApiKey
  from app.core.security import decrypt_api_key

  db_keys = await db.execute(
      select(ApiKey).where(ApiKey.user_id == current_user.id)
  )
  api_keys = db_keys.scalars().all()
  
  def mask_key_str(k: Optional[str]) -> str:
      if not k:
          return "None"
      if len(k) > 8:
          return f"{k[:4]}...{k[-4:]}"
      return "****"

  incoming_headers_summary = {k: v for k, v in request.headers.items() if k.lower() in ("x-api-keys", "x_api_keys", "authorization")}
  
  parsed_header_keys = {}
  x_keys_header = request.headers.get("x-api-keys") or request.headers.get("x_api_keys")
  if x_keys_header:
      try:
          parsed_header_keys = json.loads(x_keys_header)
      except Exception as e:
          logger.error(f"Failed to parse x-api-keys header: {e}")

  user_keys = {}
  key_sources = {}
  for k in api_keys:
      prov = k.provider_name.lower().strip()
      if prov == "gemini":
          prov = "google"
      try:
          user_keys[prov] = decrypt_api_key(k.encrypted_api_key)
          key_sources[prov] = "database"
      except Exception:
          user_keys[prov] = k.encrypted_api_key
          key_sources[prov] = "database_raw"

  if parsed_header_keys:
      for k, v in parsed_header_keys.items():
          prov = k.lower().strip()
          if prov == "gemini":
              prov = "google"
          if v and not v.startswith("••••") and v != "****":
              user_keys[prov] = v
              key_sources[prov] = "header_override"

  # Symmetric aliases: ensure both google and gemini keys are set
  if "google" in user_keys and "gemini" not in user_keys:
      user_keys["gemini"] = user_keys["google"]
      key_sources["gemini"] = key_sources["google"]
  if "gemini" in user_keys and "google" not in user_keys:
      user_keys["google"] = user_keys["gemini"]
      key_sources["google"] = key_sources["gemini"]

  from app.core.config import settings
  resolved_prov = resolve_provider_from_model(schema.model)
  final_key = user_keys.get(resolved_prov) or user_keys.get("google") or user_keys.get("gemini")
  
  # Environment fallback for Gemini
  if not final_key and (resolved_prov in ["google", "gemini"]) and settings.GEMINI_API_KEY:
      final_key = settings.GEMINI_API_KEY
      key_sources[resolved_prov] = "environment"
  if not final_key and resolved_prov == "groq" and settings.GROQ_API_KEY:
      final_key = settings.GROQ_API_KEY
      key_sources[resolved_prov] = "environment"
  if not final_key and resolved_prov == "openrouter" and settings.OPENROUTER_API_KEY:
      final_key = settings.OPENROUTER_API_KEY
      key_sources[resolved_prov] = "environment"
  if not final_key and resolved_prov == "openai" and settings.OPENAI_API_KEY:
      final_key = settings.OPENAI_API_KEY
      key_sources[resolved_prov] = "environment"

  key_found = bool(final_key)

  logger.info(json.dumps({
      "event": "messages_auth_audit",
      "selected_model": schema.model,
      "resolved_provider": resolved_prov,
      "incoming_headers": incoming_headers_summary,
      "parsed_x_api_keys": {k: mask_key_str(v) for k, v in parsed_header_keys.items()},
      "final_api_key_source": key_sources.get(resolved_prov, "none"),
      "whether_key_found": key_found,
      "keys_resolved_masked": {k: mask_key_str(v) for k, v in user_keys.items()}
  }))

  memories = await ChatService.get_user_memories(db, current_user.id)

  from app.services.document_service import DocumentService
  user_docs = await DocumentService.get_user_documents(db, current_user.id, chat_id=chat_id)
  uploaded_file_paths = [
      doc.storage_path
      for doc in user_docs
      if doc.storage_path and os.path.exists(doc.storage_path)
      and doc.status == "ready"
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
          err_msg = f"Authentication failed - Missing or invalid API key for provider {resolved_prov.upper()}. Configure it in Settings."
          logger.error(f"YIELDING AUTH ERROR: {err_msg}")
          yield f"data: {json.dumps({'event': 'error', 'detail': err_msg})}\n\n"
          yield "data: [DONE]\n\n"
          return

      queue = asyncio.Queue()
      metrics_store = {}

      async def on_token_callback(token: str):
        logger.error(f"ON_TOKEN_CALLBACK: {repr(token)}")
        await queue.put({"event": "chunk", "text": token})

      async def on_metrics_callback(metrics: dict):
        logger.error(f"ON_METRICS_CALLBACK: {metrics}")
        metrics_store.update(metrics)
        await queue.put({"event": "metrics", "metrics": metrics})

      config = {
          "configurable": {
              "user_id": current_user.id,
              "chat_id": chat_id,
              "memories": memories,
              "on_token": on_token_callback,
              "on_metrics": on_metrics_callback,
              "gemini_api_key": final_key if resolved_prov in ["google", "gemini"] else user_keys.get("gemini") or user_keys.get("google"),
              "google_api_key": final_key if resolved_prov in ["google", "gemini"] else user_keys.get("google") or user_keys.get("gemini"),
              "groq_api_key": user_keys.get("groq"),
              "openrouter_api_key": user_keys.get("openrouter"),
              "openai_api_key": user_keys.get("openai"),
              "anthropic_api_key": user_keys.get("anthropic"),
              "deepseek_api_key": user_keys.get("deepseek"),
              "alibaba_api_key": user_keys.get("alibaba"),
              "glm_api_key": user_keys.get("glm"),
              "uploaded_file_paths": uploaded_file_paths,
          }
      }

      logger.error("STARTING GRAPH TASK...")
      task = asyncio.create_task(agent_graph.ainvoke(initial_state, config))

      while not task.done() or not queue.empty():
        try:
          chunk = await asyncio.wait_for(queue.get(), timeout=0.1)
          logger.error(f"YIELDING QUEUE CHUNK: {chunk}")
          yield f"data: {json.dumps(chunk)}\n\n"
          queue.task_done()
        except asyncio.TimeoutError:
          continue
        except Exception as err:
          logger.error(f"ERROR IN QUEUE LOOP: {err}")
          yield f"data: {json.dumps({'event': 'error', 'detail': str(err)})}\n\n"
          break

      logger.error("GRAPH TASK COMPLETED, SAVING ASSISTANT MESSAGE...")
      try:
        final_state = await task
        logger.error(f"FINAL STATE KEYS: {list(final_state.keys()) if isinstance(final_state, dict) else final_state}")
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
