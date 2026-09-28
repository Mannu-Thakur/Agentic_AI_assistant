from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import List, Optional

class ApiKeyCreate(BaseModel):
    provider_name: str
    api_key: str

    @field_validator('api_key')
    @classmethod
    def validate_key(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 8:
            raise ValueError('API key appears too short (minimum 8 characters)')
        if len(v) > 512:
            raise ValueError('API key too long (maximum 512 characters)')
        return v

    @field_validator('provider_name')
    @classmethod
    def validate_provider(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Provider name cannot be empty')
        if len(v) > 64:
            raise ValueError('Provider name too long')
        return v

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
