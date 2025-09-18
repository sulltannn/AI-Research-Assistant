from typing import List, Dict
from rag_pipeline import generate_overall_summary
from utils.article_utils import summarize_article, stable_doc_id

def run_full_research(topic: str, session_id: str, hits: List[Dict]) -> Dict:
    """
    hits: list of {title, url, content}
    For each hit: compute doc_id, call summarize_article (chunk + upsert non-duplicates).
    Then call generate_overall_summary.
    """
    per_article = []
    for h in hits:
        url = h.get("url")
        title = h.get("title") or ""
        content = h.get("content") or ""
        if not url or not content:
            continue
        doc_id = stable_doc_id(url, title)
        summary = summarize_article(content, url, session_id, doc_id)
        per_article.append({"doc_id": doc_id, "url": url, "summary": summary})
    overall = generate_overall_summary(topic, session_id, [p["summary"] for p in per_article]) if per_article else "No sufficient content to summarize."
    return {"per_article": per_article, "overall": overall}
