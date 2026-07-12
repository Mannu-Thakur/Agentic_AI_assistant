import asyncio
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.auth import get_current_user
from app.schemas.auth import UserOut
from app.schemas.chat import ChatOut, MessageOut, MessageCreate, ChatCreate
from app.services.chat_service import ChatService
from app.agent.graph import agent_graph
from langchain_core.messages import HumanMessage, AIMessage

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
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
  chat = await ChatService.get_chat_by_id(db, chat_id, current_user.id)
  if not chat:
    raise HTTPException(status_code=404, detail="Conversation session not found")

  # 1. Save user query message to database
  user_msg = await ChatService.save_message(
      db=db,
      chat_id=chat_id,
      role="user",
      content=schema.content,
      parent_id=schema.parent_message_id
  )

  async def sse_event_stream():
    # Queue to exchange tokens from async LangGraph callback to generator iterator
    queue = asyncio.Queue()
    metrics_store = {}

    async def on_token_callback(token: str):
      await queue.put({"event": "chunk", "text": token})

    async def on_metrics_callback(metrics: dict):
      metrics_store.update(metrics)
      await queue.put({"event": "metrics", "metrics": metrics})

    # Fetch past messages to feed to graph
    db_messages = await ChatService.get_chat_messages(db, chat_id)
    langchain_messages = []
    for msg in db_messages:
      if msg.role == "user":
        langchain_messages.append(HumanMessage(content=msg.content))
      elif msg.role == "assistant":
        langchain_messages.append(AIMessage(content=msg.content))

    # Fetch memories
    memories = await ChatService.get_user_memories(db, current_user.id)

    initial_state = {
        "messages": langchain_messages,
        "active_model": schema.model,
        "user_id": current_user.id,
        "chat_id": chat_id,
        "retrieved_documents": [],
        "metrics": {},
        "response_text": "",
        "steps": []
    }

    config = {
        "configurable": {
            "user_id": current_user.id,
            "chat_id": chat_id,
            "memories": memories,
            "on_token": on_token_callback,
            "on_metrics": on_metrics_callback
        }
    }

    # Start graph execution in the background
    task = asyncio.create_task(agent_graph.ainvoke(initial_state, config))

    # Yield messages from queue while graph execution task is running
    while not task.done() or not queue.empty():
      try:
        # Check queue with a short timeout to prevent blocking if empty and task is done
        chunk = await asyncio.wait_for(queue.get(), timeout=0.1)
        yield f"data: {json.dumps(chunk)}\n\n"
        queue.task_done()
      except asyncio.TimeoutError:
        continue
      except Exception as err:
        yield f"data: {json.dumps({'event': 'error', 'detail': str(err)})}\n\n"
        break

    # Resolve task result
    try:
      final_state = await task
      response_content = final_state.get("response_text", "")
      
      # 2. Save Assistant message with metrics to database
      await ChatService.save_message(
          db=db,
          chat_id=chat_id,
          role="assistant",
          content=response_content,
          parent_id=user_msg.id,
          developer_metrics=metrics_store or None
      )
      
      # 3. Trigger automatic background memory extraction
      from app.services.memory_service import MemoryService
      background_tasks.add_task(
          MemoryService.extract_and_save_memories,
          user_id=current_user.id,
          chat_id=chat_id,
          user_content=schema.content,
          assistant_content=response_content
      )
    except Exception as err:
      yield f"data: {json.dumps({'event': 'error', 'detail': str(err)})}\n\n"

    yield "data: [DONE]\n\n"

  return StreamingResponse(sse_event_stream(), media_type="text/event-stream")
