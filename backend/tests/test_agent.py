import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.agent.graph import agent_graph
from app.services.chat_service import ChatService

def test_agent_graph_compilation():
  """
  Verify that the LangGraph StateGraph compiles without errors.
  """
  assert agent_graph is not None
  # Ensure nodes and entrypoint are registered
  assert "retrieve_context" in agent_graph.nodes
  assert "generate_response" in agent_graph.nodes

@pytest.mark.anyio
async def test_chat_service_operations(db_session: AsyncSession):
  """
  Verify database operations for chat threads and messages using mock user.
  """
  mock_user_id = "test-user-uuid"
  
  # Create Chat Session
  chat = await ChatService.create_chat(db_session, mock_user_id, "Test Thread")
  assert chat.id is not None
  assert chat.title == "Test Thread"
  assert chat.user_id == mock_user_id

  # Save Messages
  msg_user = await ChatService.save_message(
      db=db_session,
      chat_id=chat.id,
      role="user",
      content="Hi Assistant!"
  )
  assert msg_user.id is not None
  assert msg_user.role == "user"
  assert msg_user.content == "Hi Assistant!"
  msg_assistant = await ChatService.save_message(
      db=db_session,
      chat_id=chat.id,
      role="assistant",
      content="Hello Developer!",
      parent_id=msg_user.id,
      developer_metrics={"model_used": "mock-model", "latency_ms": 100, "tokens_input": 5, "tokens_output": 5, "cost_estimate": 0.0, "confidence_score": 1.0, "memory_hits": 0}
  )
  assert msg_assistant.id is not None
  assert msg_assistant.parent_id == msg_user.id
  assert msg_assistant.developer_metrics["model_used"] == "mock-model"

  # Retrieve Messages
  history = await ChatService.get_chat_messages(db_session, chat.id)
  assert len(history) == 2
  assert history[0].role == "user"
  assert history[1].role == "assistant"

  # Delete Chat Session
  deleted = await ChatService.delete_chat(db_session, chat.id, mock_user_id)
  assert deleted is True

  # Verify deletion cascading
  history_after_delete = await ChatService.get_chat_messages(db_session, chat.id)
  assert len(history_after_delete) == 0

@pytest.mark.anyio
async def test_memory_auto_extraction(db_session: AsyncSession):
  """
  Verify rule-based automatic memory extraction and saving to database.
  The service uses its own AsyncSessionLocal internally, so we verify
  via that same session factory after the extraction runs.
  """
  from app.services.memory_service import MemoryService
  from app.core.database import AsyncSessionLocal
  from app.models.memory import Memory
  from sqlalchemy import select, delete
  
  mock_user_id = "test-memory-extraction-uuid"
  mock_chat_id = "mock-chat-id"

  # Clean up any stale test memories
  async with AsyncSessionLocal() as db:
      await db.execute(delete(Memory).where(Memory.user_id == mock_user_id))
      await db.commit()

  # Trigger auto-extraction for name and preference
  await MemoryService.extract_and_save_memories(
      user_id=mock_user_id,
      chat_id=mock_chat_id,
      user_content="My name is Mannu and I prefer Python for backend scripting.",
      assistant_content="Hello Mannu! Python is indeed an excellent choice for scripting."
  )

  # Retrieve memories using same session factory the service uses
  async with AsyncSessionLocal() as db:
      result = await db.execute(
          select(Memory)
          .where(Memory.user_id == mock_user_id)
          .order_by(Memory.importance_score.desc())
      )
      memories = result.scalars().all()

  # Assert memories were created and mapped correctly
  assert len(memories) == 2, f"Expected 2 memories but found {len(memories)}: {[m.content for m in memories]}"
  
  # Check name fact
  name_mem = next((m for m in memories if m.category == "fact"), None)
  assert name_mem is not None, "Expected a 'fact' category memory"
  assert "Mannu" in name_mem.content
  assert name_mem.importance_score == 9

  # Check preference
  pref_mem = next((m for m in memories if m.category == "preference"), None)
  assert pref_mem is not None, "Expected a 'preference' category memory"
  assert "python" in pref_mem.content.lower()
  assert pref_mem.importance_score == 5

  # Cleanup
  async with AsyncSessionLocal() as db:
      await db.execute(delete(Memory).where(Memory.user_id == mock_user_id))
      await db.commit()


