from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class MemoryCreate(BaseModel):
    category: str = Field(..., description="Category of semantic memory: fact, preference, goal, topic")
    content: str = Field(..., description="The content text of the semantic memory")
    importance_score: int = Field(5, ge=1, le=10, description="Importance score from 1 to 10")

class MemoryOut(BaseModel):
    id: str
    user_id: str
    category: str
    content: str
    importance_score: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
