from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List, Optional

class ApiKeyCreate(BaseModel):
    provider_name: str
    api_key: str

class ApiKeyOut(BaseModel):
    provider_name: str
    masked_key: str
    # True when the key passed a live verification call to the provider's API
    is_verified: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ProviderOut(BaseModel):
    id: str
    status: str
    saved: bool
    verified: bool
    enabled: bool
    lastChecked: Optional[datetime] = None
    availableModels: List[str] = []
    lastError: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
