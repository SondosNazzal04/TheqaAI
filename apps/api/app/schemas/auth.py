# pyrefly: ignore [missing-import]
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from uuid import UUID

class RegisterRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: str = Field(..., min_length=8)
    full_name: str
    account_type: str = Field(..., pattern="^(individual|merchant)$")

class LoginRequest(BaseModel):
    email_or_phone: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: Optional[EmailStr] = None
    phone_e164: Optional[str] = None
    status: str
    locale: str

class OrgResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    type: str
    name: str
    slug: Optional[str] = None
    status: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"

class RegisterResponse(BaseModel):
    user: UserResponse
    org: OrgResponse
    access_token: str
    refresh_token: str

class MeResponse(BaseModel):
    user: UserResponse
    orgs: list[OrgResponse]
