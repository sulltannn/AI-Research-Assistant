import requests
from typing import Optional, Dict, Any
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI
from db import get_user_by_email, create_user, check_username_available
import json

def get_google_auth_url() -> str:
    """Generate Google OAuth authorization URL"""
    google_auth_url = (
        "https://accounts.google.com/o/oauth2/auth?"
        "response_type=code&"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={GOOGLE_REDIRECT_URI}&"
        "scope=openid%20email%20profile&"
        "access_type=offline"
    )
    return google_auth_url

def exchange_code_for_token(code: str) -> Optional[Dict[str, Any]]:
    """Exchange authorization code for access token"""
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    
    response = requests.post(token_url, data=data)
    if response.status_code == 200:
        return response.json()
    return None

def get_user_info_from_token(access_token: str) -> Optional[Dict[str, Any]]:
    """Get user info from Google access token"""
    user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    response = requests.get(user_info_url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

def create_or_get_user_from_google(user_info: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new user or get existing user from Google user info"""
    email = user_info.get("email")
    name = user_info.get("name", email.split("@")[0] if email else "user")
    
    # Check if user already exists
    existing_user = get_user_by_email(email)
    if existing_user:
        return existing_user
    
    # Generate a unique username
    base_username = email.split("@")[0] if email else name.lower().replace(" ", "_")
    username = base_username
    counter = 1
    
    # Ensure username is unique
    while not check_username_available(username):
        username = f"{base_username}_{counter}"
        counter += 1
    
    # Create new user with a random password (not used for Google login)
    import secrets
    random_password = secrets.token_urlsafe(16)
    new_user = create_user(
        username=username,
        password=random_password,
        role="user",
        email=email
    )
    
    return new_user