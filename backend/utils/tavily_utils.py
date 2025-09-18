from typing import List, Dict
from config import TAVILY_API_KEY, MAX_SEARCH_RESULTS, USE_TAVILY_ONLY

# Tavily is optional; wrap safely if not configured
try:
    from tavily import TavilyClient
    _tavily = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None
except Exception:
    _tavily = None

def tavily_quick_answers(query: str, max_results: int = 8) -> List[Dict]:
    if not _tavily:
        return []
    resp = _tavily.search(query=query, search_depth="advanced", max_results=max_results)
    items = []
    for r in resp.get("results", []):
        items.append({"title": r.get("title") or "", "url": r.get("url") or "", "content": r.get("content") or ""})
    return items


def duckduckgo_fallback(query: str, max_results: int = 8) -> List[Dict]:
    """
    Only used when USE_TAVILY_ONLY is False. Returns list of dicts {title, url}.
    """
    if USE_TAVILY_ONLY:
        return []
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                href = r.get("href") or r.get("url") or r.get("link")
                title = r.get("title") or ""
                if href and href.startswith("http"):
                    results.append({"title": title, "url": href})
                    if len(results) >= max_results:
                        break
        return results
    except Exception:
        # HTML fallback scraping as last resort
        try:
            import requests
            from bs4 import BeautifulSoup
            q = query.replace(" ", "+")
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
        except Exception:
            return []
