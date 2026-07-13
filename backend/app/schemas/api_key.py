from pydantic import BaseModel, ConfigDict
from datetime import datetime

class ApiKeyCreate(BaseModel):
    provider_name: str
    api_key: str

class ApiKeyOut(BaseModel):
    provider_name: str
    masked_key: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
