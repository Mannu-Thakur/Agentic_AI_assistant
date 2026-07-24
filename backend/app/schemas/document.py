from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class DocumentOut(BaseModel):
    id: str
    user_id: str
    chat_id: Optional[str] = None
    filename: str
    file_type: str
    storage_path: str
    size_bytes: int
    status: str
    error_message: Optional[str] = None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)
