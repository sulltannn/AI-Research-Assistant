from rag_pipeline import llm
import re, json
from typing import List
from langchain.schema import Document


def answer_from_docs(docs: List[Document], question: str, chat_history: List[tuple] = None) -> str:
	"""Compose a conversational answer from retrieved documents using the RAG pipeline."""
	from rag_pipeline import get_conversational_chain
	
	# Get the conversational chain for the session
	session_id = docs[0].metadata.get("session_id") if docs else None
	if not session_id:
		# Fallback to simple prompt if no session context
		context = "\n\n".join([d.page_content for d in docs[:6]])
		prompt = f"""
You are a helpful research assistant. Using ONLY the context below, answer the user's question concisely. If unsure, say you don't know.

Question:
{question}

Context:
{context}
"""
		resp = llm.invoke(prompt)
		return resp.content if hasattr(resp, "content") else str(resp)
	
	# Use the conversational RAG chain with chat history
	chain = get_conversational_chain(session_id)
	chat_history = chat_history or []
	
	result = chain({
		"question": question,
		"chat_history": chat_history,
		"context": docs
	})
	
	return result.get("answer", "I could not generate an answer.")


def evaluate_answer(answer: str, question: str, short_context: str = "") -> dict:
    """
    Self-critique using the LLM. Returns dict with keys:
      - 'ok' (bool)
      - 'confidence' (0..1)
      - 'notes' (string)
    """
    prompt = f"""
You are an evaluator. Given the user's question and the draft answer, assess whether the answer is complete and supported by the provided context.
Question:
{question}

Draft Answer:
{answer}

Context (if any):
{short_context}

Respond in JSON with keys:
- ok: true|false
- confidence: a number between 0 and 1
- notes: short note on what might be missing (one sentence).
"""
    try:
        resp = llm.invoke(prompt)
        text = resp.content if hasattr(resp, "content") else str(resp)
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            parsed = json.loads(m.group(0))
            ok = parsed.get("ok", False)
            confidence = float(parsed.get("confidence", 0.0))
            notes = parsed.get("notes", "")
            return {"ok": bool(ok), "confidence": confidence, "notes": notes}
    except Exception:
        pass

    # fallback heuristic
    lower = (answer or "").lower()
    ok = "yes" in lower or "true" in lower or "i'm confident" in lower
    confidence = 0.6 if ok else 0.2
    return {"ok": ok, "confidence": confidence, "notes": "Could not parse LLM JSON; used heuristic."}
