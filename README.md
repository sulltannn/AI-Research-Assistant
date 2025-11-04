## AI Research Assistant — Backend

FastAPI backend for an agentic RAG-powered research/chat assistant. Provides authentication (JWT + optional Google OAuth), chat session management with SQLite persistence, and a LangGraph workflow that plans, retrieves, summarizes, evaluates, and answers user queries.

### Tech Stack
- **API**: FastAPI
- **App Server**: Uvicorn
- **AI/Orchestration**: LangChain, LangGraph, OpenAI
- **Search/RAG**: Pinecone (optional), DuckDuckGo Search, Tavily (optional)
- **DB**: SQLite (`chats.sqlite3`)
- **Auth**: JWT, Google OAuth (optional)

### Directory Layout
```
backend/
  main.py                 # FastAPI app factory and router wiring
  workflow.py             # LangGraph workflow (planner → retriever → summarizer → evaluator)
  rag_pipeline.py         # RAG helpers (if used by agents)
  config.py               # Env-driven configuration
  db.py                   # SQLite primitives (users, chats, chunks, OTP)
  pydantic_models.py      # Request/response schemas
  routers/
    auth.py               # Signup/login, Google OAuth, password reset, admin
    chat.py               # New chat, list/load/save, research, chat
  agents/                 # Planner / Retriever / Summarizer / Evaluator nodes
  utils/                  # Article fetching, OAuth helpers, session store, etc.
  chats.sqlite3           # SQLite database (created on first run)
```

### Prerequisites
- Python 3.11+ (3.12 supported)
- An OpenAI API key
- Pinecone + index for vector search
- Tavily API key for web search (or fallback to DuckDuckGo)

### Setup (Windows PowerShell)
```powershell
# From the repository root
cd backend

# (Optional) Create and activate a virtual environment
python -m venv .venv
. .venv\Scripts\Activate.ps1

# Install dependencies from project root requirements
pip install -r ..\requirements.txt

# Copy environment template (or create your own .env)
ni .env -ItemType File -Force
notepad .env
```

### Environment Variables (.env)
Set in `backend/.env` (all are strings unless noted):

- OPENAI_API_KEY: OpenAI API key.
- PINECONE_API_KEY: Pinecone API key (optional if you don’t use Pinecone).
- PINECONE_ENV: Pinecone environment. Default: `us-east-1`.
- PINECONE_INDEX: Pinecone index name. Default: `research-assistant`.
- EMBEDDING_MODEL: Embedding model. Default: `text-embedding-3-small`.
- EMBEDDING_DIMENSION: Embedding dimension (int). Default: `1536`.
- MAX_HISTORY_MESSAGES: Chat history window (int). Default: `12`.
- MAX_SEARCH_RESULTS: Web results cap (int). Default: `8`.
- MIN_ARTICLE_CHARS: Minimum chars to treat article as valid (int). Default: `200`.
- RETRIEVAL_K: Top-K retrieval (int). Default: `5`.
- RETRIEVAL_MIN_DOCS: Minimum local docs (int). Default: `3`.
- RETRIEVAL_SIM_THRESHOLD: Similarity threshold (float). Default: `0.35`.
- CHAT_QUICK_SEARCH_RESULTS: Quick web results (int). Default: `4`.
- TIME_SENSITIVE_KEYWORDS: Comma-separated keywords to trigger web mode.
- USE_TAVILY_ONLY: Use Tavily only (0/1). Default: `1`.
- JWT_SECRET_KEY: JWT HMAC secret. Default is dev-only placeholder.
- JWT_ALGORITHM: JWT algorithm. Default: `HS256`.
- JWT_EXPIRE_MINUTES: JWT lifetime (int). Default: `60`.
- GOOGLE_CLIENT_ID: Google OAuth client id (optional).
- GOOGLE_CLIENT_SECRET: Google OAuth client secret (optional).
- GOOGLE_REDIRECT_URI: Google OAuth redirect URI (optional).
- EMAIL_HOST: SMTP host. Default: `localhost`.
- EMAIL_PORT: SMTP port (int). Default: `587`.
- EMAIL_USER: SMTP username.
- EMAIL_PASSWORD: SMTP password.
- EMAIL_FROM: From address. Default: `noreply@aireserachassistant.com`.
- CORS_ORIGINS: Comma-separated allowed origins. Default: `*`.

