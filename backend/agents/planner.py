from typing import Dict
from config import TIME_SENSITIVE_KEYWORDS, RETRIEVAL_MIN_DOCS

def _contains_time_keyword(q: str) -> bool:
    ql = q.lower()
    return any(kw.strip().lower() in ql for kw in TIME_SENSITIVE_KEYWORDS)

def decide(query: str, retrieved_count: int) -> Dict[str, str]:
    """
    Decide path:
      - 'local' => use session Pinecone only
      - 'quick_web' => quick web search to answer chat
      - 'full_research' => used by /research endpoint only
    Returns a dict: {'mode': 'local'|'quick_web', 'reason': '...'}
    """
    if _contains_time_keyword(query):
        return {"mode": "quick_web", "reason": "time_sensitive"}
    if retrieved_count < RETRIEVAL_MIN_DOCS:
        return {"mode": "quick_web", "reason": "insufficient_local_docs"}
    return {"mode": "local", "reason": "sufficient_local_docs"}
