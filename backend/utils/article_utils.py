import hashlib
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from rag_pipeline import llm, vectorstore
from config import MIN_ARTICLE_CHARS
from db import insert_chunk_record, chunk_exists_for_session
from utils.sessions_store import sessions
import re

# chunker settings
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=200,
    separators=["\n\n", "\n", ". ", " ", ""]
)

_WHITESPACE_RE = re.compile(r"\s+")

def stable_doc_id(url: str, title: str = "") -> str:
    base = (url or "") + "::" + (title or "")
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]

def _normalize_text_for_hash(t: str) -> str:
    return _WHITESPACE_RE.sub(" ", t.strip())

def _chunk_id_from_content(chunk_text: str, doc_id: str, position: int) -> str:
    base = _normalize_text_for_hash(chunk_text) + "::" + (doc_id or "") + "::" + str(position)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]

def fetch_url_text(url: str, min_paragraph_len: int = 40) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"}
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "noscript", "header", "footer", "form", "svg"]):
            tag.extract()
        paragraphs = []
        for p in soup.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            if text and len(text) >= min_paragraph_len:
                paragraphs.append(text)
        content = "\n\n".join(paragraphs)
        if not content:
            article_tag = soup.find("article")
            if article_tag:
                content = article_tag.get_text(separator="\n", strip=True)
        return content or ""
    except Exception as e:
        print(f"[fetch_url_text] Error fetching {url}: {e}")
        return ""


    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(topic, max_results=max_results):
                href = r.get("href") or r.get("url") or r.get("link")
                title = r.get("title") or ""
                if href and href.startswith("http"):
                    results.append({"title": title, "url": href})
                    if len(results) >= max_results:
                        break
        return results
    except Exception:
        try:
            q = topic.replace(" ", "+")
            import requests
            from bs4 import BeautifulSoup
            search_url = f"https://duckduckgo.com/html/?q={q}"
            r = requests.get(search_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "lxml")
            links = []
            for a in soup.select("a.result__a"):
                href = a.get("href")
                title = a.get_text(strip=True)
                if href and href.startswith("http"):
                    links.append({"title": title, "url": href})
                if len(links) >= max_results:
                    break
            return links
        except Exception as e:
            print(f"[duckduckgo_search] fallback failed: {e}")
            return []

def summarize_article(article_text: str, url: str, session_id: str, doc_id: Optional[str] = None) -> str:
    """
    Summarize an article, chunk and upsert with chunk-level dedupe.
    Also updates sessions[session_id]['chunk_ids'] in-memory immediately after insertion.
    """
    if not article_text or len(article_text.strip()) < MIN_ARTICLE_CHARS:
        return "Skipped (insufficient content)."

    doc_id = doc_id or stable_doc_id(url)

    prompt = f"""
Summarize this article and generate a proper citation object (title, authors if available, venue, year, url).
If any field is unknown, use null. Always include the source URL exactly as provided.

Article URL: {url}

Article text:
{article_text}
"""
    try:
        summary = llm.invoke(prompt)
    except Exception as e:
        print(f"[summarize_article] LLM error: {e}")
        summary = "Summary generation failed."

    chunks = text_splitter.split_text(article_text)
    docs_to_add = []
    added_chunk_ids = []

    for idx, chunk in enumerate(chunks):
        chunk_id = _chunk_id_from_content(chunk, doc_id, idx)

        # in-memory check first (fast)
        if session_id in sessions and chunk_id in sessions[session_id].get("chunk_ids", set()):
            continue

        # persistent DB check (session-scoped)
        try:
            if chunk_exists_for_session(chunk_id, session_id):
                # keep in-memory consistent
                if session_id in sessions:
                    sessions[session_id].setdefault("chunk_ids", set()).add(chunk_id)
                continue
        except Exception as e:
            print(f"[summarize_article] chunk_exists_for_session check error: {e}")
            # fallback to attempt upsert (defensive)

        meta = {
            "session_id": session_id,
            "doc_id": doc_id,
            "url": url,
            "position": idx,
            "doc_type": "article_chunk",
            "chunk_id": chunk_id
        }
        docs_to_add.append(Document(page_content=chunk, metadata=meta))
        added_chunk_ids.append({"chunk_id": chunk_id, "position": idx})

    if docs_to_add:
        try:
            vectorstore.add_documents(docs_to_add)
            for c in added_chunk_ids:
                insert_chunk_record(c["chunk_id"], doc_id, session_id, url, c["position"])
                # update in-memory immediately
                if session_id in sessions:
                    sessions[session_id].setdefault("chunk_ids", set()).add(c["chunk_id"])
        except Exception as e:
            print(f"[summarize_article] vectorstore.add_documents error: {e}")

    return summary
