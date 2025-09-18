from pydantic import BaseModel, HttpUrl, EmailStr
from typing import List, Optional, Dict, Any
# ---------------- Pydantic models ----------------

# Research and Chat Models
class ArticleIn(BaseModel):
    url: HttpUrl
    text: Optional[str] = None
    doc_id: Optional[str] = None

class ResearchRequest(BaseModel):
    session_id: str
    topic: str
    urls: Optional[List[HttpUrl]] = None
    user_id: Optional[str] = None

class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_id: Optional[str] = None

# Auth models
class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: Optional[str] = "user"

class LoginRequest(BaseModel):
    username: str
    password: str

class GoogleAuthRequest(BaseModel):
    code: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MeResponse(BaseModel):
    id: int
    username: str
    email: Optional[EmailStr] = None
    role: str


# Forgot Password Models
class ForgotPasswordRequest(BaseModel):
    username_or_email: str


class VerifyOtpRequest(BaseModel):
    username_or_email: str
    otp: str


class ResetPasswordRequest(BaseModel):
    username_or_email: str
    otp: str
    new_password: str


    