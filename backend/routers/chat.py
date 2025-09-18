from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Optional
import uuid

from config import MAX_HISTORY_MESSAGES
from db import upsert_chat, load_chat, list_chats
from pydantic_models import ResearchRequest, ChatRequest
from routers.auth import _get_current_user
from utils.sessions_store import sessions
router = APIRouter(tags=["chat"])

# In-memory session storage
#sessions = {}

# Global workflow instance
workflow = None

# Helper functions
def ensure_session(session_id: Optional[str], user_id: Optional[str] = None) -> str:
    if not session_id:
        sid = str(uuid.uuid4())
        sessions[sid] = {"user_id": user_id, "doc_ids": set(), "messages": []}
        return sid
    if session_id not in sessions:
        record = load_chat(session_id)
        if record:
            # Enforce ownership if user_id provided
            if user_id is not None and record.get("user_id") not in (None, "", user_id):
                raise HTTPException(status_code=403, detail="Forbidden: not your chat")
            sessions[session_id] = {
                "user_id": record.get("user_id"),
                "doc_ids": set(),
                "messages": record.get("messages", []),
            }
        else:
            sessions[session_id] = {"user_id": user_id, "doc_ids": set(), "messages": []}
    return session_id

def messages_to_pairs_for_lc(messages: List[Dict[str, str]]) -> List[tuple]:
    pairs = []
    pending_user = None
    for m in messages:
        if m["role"] == "user":
            pending_user = m["content"]
        elif m["role"] == "assistant" and pending_user is not None:
            pairs.append((pending_user, m["content"]))
            pending_user = None
    return pairs

def last_n_messages(session_id: str, n: int) -> List[Dict[str, str]]:
    msgs = sessions[session_id]["messages"]
    return msgs[-n:] if len(msgs) > n else msgs

def title_from_messages(messages: List[Dict[str, str]]) -> str:
    for m in messages:
        if m["role"] == "user":
            return (m["content"][:80] + "...") if len(m["content"]) > 80 else m["content"]
    return "Untitled Chat"

# Set workflow instance
def set_workflow(wf):
    global workflow
    workflow = wf

# Chat and Research endpoints
@router.post("/new_chat")
def new_chat(current = Depends(_get_current_user)):
    session_id = str(uuid.uuid4())
    sessions[session_id] = {"user_id": str(current["id"]), "doc_ids": set(), "messages": []}
    return {"session_id": session_id}

@router.get("/list_chats")
def list_chats_endpoint(current = Depends(_get_current_user), limit: int = 50, offset: int = 0):
    return {"chats": list_chats(user_id=str(current["id"]), limit=limit, offset=offset)}

@router.get("/load_chat/{session_id}")
def load_chat_endpoint(session_id: str, current = Depends(_get_current_user)):
    if session_id in sessions:
        # Enforce ownership for in-memory session
        owner = sessions[session_id].get("user_id")
        if owner and owner != str(current["id"]):
            raise HTTPException(status_code=403, detail="Forbidden: not your chat")
        return {"session_id": session_id, "messages": sessions[session_id]["messages"]}
    record = load_chat(session_id)
    if not record:
        raise HTTPException(status_code=404, detail="Chat not found")
    if record.get("user_id") and record.get("user_id") != str(current["id"]):
        raise HTTPException(status_code=403, detail="Forbidden: not your chat")
    sessions[session_id] = {
        "user_id": record.get("user_id"),
        "doc_ids": set(),
        "messages": record.get("messages", []),
    }
    return {"session_id": session_id, "messages": sessions[session_id]["messages"]}

@router.post("/research")
def research(req: ResearchRequest, current = Depends(_get_current_user)):
    sid = ensure_session(req.session_id, user_id=str(current["id"]))
    sessions[sid]["messages"].append({"role": "user", "content": f"New research request: {req.topic}"})
    if not workflow:
        raise HTTPException(status_code=500, detail="Workflow not initialized")

    # Run Agentic RAG workflow
    input_data = {
        "query": req.topic,
        "session_id": sid,
        "mode": "research",
        "urls": req.urls or []
    }
    result = workflow.invoke(input_data)

    per_article = result.get("per_article", [])
    overall_summary = result.get("overall_summary", "No sufficient content to summarize.")

    # Save assistant message for chat history
    lines = ["Per-article summaries:"]
    for i, s in enumerate(per_article, 1):
        lines.append(f"{i}. {s['summary']}\n(Source: {s['url']})")
    lines.append("\nOverall synthesis:\n" + overall_summary)
    assistant_block = "\n".join(lines)
    sessions[sid]["messages"].append({"role": "assistant", "content": assistant_block})

    return {"topic": req.topic, "per_article": per_article, "overall_summary": overall_summary}

@router.post("/chat")
def chat(req: ChatRequest, current = Depends(_get_current_user)):
    sid = ensure_session(req.session_id, user_id=str(current["id"]))
    sessions[sid]["messages"].append({"role": "user", "content": req.message})

    if not workflow:
        raise HTTPException(status_code=500, detail="Workflow not initialized")

    # Run Agentic RAG workflow
    input_data = {
        "query": req.message,
        "session_id": sid,
        "mode": "chat",
        "history": messages_to_pairs_for_lc(last_n_messages(sid, MAX_HISTORY_MESSAGES))
    }
    result = workflow.invoke(input_data)

    answer = result.get("answer", "I could not generate an answer.")
    sources = result.get("sources", [])

    # Save assistant message
    sessions[sid]["messages"].append({"role": "assistant", "content": answer})

    return {"session_id": sid, "answer": answer, "sources": sources}

@router.post("/end_chat/{session_id}")
def end_chat(session_id: str, current = Depends(_get_current_user)):
    if session_id not in sessions:
        record = load_chat(session_id)
        if record:
            if record.get("user_id") and record.get("user_id") != str(current["id"]):
                raise HTTPException(status_code=403, detail="Forbidden: not your chat")
            return {"message": "Chat already saved", "session_id": session_id, "title": record.get("title", "Untitled")}
        else:
            raise HTTPException(status_code=404, detail="Chat session not found")

    # Enforce ownership for in-memory session before saving
    owner = sessions[session_id].get("user_id")
    if owner and owner != str(current["id"]):
        raise HTTPException(status_code=403, detail="Forbidden: not your chat")
    msgs = sessions[session_id]["messages"]
    title = title_from_messages(msgs)
    upsert_chat(session_id=session_id, user_id=sessions[session_id].get("user_id") or str(current["id"]), title=title, messages=msgs)
    del sessions[session_id]
    return {"message": "Chat saved", "session_id": session_id, "title": title}

@router.post("/save_chat/{session_id}")
def save_chat(session_id: str, current = Depends(_get_current_user)):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Chat session not found")
    msgs = sessions[session_id]["messages"]
    title = title_from_messages(msgs)
    upsert_chat(session_id=session_id, user_id=sessions[session_id].get("user_id") or str(current["id"]), title=title, messages=msgs)
    return {"message": "Chat saved", "session_id": session_id, "title": title}