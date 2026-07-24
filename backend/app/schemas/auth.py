from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    role: str = "user"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UserPreferenceOut(BaseModel):
    default_model: str
    theme: str
    developer_mode: bool
    system_prompt_override: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