Example minimal `.env` for local dev:
```ini
OPENAI_API_KEY=sk-...
JWT_SECRET_KEY=change-me-in-prod
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# Optional search providers
TAVILY_API_KEY=
USE_TAVILY_ONLY=0

# Optional Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:5173/google/callback

# Optional SMTP for password reset
EMAIL_HOST=localhost
EMAIL_PORT=587
EMAIL_USER=
EMAIL_PASSWORD=
EMAIL_FROM=noreply@aireserachassistant.com
```

### Running the API (Dev)
```powershell
# From backend directory (with venv activated)
uvicorn main:app --reload --port 8000
```

- Health: `GET http://localhost:8000/health`
- Root: `GET http://localhost:8000/`

On first boot the app initializes `backend/chats.sqlite3` (or `chats.sqlite3` at repo root depending on working directory). Keep your working directory consistent.

### Authentication
- Username/password with JWT
- Optional Google OAuth (authorization code flow)
- Password reset via email + OTP (2 minutes validity)

Include the JWT as `Authorization: Bearer <token>` on protected endpoints.

### API Overview

Auth (`/auth`):
- `POST /auth/signup` → Create user. Body: `{ username, email, password, role? }`
- `POST /auth/login` → JWT. Body: `{ username, password }`
- `GET /auth/me` → Current user.
- `GET /auth/username_available?username=...`
- `GET /auth/google/login` → Returns Google auth URL.
- `POST /auth/google` → Exchanges `code` for JWT. Body: `{ code }`
- `POST /auth/forgot-password` → Sends OTP to user email. Body: `{ username_or_email }`
- `POST /auth/verify-otp` → Verify OTP. Body: `{ username_or_email, otp }`
- `POST /auth/resend-otp` → Reissue OTP. Body: `{ username_or_email }`
- `POST /auth/reset-password` → Reset with OTP. Body: `{ username_or_email, otp, new_password }`

Admin (`/admin`) — requires `role=admin`:
- `GET /admin/users?limit=&offset=` → List users
- `POST /admin/set_role?user_id=&role=` → Set role (`user|admin`)

Chat/Research:
- `POST /new_chat` → Start a chat. Returns `{ session_id }` (auth required)
- `GET /list_chats?limit=&offset=` → Paginated list for current user
- `GET /load_chat/{session_id}` → Load messages into memory
- `POST /research` → Long-form research synthesis
  - Body: `{ session_id, topic, urls? }`
  - Returns: `{ topic, per_article, overall_summary }`
- `POST /chat` → Conversational answer with sources
  - Body: `{ session_id, message }`
  - Returns: `{ session_id, answer, sources }`
- `POST /end_chat/{session_id}` → Persist and close chat
- `POST /save_chat/{session_id}` → Persist without closing

Notes:
- Most chat endpoints require auth (`Authorization: Bearer ...`).
- Sessions are tracked in-memory during a run and persisted to SQLite via `/save_chat` or `/end_chat`.

### Data Model (SQLite)
- `users` — basic auth and role management
- `chats` — chat transcripts with titles and timestamps
- `chunks` — per-session content/chunk references for provenance
- `otps` — password reset OTPs with expiry

DB is created automatically by `init_db()` during app startup.

### Workflow (High-Level)
1) Planner decides between local context vs. web search.
2) Retriever gathers either session-local docs or web results (DuckDuckGo/Tavily, or explicit URLs in research mode).
3) Summarizer synthesizes per-URL and overall insights (research mode).
4) Evaluator produces an answer, estimates confidence, and attaches sources.
5) Feedback loop may trigger a quick web search if confidence is low.

### Deployment
- Set strong `JWT_SECRET_KEY` and restrict `CORS_ORIGINS`.
- Provision secrets via platform env vars (no `.env` in production repos).
- Persist the SQLite file (`chats.sqlite3`) or switch to a managed DB.
- Run with a production server (e.g., `uvicorn` behind Nginx or a process manager).



