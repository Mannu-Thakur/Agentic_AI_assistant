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
    default_model: Optional[str] = None
    theme: str
    developer_mode: bool
    system_prompt_override: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    def validate_password(self) -> None:
        if len(self.new_password) < 8:
            raise ValueError("Password must be at least 8 characters long")
