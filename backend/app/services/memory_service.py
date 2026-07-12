from typing import List, Optional
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.memory import Memory

class MemoryService:
    @staticmethod
    async def get_user_memories(db: AsyncSession, user_id: str) -> List[Memory]:
        """
        Retrieves all semantic memories for a given user, ordered by importance score.
        """
        result = await db.execute(
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(desc(Memory.importance_score))
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_memory(
        db: AsyncSession,
        user_id: str,
        category: str,
        content: str,
        importance_score: int
    ) -> Memory:
        """
        Saves a new user semantic memory/fact.
        """
        mem = Memory(
            user_id=user_id,
            category=category,
            content=content,
            importance_score=importance_score
        )
        db.add(mem)
        await db.commit()
        await db.refresh(mem)
        return mem

    @staticmethod
    async def delete_memory(db: AsyncSession, memory_id: str, user_id: str) -> bool:
        """
        Deletes a user memory/fact.
        """
        result = await db.execute(
            select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
        )
        mem = result.scalar_one_or_none()
        if not mem:
            return False

        await db.delete(mem)
        await db.commit()
        return True

    @staticmethod
    async def extract_and_save_memories(
        user_id: str,
        chat_id: str,
        user_content: str,
        assistant_content: str
    ):
        """
        FastAPI Background Task to analyze a chat exchange, extract semantic memories,
        perform duplicate filtering, and save them.
        """
        import logging
        import json
        from app.core.database import AsyncSessionLocal
        from app.providers.gemini import GeminiProvider
        
        logger = logging.getLogger("app.services.memory_service")
        provider = GeminiProvider()
        
        memories_to_create = []

        if provider.is_mock:
            # 1. Rule-based simulated extraction for Mock Mode
            logger.info("Executing rule-based memory extraction in mock mode")
            import re
            user_content_lower = user_content.lower()

            # Rule 1: Name / personal info
            if "my name is" in user_content_lower:
                parts = re.split(r'(?i)my name is', user_content, 1)
                if len(parts) > 1:
                    # Stop at comma, period, 'and', or whitespace after the name
                    raw = parts[1].strip()
                    name_match = re.match(r'^([A-Za-z][A-Za-z\-\']{0,30}(?:\s[A-Za-z][A-Za-z\-\']{0,30})?)', raw)
                    if name_match:
                        name = name_match.group(1).strip(" .!,").title()
                        if len(name) < 50:
                            memories_to_create.append({
                                "category": "fact",
                                "content": f"User's name is {name}",
                                "importance_score": 9
                            })
            
            # Rule 2: Job / Role
            if "i work as a" in user_content_lower or "i am a" in user_content_lower:
                parts = re.split(r'(?i)i work as a|(?i)i am a', user_content, 1)
                if len(parts) > 1:
                    role = parts[1].split(".")[0].split("and")[0].strip(" .!,")
                    if len(role) < 100:
                        memories_to_create.append({
                            "category": "fact",
                            "content": f"Works as a {role}",
                            "importance_score": 8
                        })
            elif "i'm a" in user_content_lower:
                parts = re.split(r'(?i)i\'m a', user_content, 1)
                if len(parts) > 1:
                    role = parts[1].split(".")[0].split("and")[0].strip(" .!,")
                    if len(role) < 100:
                        memories_to_create.append({
                            "category": "fact",
                            "content": f"Works as a {role}",
                            "importance_score": 8
                        })

            # Rule 3: Preferences
            if "i prefer" in user_content_lower:
                parts = re.split(r'(?i)i prefer', user_content, 1)
                if len(parts) > 1:
                    pref = parts[1].split(".")[0].split("because")[0].strip(" .!,")
                    if len(pref) < 150:
                        memories_to_create.append({
                            "category": "preference",
                            "content": f"Prefers {pref}",
                            "importance_score": 5
                        })

            # Rule 4: Goals
            if "i want to" in user_content_lower:
                parts = re.split(r'(?i)i want to', user_content, 1)
                if len(parts) > 1:
                    goal = parts[1].split(".")[0].split("because")[0].strip(" .!,")
                    if len(goal) < 150:
                        memories_to_create.append({
                            "category": "goal",
                            "content": f"Wants to {goal}",
                            "importance_score": 6
                        })
            elif "my goal is to" in user_content_lower:
                parts = re.split(r'(?i)my goal is to', user_content, 1)
                if len(parts) > 1:
                    goal = parts[1].split(".")[0].strip(" .!,")
                    if len(goal) < 150:
                        memories_to_create.append({
                            "category": "goal",
                            "content": f"Goal is to {goal}",
                            "importance_score": 6
                        })

            # Rule 5: Topics
            if "interested in" in user_content_lower:
                parts = re.split(r'(?i)interested in', user_content, 1)
                if len(parts) > 1:
                    topic = parts[1].split(".")[0].strip(" .!,")
                    if len(topic) < 100:
                        memories_to_create.append({
                            "category": "topic",
                            "content": f"Interested in {topic}",
                            "importance_score": 4
                        })
        else:
            # 2. LLM-based extraction using Gemini API
            logger.info("Executing LLM-based memory extraction")
            system_instruction = (
                "You are an AI memory consolidation module. Your job is to extract user facts, preferences, goals, and interests from the conversation.\n"
                "Output ONLY a JSON list of objects, representing new memories to store. Each object must have:\n"
                "- 'category': 'fact' | 'preference' | 'goal' | 'topic'\n"
                "- 'content': string (concise, clear third-person statement, e.g. 'Prefers Python over JS')\n"
                "- 'importance_score': integer between 1 and 10\n"
                "If no new long-term facts/preferences are found, return an empty list []. Do not include explanation or markdown code block wrapper, output raw JSON."
            )
            
            conversation_text = f"User: {user_content}\nAssistant: {assistant_content}"
            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Analyze this exchange:\n{conversation_text}"}
            ]
            
            try:
                response = await provider.generate(messages, model="gemini-1.5-flash")
                raw_text = response.get("text", "").strip()
                
                # Strip markdown code blocks
                if raw_text.startswith("```"):
                    raw_text = raw_text.split("```", 1)[1]
                    if raw_text.startswith("json"):
                        raw_text = raw_text[4:]
                    if raw_text.endswith("```"):
                        raw_text = raw_text[:-3]
                    raw_text = raw_text.strip()
                
                if raw_text:
                    memories_to_create = json.loads(raw_text)
                    if not isinstance(memories_to_create, list):
                        memories_to_create = []
            except Exception as e:
                logger.error(f"Failed to generate or parse memories from LLM: {str(e)}")
                memories_to_create = []

        if memories_to_create:
            async with AsyncSessionLocal() as db:
                # Fetch existing memories
                existing_res = await db.execute(
                    select(Memory).where(Memory.user_id == user_id)
                )
                existing_contents = {m.content.lower().strip() for m in existing_res.scalars().all()}
                
                for m_data in memories_to_create:
                    content_cleaned = m_data.get("content", "").strip()
                    category = m_data.get("category", "fact")
                    importance = int(m_data.get("importance_score", 5))
                    
                    if not content_cleaned or category not in ["fact", "preference", "goal", "topic"]:
                        continue
                        
                    # Skip duplicate contents
                    if content_cleaned.lower().strip() in existing_contents:
                        logger.info(f"Deduplicated existing memory: {content_cleaned}")
                        continue
                        
                    db_mem = Memory(
                        user_id=user_id,
                        category=category,
                        content=content_cleaned,
                        importance_score=importance
                    )
                    db.add(db_mem)
                    logger.info(f"Saved new semantic memory: {content_cleaned} (Category: {category})")
                
                await db.commit()

