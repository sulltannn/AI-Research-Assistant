import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", None)
PINECONE_ENV = os.getenv("PINECONE_ENV", "us-east-1")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "research-assistant")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")  # 1536-dim
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

# Conversation and search knobs
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "12"))
MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "8"))
MIN_ARTICLE_CHARS = int(os.getenv("MIN_ARTICLE_CHARS", "200"))

# Agent/planner knobs
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "5"))
RETRIEVAL_MIN_DOCS = int(os.getenv("RETRIEVAL_MIN_DOCS", "3"))
RETRIEVAL_SIM_THRESHOLD = float(os.getenv("RETRIEVAL_SIM_THRESHOLD", "0.35"))
CHAT_QUICK_SEARCH_RESULTS = int(os.getenv("CHAT_QUICK_SEARCH_RESULTS", "4"))

TIME_SENSITIVE_KEYWORDS = os.getenv(
    "TIME_SENSITIVE_KEYWORDS",
    "latest,breaking,news,today,this week,recent,update,updated,currently,now,2024,2025,2026"
).split(",")

# Use Tavily exclusively if True; otherwise DuckDuckGo fallback allowed
USE_TAVILY_ONLY = bool(int(os.getenv("USE_TAVILY_ONLY", "1")))

# JWT auth config
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

# Google OAuth config
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

# Email config
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@aireserachassistant.com")

# CORS config
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# SMTP config for email sending
SMTP_SERVER = EMAIL_HOST
SMTP_PORT = EMAIL_PORT
SMTP_USERNAME = EMAIL_USER
SMTP_PASSWORD = EMAIL_PASSWORD