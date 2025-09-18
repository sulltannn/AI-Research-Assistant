from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END

from agents.planner import decide
from agents.retriever import retrieve_docs, web_search
from agents.summarizer import run_full_research
from agents.evaluator import evaluate_answer, answer_from_docs
from utils.article_utils import fetch_url_text


# ---- Define the workflow state (TypedDict so LangGraph preserves inputs) ----
class WorkflowState(TypedDict, total=False):
    # inputs
    mode: str                       # "chat" | "research"
    session_id: str
    query: str
    topic: str                      # optional alias for query
    urls: List[str]
    history: List[Any]

    # planning
    decision: Dict[str, Any]        # {'mode': 'local'|'quick_web'|'full_research', 'reason': str}
    local_docs: List[Any]
    retrieved_docs_preview: List[Any]

    # retrieval
    retrieved_docs: List[Any]       # LangChain Documents or similar
    web_results: List[Dict[str, Any]]

    # summarization outputs
    per_article: List[Dict[str, Any]]
    overall_summary: str

    # evaluation / final answer
    answer: str
    confidence: float
    evaluation: Dict[str, Any]
    sources: List[Dict[str, Optional[str]]]

    # control
    retry_count: int


def _normalize(s: WorkflowState) -> WorkflowState:
    """Ensure 'query' and 'mode' exist."""
    out: WorkflowState = dict(s)
    if not out.get("query"):
        out["query"] = out.get("topic", "") or ""
    if not out.get("mode"):
        out["mode"] = "chat"
    return out


def create_workflow():
    """
    Build a LangGraph workflow for Agentic RAG.
    Planner → Retriever → Summarizer → Evaluator (+ feedback loop)
    """
    graph = StateGraph(WorkflowState)
    MAX_FEEDBACK_RETRIES = 2

    # 1) PLANNER
    def planner_node(state: WorkflowState) -> WorkflowState:
        s = _normalize(state)
        mode = s["mode"]

        # Research mode: force full research path
        if mode == "research":
            return {"decision": {"mode": "full_research", "reason": "explicit research"}}

        # Chat mode: decide local vs quick_web based on local doc availability
        q = s["query"]
        sid = s.get("session_id", "")
        try:
            retrieved_docs = retrieve_docs(q, sid, k=3)
        except Exception as e:
            print(f"[planner_node] retrieve_docs error: {e}")
            retrieved_docs = []

        decision = decide(q, len(retrieved_docs or []))  # {'mode': 'local'|'quick_web', 'reason': ...}
        return {
            "decision": decision,
            "retrieved_docs_preview": retrieved_docs or []
        }

    graph.add_node("planner", planner_node)

    # 2) RETRIEVER
    def retriever_node(state: WorkflowState) -> WorkflowState:
        s = _normalize(state)
        decision_mode = (s.get("decision") or {}).get("mode", "local")
        q = s["query"]
        sid = s.get("session_id", "")

        # For research or quick_web → web search path
        if decision_mode in ("quick_web", "full_research"):
            # If research with explicit URLs, honor them (scrape directly)
            if decision_mode == "full_research" and s.get("urls"):
                hits: List[Dict[str, Any]] = []
                for u in s["urls"]:
                    content = fetch_url_text(u) or ""
                    if content:
                        hits.append({"title": "", "url": u, "content": content})
                return {"web_results": hits}

            # Otherwise do normal web search
            results = web_search(q) or []
            out: WorkflowState = {"web_results": results}

            # For quick_web in chat, also prep pseudo-docs so evaluator can reuse the same path
            if decision_mode == "quick_web" and results:
                from langchain.schema import Document
                docs = []
                for r in results:
                    content = r.get("content") or ""
                    if not content:
                        continue
                    meta = {
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "session_id": sid
                    }
                    docs.append(Document(page_content=content, metadata=meta))
                if docs:
                    out["retrieved_docs"] = docs
            return out

        # Local path for chat
        docs = s.get("retrieved_docs_preview")
        if docs is None:
            try:
                docs = retrieve_docs(q, sid)
            except Exception as e:
                print(f"[retriever_node] retrieve_docs error: {e}")
                docs = []
        return {"retrieved_docs": docs or []}

    graph.add_node("retriever", retriever_node)

    # 3) SUMMARIZER (only for full_research)
    def summarizer_node(state: WorkflowState) -> WorkflowState:
        s = _normalize(state)
        decision_mode = (s.get("decision") or {}).get("mode")
        if decision_mode == "full_research" and s.get("web_results"):
            res = run_full_research(s["query"], s.get("session_id", ""), s["web_results"])
            per_article = res.get("per_article", [])
            overall = res.get("overall")
            overall_text = overall.content if hasattr(overall, "content") else str(overall)
            return {
                "per_article": per_article,
                "overall_summary": overall_text
            }
        return {}

    graph.add_node("summarizer", summarizer_node)

    # 4) EVALUATOR (answer from docs; if poor, feedback to quick_web)
    def evaluator_node(state: WorkflowState) -> WorkflowState:
        s = _normalize(state)
        docs = s.get("retrieved_docs") or []
        if not docs:
            return {}

        chat_history = s.get("history", [])
        q = s["query"]

        answer_text = answer_from_docs(docs, q, chat_history)
        eval_res = evaluate_answer(answer_text, q)

        # Build sources list (doc_id may be None for web snippets)
        try:
            sources = [
                {
                    "doc_id": (getattr(d, "metadata", {}) or {}).get("doc_id"),
                    "url": (getattr(d, "metadata", {}) or {}).get("url"),
                }
                for d in docs
            ]
        except Exception:
            sources = []

        return {
            "answer": answer_text,
            "confidence": float(eval_res.get("confidence", 0.0)),
            "evaluation": eval_res,
            "sources": sources,
        }

    graph.add_node("evaluator", evaluator_node)

    # 5) FEEDBACK LOOP (flip to quick_web on low confidence)
    def feedback_node(state: WorkflowState) -> WorkflowState:
        retry = int(state.get("retry_count", 0)) + 1
        return {
            "retry_count": retry,
            "decision": {"mode": "quick_web", "reason": "low_confidence_retry"}
        }

    graph.add_node("feedback", feedback_node)

    # ---- EDGES ----
    graph.set_entry_point("planner")
    graph.add_edge("planner", "retriever")
    graph.add_edge("retriever", "summarizer")   # research path
    graph.add_edge("retriever", "evaluator")    # chat path
    graph.add_edge("feedback", "retriever")
    graph.add_edge("summarizer", END)

    # evaluator → END if ok, else feedback (with max retries)
    def should_end_from_evaluator(state: WorkflowState) -> bool:
        ok = (state.get("evaluation") or {}).get("ok", True)
        if ok:
            return True
        return int(state.get("retry_count", 0)) >= MAX_FEEDBACK_RETRIES

    graph.add_conditional_edges(
        "evaluator",
        should_end_from_evaluator,
        {True: END, False: "feedback"},
    )

    return graph.compile()
