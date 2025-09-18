from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from config import CORS_ORIGINS
from workflow import create_workflow
from routers import auth, chat
from db import init_db

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize database
init_db()

# Create workflow instance
workflow = create_workflow()
chat.set_workflow(workflow)

# Create FastAPI app
app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(auth.admin_router)
app.include_router(chat.router)

# Root endpoint
@app.get("/")
def read_root():
    return {"message": "AI Research Assistant API"}

# Health endpoint
@app.get("/health")
def health():
    return {"status": "ok", "workflow_ready": bool(workflow)}
