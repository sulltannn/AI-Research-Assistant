from fastapi import APIRouter, Depends, Header, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import secrets
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from jose import JWTError, jwt

from config import JWT_SECRET_KEY, JWT_ALGORITHM, SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, EMAIL_FROM
from db import (
    verify_user_password, create_user, check_username_available, 
    get_user_by_username, get_user_by_email, create_otp, verify_otp, 
    delete_otp, update_password,list_users as db_list_users, set_user_role
)
from utils.oauth_utils import exchange_code_for_token, get_user_info_from_token, create_or_get_user_from_google, get_google_auth_url
from pydantic_models import (
    SignupRequest, LoginRequest, GoogleAuthRequest, TokenResponse, 
    MeResponse, ForgotPasswordRequest, VerifyOtpRequest, ResetPasswordRequest
)

router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])

# Helper functions
def _create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=30)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def send_email(to_email: str, subject: str, body: str) -> bool:
    try:
        message = MIMEMultipart()
        message["From"] = EMAIL_FROM
        message["To"] = to_email
        message["Subject"] = subject
        message.attach(MIMEText(body, "html"))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
        return False

def send_otp(to_email: str, user_id: int):
    # Generate a 6-digit OTP
    otp = str(random.randint(100000, 999999))
    
    # Set expiration time (2 minutes from now)
    expires_at = (datetime.utcnow() + timedelta(minutes=2)).isoformat()
    
    # Store OTP in database
    create_otp(user_id, otp, expires_at)
    
    # Send OTP via email
    email_subject = "Password Reset Verification Code"
    email_body = f"""
    <html>
    <body>
        <h2>Password Reset Request</h2>
        <p>Hello,</p>
        <p>We received a request to reset your password. Please use the following verification code to complete the process:</p>
        <h3 style="background-color: #f0f0f0; padding: 10px; text-align: center; font-size: 24px;">{otp}</h3>
        <p>This code will expire in 2 minutes.</p>
        <p>If you did not request a password reset, please ignore this email.</p>
        <p>Thank you,<br>AI Research Assistant Team</p>
    </body>
    </html>
    """
    
    email_sent = send_email(to_email, email_subject, email_body)
    
    # For security reasons, don't return the actual OTP in production
    # But for testing purposes, we'll include it if email sending fails
    response = {"message": "OTP sent to your email", "expires_at": expires_at}
    if not email_sent:
        # Only include OTP in response if email sending failed (for testing)
        response["otp"] = otp
        logging.warning(f"Email sending failed, returning OTP in response for user ID {user_id}")
    
    return response

async def _get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split()[1]
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        sub = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role")
        uid = payload.get("uid")
        if sub is None or role is None or uid is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"id": uid, "username": sub, "email": email, "role": role}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def _require_admin(user = Depends(_get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# Auth endpoints
@router.post("/signup", response_model=MeResponse)
def signup(req: SignupRequest):
    if not check_username_available(req.username):
        raise HTTPException(status_code=400, detail="Username already exists")
    role = req.role if req.role in ("user", "admin") else "user"
    user = create_user(req.username, req.password, role, req.email)
    return {"id": user["id"], "username": user["username"], "email": user["email"], "role": user["role"]}

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    user = verify_user_password(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _create_access_token({"sub": user["username"], "email": user.get("email"), "role": user["role"], "uid": user["id"]})
    return {"access_token": token, "token_type": "bearer"}

@router.post("/google", response_model=TokenResponse)
def google_auth(req: GoogleAuthRequest):
    # Exchange code for token
    token_data = exchange_code_for_token(req.code)
    if not token_data:
        raise HTTPException(status_code=400, detail="Failed to exchange code for token")
    
    # Get user info from token
    user_info = get_user_info_from_token(token_data["access_token"])
    if not user_info:
        raise HTTPException(status_code=400, detail="Failed to get user info")
    
    # Create or get user
    user = create_or_get_user_from_google(user_info)
    
    # Create access token
    token = _create_access_token({
        "sub": user["username"], 
        "email": user.get("email"), 
        "role": user["role"], 
        "uid": user["id"]
    })
    return {"access_token": token, "token_type": "bearer"}

@router.get("/google/login")
def google_login():
    """Redirect to Google OAuth"""
    auth_url = get_google_auth_url()
    return {"auth_url": auth_url}

@router.get("/me", response_model=MeResponse)
def me(user = Depends(_get_current_user)):
    return {"id": user["id"], "username": user["username"], "email": user.get("email"), "role": user["role"]}

@router.get("/username_available")
def username_available(username: str):
    return {"available": check_username_available(username)}

# Forgot Password endpoints
@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    """
    Request password reset. Generates and sends OTP to user's email.
    """
    # Try to find user by username first
    user = get_user_by_username(req.username_or_email)
    # If not found, try to find by email
    if not user:
        user = get_user_by_email(req.username_or_email)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.get("email"):
        raise HTTPException(status_code=400, detail="User does not have an email address")
    
    return send_otp(user["email"], user["id"])

@router.post("/verify-otp")
def verify_otp_endpoint(req: VerifyOtpRequest):
    """
    Verify the OTP entered by the user.
    """
    # Try to find user by username first
    user = get_user_by_username(req.username_or_email)
    # If not found, try to find by email
    if not user:
        user = get_user_by_email(req.username_or_email)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify OTP
    if verify_otp(user["id"], req.otp):
        return {"message": "OTP verified successfully"}
    else:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

@router.post("/resend-otp")
def resend_otp(req: ForgotPasswordRequest):
    """
    Resend OTP to user's email. Always invalidates previous OTP and generates a new one.
    """
    # Try to find user by username first
    user = get_user_by_username(req.username_or_email)
    # If not found, try to find by email
    if not user:
        user = get_user_by_email(req.username_or_email)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not user.get("email"):
        raise HTTPException(status_code=400, detail="User does not have an email address")
    
    # Always delete any existing OTP before creating a new one
    # Note: The create_otp function already handles this, but we're being explicit here
    delete_otp(user["id"])
    
    return send_otp(user["email"], user["id"])

@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    """
    Reset user's password after OTP verification.
    """
    # Try to find user by username first
    user = get_user_by_username(req.username_or_email)
    # If not found, try to find by email
    if not user:
        user = get_user_by_email(req.username_or_email)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify OTP
    if not verify_otp(user["id"], req.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    # Update password
    update_password(user["id"], req.new_password)
    
    return {"message": "Password reset successfully"}

# Admin endpoints
@admin_router.get("/users")
def admin_list_users(_: Dict[str, Any] = Depends(_require_admin), limit: int = 100, offset: int = 0):
    return {"users": db_list_users(limit=limit, offset=offset)}

@admin_router.post("/set_role")
def admin_set_role(user_id: int, role: str, _: Dict[str, Any] = Depends(_require_admin)):
    if role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    set_user_role(user_id, role)
    return {"message": "Role updated"}