from datetime import datetime
from pydantic import BaseModel, ConfigDict

class DocumentOut(BaseModel):
    id: str
    user_id: str
    filename: str
    file_type: str
    storage_path: str
    size_bytes: int
    status: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)
