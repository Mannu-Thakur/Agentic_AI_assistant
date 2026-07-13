import json
from typing import List, Dict, Any, Optional
from sqlalchemy import select, delete, desc
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.chat import Chat, Message, SharedLink
from app.models.memory import Memory
from app.schemas.chat import ChatCreate

class ChatService:
  @staticmethod
  async def get_user_chats(db: AsyncSession, user_id: str) -> List[Chat]:
    result = await db.execute(
        select(Chat)
        .where(Chat.user_id == user_id)
        .order_by(desc(Chat.updated_at))
    )
    return list(result.scalars().all())

  @staticmethod
  async def create_chat(db: AsyncSession, user_id: str, title: str = "New Chat") -> Chat:
    chat = Chat(user_id=user_id, title=title)
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat

  @staticmethod
  async def get_chat_by_id(db: AsyncSession, chat_id: str, user_id: str) -> Optional[Chat]:
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_chat_messages(db: AsyncSession, chat_id: str) -> List[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())

  @staticmethod
  async def save_message(
      db: AsyncSession,
      chat_id: str,
      role: str,
      content: str,
      parent_id: Optional[str] = None,
      tool_calls: Optional[List[Dict[str, Any]]] = None,
      developer_metrics: Optional[Dict[str, Any]] = None,
  ) -> Message:
    message = Message(
        chat_id=chat_id,
        role=role,
        content=content,
        parent_id=parent_id,
        tool_calls=tool_calls,
        developer_metrics=developer_metrics
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message

  @staticmethod
  async def delete_chat(db: AsyncSession, chat_id: str, user_id: str) -> bool:
    chat = await ChatService.get_chat_by_id(db, chat_id, user_id)
    if not chat:
      return False
    await db.delete(chat)
    await db.commit()
    return True

  @staticmethod
  async def get_user_memories(db: AsyncSession, user_id: str) -> List[Dict[str, Any]]:
    result = await db.execute(
        select(Memory).where(Memory.user_id == user_id).order_by(desc(Memory.importance_score))
    )
    memories_list = result.scalars().all()
    return [
        {
            "id": m.id,
            "category": m.category,
            "content": m.content,
            "importance_score": m.importance_score,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in memories_list
    ]

  @staticmethod
  async def toggle_chat_share(db: AsyncSession, chat_id: str, user_id: str, is_shared: bool) -> Optional[Chat]:
    chat = await ChatService.get_chat_by_id(db, chat_id, user_id)
    if not chat:
      return None

    if is_shared:
      # Generate a static snapshot of the chat's current messages
      messages = await ChatService.get_chat_messages(db, chat_id)
      snapshot = []
      for m in messages:
        if m.role in ("system", "tool"):
          continue
        snapshot.append({
          "id": m.id,
          "role": m.role,
          "content": m.content,
          "created_at": m.created_at.isoformat() if m.created_at else None
        })

      shared_link = None
      if chat.share_id:
        res = await db.execute(select(SharedLink).where(SharedLink.id == chat.share_id))
        shared_link = res.scalar_one_or_none()

      if shared_link:
        shared_link.title = chat.title or "Shared Chat"
        shared_link.snapshot_messages = snapshot
      else:
        shared_link = SharedLink(
          chat_id=chat.id,
          title=chat.title or "Shared Chat",
          snapshot_messages=snapshot
        )
        db.add(shared_link)
      
      await db.flush()  # Ensures shared_link has an ID
      chat.is_shared = True
      chat.share_id = shared_link.id
    else:
      if chat.share_id:
        res = await db.execute(select(SharedLink).where(SharedLink.id == chat.share_id))
        shared_link = res.scalar_one_or_none()
        if shared_link:
          await db.delete(shared_link)
      chat.is_shared = False
      chat.share_id = None

    await db.commit()
    await db.refresh(chat)
    return chat

  @staticmethod
  async def get_shared_link_by_id(db: AsyncSession, share_id: str) -> Optional[SharedLink]:
    result = await db.execute(
        select(SharedLink).where(SharedLink.id == share_id)
    )
    return result.scalar_one_or_none()

