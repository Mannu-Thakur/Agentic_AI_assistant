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
  def generate_short_descriptive_title(prompt: str) -> str:
    """
    Generates a short, clean, descriptive title (3-6 words, max 42 chars)
    from a user's initial prompt.
    """
    import re
    if not prompt or not prompt.strip():
      return "New Chat"

    clean_text = prompt.strip()
    if "[Attached File:" in clean_text:
      clean_text = clean_text.split("[Attached File:")[0].strip()

    if not clean_text:
      return "File Discussion"

    lines = [l.strip() for l in clean_text.splitlines() if l.strip()]
    first_line = lines[0] if lines else clean_text

    fluff_patterns = [
      r"^(can you\s+)?(please\s+)?(help me\s+)?(write|create|build|generate|code|make)\s+(a|an|the)\s+",
      r"^(can you\s+)?(please\s+)?(help me\s+)?(with|to|about)\s+",
      r"^(how\s+(do|can|to|i|we)\s+)",
      r"^(tell me|explain|what is|who is|where is|why is|how is)\s+(about\s+)?",
      r"^(i want to|i need to|i'd like to)\s+",
      r"^(please\s+)",
    ]

    processed = first_line
    for pat in fluff_patterns:
      processed = re.sub(pat, "", processed, flags=re.IGNORECASE).strip()

    processed = re.sub(r"[?.,!\"':;]+$", "", processed).strip()

    if len(processed) < 3:
      processed = re.sub(r"[?.,!\"':;]+$", "", first_line).strip()

    words = processed.split()
    if len(words) > 6:
      processed = " ".join(words[:6])

    if len(processed) > 42:
      truncated = processed[:42]
      if " " in truncated:
        processed = truncated.rsplit(" ", 1)[0]
      else:
        processed = truncated

    processed = re.sub(r"[^\w\s\-\&\+\#]", "", processed).strip()

    acronyms = {"api", "sql", "json", "csv", "ai", "llm", "pdf", "html", "css", "js", "ts", "ui", "ux", "db", "url", "http", "https", "rest", "rag", "ocr"}
    formatted_words = []
    for w in processed.split():
      if w.lower() in acronyms:
        formatted_words.append(w.upper())
      elif len(w) > 1 and w.isupper():
        formatted_words.append(w)
      else:
        formatted_words.append(w.capitalize())

    title = " ".join(formatted_words).strip()
    return title if title else "New Chat"

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
      images: Optional[List[Dict[str, Any]]] = None,
  ) -> Message:
    message = Message(
        chat_id=chat_id,
        role=role,
        content=content,
        parent_id=parent_id,
        tool_calls=tool_calls,
        developer_metrics=developer_metrics,
        images=images,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message

  @staticmethod
  async def delete_messages_after(
      db: AsyncSession, chat_id: str, parent_message_id: Optional[str]
  ) -> int:
    """Delete all messages that come after `parent_message_id`.

    Used by the edit and retry flows to remove orphaned messages from the DB
    before inserting the replacement user message.

    - parent_message_id = None  → delete ALL messages in the chat (editing the
                                   very first message).
    - parent_message_id = <id>  → delete every message whose created_at is
                                   strictly after the parent's created_at.
    """
    if parent_message_id is None:
      result = await db.execute(
          delete(Message).where(Message.chat_id == chat_id)
      )
    else:
      ref = await db.execute(
          select(Message).where(
              Message.id == parent_message_id,
              Message.chat_id == chat_id,
          )
      )
      ref_msg = ref.scalar_one_or_none()
      if not ref_msg:
        return 0
      result = await db.execute(
          delete(Message).where(
              Message.chat_id == chat_id,
              Message.created_at > ref_msg.created_at,
          )
      )
    await db.commit()
    return result.rowcount

  @staticmethod
  async def delete_single_message(
      db: AsyncSession, chat_id: str, message_id: str
  ) -> int:
    """Delete a specific message and any associated response that belongs to it."""
    res = await db.execute(
        select(Message).where(Message.id == message_id, Message.chat_id == chat_id)
    )
    target = res.scalar_one_or_none()
    if not target:
      return 0

    ids_to_delete = [target.id]

    # If deleting a user question, find its direct assistant answer(s)
    if target.role == "user":
      sub_res = await db.execute(
          select(Message).where(
              Message.chat_id == chat_id,
              Message.created_at >= target.created_at
          ).order_by(Message.created_at)
      )
      all_after = sub_res.scalars().all()
      for m in all_after:
        if m.id == target.id:
          continue
        if m.parent_id == target.id or m.role == "assistant":
          ids_to_delete.append(m.id)
        if m.role == "user" and m.id != target.id:
          break

    result = await db.execute(
        delete(Message).where(Message.id.in_(ids_to_delete))
    )
    await db.commit()
    return result.rowcount


  @staticmethod
  async def update_chat_title(
      db: AsyncSession, chat_id: str, user_id: str, title: str
  ) -> Optional[Chat]:
    """Update a chat's title (used by PATCH and auto-title on first message)."""
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    )
    chat = result.scalar_one_or_none()
    if not chat:
      return None
    chat.title = title[:100].strip() or "New Chat"
    await db.commit()
    await db.refresh(chat)
    return chat

  @staticmethod
  async def delete_chat(db: AsyncSession, chat_id: str, user_id: str) -> bool:
    chat = await ChatService.get_chat_by_id(db, chat_id, user_id)
    if not chat:
      return False
    await db.delete(chat)
    await db.commit()
    return True

  @staticmethod
  async def delete_all_chats(db: AsyncSession, user_id: str) -> int:
    chat_ids_subquery = select(Chat.id).where(Chat.user_id == user_id)
    await db.execute(delete(SharedLink).where(SharedLink.chat_id.in_(chat_ids_subquery)))
    await db.execute(delete(Message).where(Message.chat_id.in_(chat_ids_subquery)))
    result = await db.execute(delete(Chat).where(Chat.user_id == user_id))
    await db.commit()
    return result.rowcount

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
  async def toggle_chat_share(
    db: AsyncSession,
    chat_id: str,
    user_id: str,
    is_shared: bool,
    is_live: bool = False
  ) -> Optional[Chat]:
    chat = await ChatService.get_chat_by_id(db, chat_id, user_id)
    if not chat:
      return None

    if is_shared:
      # For static snapshot shares capture the current messages.
      # For live shares the viewer will fetch real-time messages, so snapshot stays empty.
      if not is_live:
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
      else:
        snapshot = []

      shared_link = None
      if chat.share_id:
        res = await db.execute(select(SharedLink).where(SharedLink.id == chat.share_id))
        shared_link = res.scalar_one_or_none()

      if shared_link:
        shared_link.title = chat.title or "Shared Chat"
        if not is_live:
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
      chat.is_live_share = is_live
    else:
      if chat.share_id:
        res = await db.execute(select(SharedLink).where(SharedLink.id == chat.share_id))
        shared_link = res.scalar_one_or_none()
        if shared_link:
          await db.delete(shared_link)
      chat.is_shared = False
      chat.share_id = None
      chat.is_live_share = False

    await db.commit()
    await db.refresh(chat)
    return chat

  @staticmethod
  async def get_shared_link_by_id(db: AsyncSession, share_id: str) -> Optional[SharedLink]:
    result = await db.execute(
        select(SharedLink).where(SharedLink.id == share_id)
    )
    return result.scalar_one_or_none()

