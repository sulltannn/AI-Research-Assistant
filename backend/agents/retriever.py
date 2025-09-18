from typing import List, Dict
from rag_pipeline import vectorstore
from config import RETRIEVAL_K
from utils.tavily_utils import tavily_quick_answers, duckduckgo_fallback
from langchain.schema import Document

def retrieve_docs(query: str, session_id: str, k: int = RETRIEVAL_K) -> List[Document]:
    """Retrieve session-scoped documents from vector store; fail soft and return []."""
    try:
        retriever = vectorstore.as_retriever(search_kwargs={"filter": {"session_id": session_id}, "k": k})
        try:
            # Newer LangChain retrievers are Runnables
            return retriever.invoke(query)
        except Exception:
            # Older interface
            return retriever.get_relevant_documents(query)
    except Exception as e:
        print(f"[retrieve_docs] retrieval error: {e}")
        return []

def web_search(query: str, max_results: int = 4) -> List[Dict]:
    # try tavily first
    hits = tavily_quick_answers(query, max_results=max_results)
    if hits:
        return hits
    # fallback to DuckDuckGo if available
    return duckduckgo_fallback(query, max_results=max_results)


