"""
app/services/web_search.py — Unified multi-provider web search service.

Provider waterfall (configurable via WEB_SEARCH_PROVIDER_ORDER):
  1. Tavily    — AI-curated, highest quality (tavily-python SDK)
  2. SerpAPI   — Real Google results (google-search-results SDK)
  3. Exa AI    — Neural semantic search (exa-py SDK)
  4. DuckDuckGo— Free, no key needed (duckduckgo-search SDK)

After fetching, results are ranked by BM25 relevance against the query
so the most relevant snippets surface first.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.cache_service import web_search_cache

logger = logging.getLogger("app.services.web_search")


# ─────────────────────────────────────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    title:     str
    url:       str
    snippet:   str
    source:    str          # "tavily" | "serpapi" | "exa" | "duckduckgo"
    score:     float = 0.0  # BM25 relevance score (set after ranking)
    published: Optional[str] = None   # ISO date string if available
    raw:       Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
#  BM25 ranking (no external library — mirrors vector_store.py pattern)
# ─────────────────────────────────────────────────────────────────────────────

def _bm25_score(query: str, texts: List[str], k1: float = 1.5, b: float = 0.75) -> List[float]:
    """Return a BM25 relevance score for each text w.r.t. the query."""
    query_terms = re.findall(r"\w+", query.lower())
    if not query_terms:
        return [0.0] * len(texts)

    tokenized = [re.findall(r"\w+", t.lower()) for t in texts]
    doc_lengths = [len(tok) for tok in tokenized]
    avg_dl = sum(doc_lengths) / max(len(doc_lengths), 1)
    N = len(texts)

    df: Dict[str, int] = defaultdict(int)
    for tok_list in tokenized:
        for term in set(tok_list):
            df[term] += 1

    scores: List[float] = []
    for i, tok_list in enumerate(tokenized):
        tf_map: Dict[str, int] = defaultdict(int)
        for t in tok_list:
            tf_map[t] += 1

        score = 0.0
        for term in query_terms:
            tf  = tf_map.get(term, 0)
            idf = math.log((N - df[term] + 0.5) / (df[term] + 0.5) + 1)
            dl  = doc_lengths[i]
            tf_norm = tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / max(avg_dl, 1)))
            score += idf * tf_norm
        scores.append(score)

    return scores


def rank_results(query: str, results: List[SearchResult]) -> List[SearchResult]:
    """Rank search results by BM25 relevance of (title + snippet) vs query."""
    if not results:
        return results

    texts = [f"{r.title} {r.snippet}" for r in results]
    raw_scores = _bm25_score(query, texts)
    max_score = max(raw_scores) if raw_scores else 1.0

    for result, raw_score in zip(results, raw_scores):
        # Normalize to 0.0–1.0
        result.score = round(raw_score / max(max_score, 1e-9), 4)

    return sorted(results, key=lambda r: r.score, reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Provider: Tavily
# ─────────────────────────────────────────────────────────────────────────────

async def search_tavily(query: str, api_key: str, max_results: int = 8) -> List[SearchResult]:
    """Search using Tavily API (SDK or direct HTTP REST call)."""
    try:
        from tavily import TavilyClient
        def _sync_search():
            client = TavilyClient(api_key=api_key)
            response = client.search(
                query=query,
                max_results=max_results,
                search_depth="basic",
                include_answer=False,
            )
            results = []
            for r in response.get("results", []):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", r.get("snippet", "")),
                    source="tavily",
                    published=r.get("published_date"),
                    raw=r,
                ))
            return results

        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(loop.run_in_executor(None, _sync_search), timeout=8.0)
    except (ImportError, ModuleNotFoundError, Exception) as exc:
        logger.info(f"Tavily SDK search failed or not installed ({exc}); using direct HTTP REST call.")
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_answer": False,
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for r in data.get("results", []):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("content", r.get("snippet", "")),
                        source="tavily",
                        published=r.get("published_date"),
                        raw=r,
                    ))
                return results
            else:
                logger.warning(f"Tavily REST API returned HTTP {resp.status_code}: {resp.text[:200]}")
                return []


# ─────────────────────────────────────────────────────────────────────────────
#  Provider: SerpAPI
# ─────────────────────────────────────────────────────────────────────────────

async def search_serpapi(query: str, api_key: str, max_results: int = 8) -> List[SearchResult]:
    """Search using SerpAPI (SDK or direct HTTP REST call)."""
    try:
        from serpapi import GoogleSearch
        def _sync_search():
            params = {
                "q":       query,
                "api_key": api_key,
                "num":     max_results,
                "hl":      "en",
                "gl":      "us",
            }
            search = GoogleSearch(params)
            data   = search.get_dict()
            results = []
            for r in data.get("organic_results", [])[:max_results]:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("link", ""),
                    snippet=r.get("snippet", ""),
                    source="serpapi",
                    published=r.get("date"),
                    raw=r,
                ))
            return results

        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(loop.run_in_executor(None, _sync_search), timeout=8.0)
    except (ImportError, ModuleNotFoundError, Exception) as exc:
        logger.info(f"SerpAPI SDK search failed or not installed ({exc}); using direct HTTP REST call.")
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "q":       query,
                    "api_key": api_key,
                    "num":     max_results,
                    "hl":      "en",
                    "gl":      "us",
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for r in data.get("organic_results", [])[:max_results]:
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("link", ""),
                        snippet=r.get("snippet", ""),
                        source="serpapi",
                        published=r.get("date"),
                        raw=r,
                    ))
                return results
            else:
                logger.warning(f"SerpAPI REST API returned HTTP {resp.status_code}: {resp.text[:200]}")
                return []


# ─────────────────────────────────────────────────────────────────────────────
#  Provider: Exa AI
# ─────────────────────────────────────────────────────────────────────────────

async def search_exa(query: str, api_key: str, max_results: int = 8) -> List[SearchResult]:
    """Search using Exa AI (SDK or direct HTTP REST call)."""
    try:
        from exa_py import Exa
        def _sync_search():
            client = Exa(api_key=api_key)
            response = client.search_and_contents(
                query,
                num_results=max_results,
                text={"max_characters": 500},
            )
            results = []
            for r in response.results:
                results.append(SearchResult(
                    title=getattr(r, "title", "") or "",
                    url=getattr(r, "url", "") or "",
                    snippet=getattr(r, "text", "") or "",
                    source="exa",
                    published=getattr(r, "published_date", None),
                    raw=r.__dict__ if hasattr(r, "__dict__") else {},
                ))
            return results

        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(loop.run_in_executor(None, _sync_search), timeout=8.0)
    except (ImportError, ModuleNotFoundError, Exception) as exc:
        logger.info(f"Exa SDK search failed or not installed ({exc}); using direct HTTP REST call.")
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "query": query,
                    "numResults": max_results,
                    "contents": {"text": {"maxCharacters": 500}}
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for r in data.get("results", []):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("text", r.get("snippet", "")),
                        source="exa",
                        published=r.get("publishedDate"),
                        raw=r,
                    ))
                return results
            else:
                logger.warning(f"Exa REST API returned HTTP {resp.status_code}: {resp.text[:200]}")
                return []


# ─────────────────────────────────────────────────────────────────────────────
#  Provider: DuckDuckGo (free fallback, no key)
# ─────────────────────────────────────────────────────────────────────────────

async def search_duckduckgo(query: str, max_results: int = 8) -> List[SearchResult]:
    """Free fallback search using DuckDuckGo (SDK or direct HTML scraping)."""
    # 1. Try DuckDuckGo python SDK if available
    try:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            from ddgs import DDGS

        def _sync_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        loop = asyncio.get_running_loop()
        raw = await asyncio.wait_for(loop.run_in_executor(None, _sync_search), timeout=8.0)
        if raw:
            results = []
            for r in raw:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", r.get("link", "")),
                    snippet=r.get("body", r.get("snippet", "")),
                    source="duckduckgo",
                    raw=r,
                ))
            return results
    except Exception as exc:
        logger.info(f"DDGS package search failed ({exc}); falling back to HTTP HTML scraping.")

    # 2. Native HTTP fallback using DuckDuckGo HTML endpoint
    import httpx
    import urllib.parse
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers=headers,
            )
            if resp.status_code == 200:
                html_text = resp.text
                results = []

                # 2a. Try BeautifulSoup DOM parsing if available
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_text, "html.parser")
                    for res_div in soup.find_all("div", class_=re.compile(r"result")):
                        a_tag = res_div.find("a", class_=re.compile(r"result__a")) or res_div.find("a")
                        s_tag = res_div.find("a", class_=re.compile(r"result__snippet")) or res_div.find("td", class_=re.compile(r"result-snippet"))
                        if a_tag and a_tag.get("href"):
                            href = a_tag["href"]
                            title = a_tag.get_text(strip=True)
                            snippet = s_tag.get_text(strip=True) if s_tag else ""
                            if href.startswith("//duckduckgo.com/l/?uddg="):
                                href = urllib.parse.unquote(href.split("uddg=")[-1].split("&")[0])
                            if title and href and not href.startswith("javascript:"):
                                results.append(SearchResult(
                                    title=title,
                                    url=href,
                                    snippet=snippet,
                                    source="duckduckgo",
                                ))
                            if len(results) >= max_results:
                                break
                    if results:
                        return results
                except Exception as bs_exc:
                    logger.debug(f"BS4 parsing skipped: {bs_exc}")

                # 2b. Multi-pattern regex fallback for raw HTML
                patterns = [
                    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?(?:<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>)?',
                    r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*result__url[^"]*"[^>]*>(.*?)</a>',
                ]
                for pat in patterns:
                    for match in re.finditer(pat, html_text, re.DOTALL | re.IGNORECASE):
                        if len(results) >= max_results:
                            break
                        groups = match.groups()
                        href = groups[0] if len(groups) > 0 else ""
                        title = groups[1] if len(groups) > 1 else ""
                        snippet = groups[2] if len(groups) > 2 else ""

                        title = re.sub(r"<[^>]+>", "", title or "").strip()
                        snippet = re.sub(r"<[^>]+>", "", snippet or "").strip()

                        if href.startswith("//duckduckgo.com/l/?uddg="):
                            href = urllib.parse.unquote(href.split("uddg=")[-1].split("&")[0])

                        if title and href and not href.startswith("javascript:"):
                            results.append(SearchResult(
                                title=title,
                                url=href,
                                snippet=snippet,
                                source="duckduckgo",
                            ))
                if results:
                    return results
    except Exception as exc:
        logger.warning(f"DuckDuckGo HTML scraping failed: {exc}")

    return []


def enhance_query_for_freshness(query: str) -> str:
    """
    Enrich search query with temporal/freshness indicators if asking for current information
    so external search engines prioritize recent news articles over stale historical ones.
    """
    q_clean = query.strip()
    q_lower = q_clean.lower()
    fresh_keywords = (
        "current", "latest", "present", "who is the", "who is minister",
        "chief minister", "education minister", "prime minister", "president of",
        "governor of", "election", "cabinet"
    )
    if any(kw in q_lower for kw in fresh_keywords):
        if not re.search(r"\b(202\d|203\d)\b", q_clean):
            import datetime
            current_year = datetime.datetime.now().year
            q_clean = f"{q_clean} {current_year - 1} {current_year}"
    return q_clean


# ─────────────────────────────────────────────────────────────────────────────
#  Unified search entry point
# ─────────────────────────────────────────────────────────────────────────────

async def unified_web_search(
    query: str,
    api_keys: Dict[str, str],
    max_results: Optional[int] = None,
) -> List[SearchResult]:
    """
    Try each provider in priority order (WEB_SEARCH_PROVIDER_ORDER).
    Skips providers whose key is missing. DuckDuckGo never requires a key.
    Ranks results by BM25 before returning.

    BUG-6 FIX: Results are now cached via WebSearchCache (10-minute TTL) so
    repeated identical queries (e.g., CRAG fallback re-running the same query)
    do not hit the external search API again.

    Args:
        query:       The search query (already cleaned of injected context).
        api_keys:    Dict of {provider: key} — includes both user DB keys
                     and server .env keys.
        max_results: Override WEB_SEARCH_MAX_RESULTS if provided.

    Returns:
        Ranked list of SearchResult objects.
    """
    cached = await web_search_cache.get(query)
    if cached is not None:
        logger.debug(f"[unified_web_search] Cache HIT for query='{query[:60]}'")
        if isinstance(cached, list):
            return cached
        if isinstance(cached, str):
            return [SearchResult(
                title="Web Search Result",
                url="",
                snippet=cached,
                source="cache",
                score=1.0,
            )]

    search_query = enhance_query_for_freshness(query)
    logger.info(f"[unified_web_search] Temporal enhanced query: '{search_query[:80]}'")

    n = max_results or settings.WEB_SEARCH_MAX_RESULTS
    provider_order = [p.strip() for p in settings.WEB_SEARCH_PROVIDER_ORDER.split(",") if p.strip()]

    # Merge server-side .env keys as lower-priority fallback
    merged_keys: Dict[str, str] = {}
    if settings.TAVILY_API_KEY:
        merged_keys["tavily"] = settings.TAVILY_API_KEY
    if settings.SERP_API_KEY:
        merged_keys["serpapi"] = settings.SERP_API_KEY
    if settings.EXA_API_KEY:
        merged_keys["exa"] = settings.EXA_API_KEY

    # User-supplied keys override server .env keys (with alias mapping)
    for k, v in api_keys.items():
        if v and not str(v).startswith("mock_"):
            k_lower = k.lower()
            merged_keys[k_lower] = v
            if k_lower in ("serp_api", "google_search"):
                merged_keys["serpapi"] = v
            elif k_lower in ("exa_ai", "exa_search"):
                merged_keys["exa"] = v
            elif k_lower in ("tavily_search", "tavily_api"):
                merged_keys["tavily"] = v

    last_error: Optional[Exception] = None

    for provider in provider_order:
        provider = provider.lower()

        try:
            if provider == "tavily":
                key = merged_keys.get("tavily") or merged_keys.get("tavily_search")
                if not key:
                    continue
                logger.info(f"[web_search] Trying Tavily for: '{search_query[:60]}'")
                results = await asyncio.wait_for(search_tavily(search_query, key, n), timeout=7.0)

            elif provider == "serpapi":
                key = merged_keys.get("serpapi") or merged_keys.get("serp_api")
                if not key:
                    continue
                logger.info(f"[web_search] Trying SerpAPI for: '{search_query[:60]}'")
                results = await asyncio.wait_for(search_serpapi(search_query, key, n), timeout=7.0)

            elif provider == "exa":
                key = merged_keys.get("exa")
                if not key:
                    continue
                logger.info(f"[web_search] Trying Exa AI for: '{search_query[:60]}'")
                results = await asyncio.wait_for(search_exa(search_query, key, n), timeout=7.0)

            elif provider == "duckduckgo":
                logger.info(f"[web_search] Trying DuckDuckGo for: '{search_query[:60]}'")
                results = await asyncio.wait_for(search_duckduckgo(search_query, n), timeout=7.0)

            else:
                logger.warning(f"[web_search] Unknown provider in order list: {provider}")
                continue

            if results:
                logger.info(f"[web_search] {provider} returned {len(results)} results → ranking")
                ranked = rank_results(query, results)
                # BUG-6 FIX: Persist to cache (key = query text, value = formatted string)
                # so subsequent calls with the same query (e.g. CRAG retry) are served
                # from cache without hitting external APIs again.
                try:
                    await web_search_cache.set(query, ranked)
                except Exception as _cache_err:
                    logger.debug(f"[unified_web_search] Cache set failed (non-fatal): {_cache_err}")
                return ranked
            else:
                logger.warning(f"[web_search] {provider} returned 0 results, trying next")

        except Exception as exc:
            last_error = exc
            logger.warning(f"[web_search] {provider} failed: {exc!r} — trying next provider")
            continue

    logger.error(f"[web_search] All providers failed. Last error: {last_error}")
    return []


def _ensure_search_results(results: List[Any]) -> List[SearchResult]:
    cleaned = []
    for r in results:
        if isinstance(r, SearchResult):
            cleaned.append(r)
        elif isinstance(r, dict):
            cleaned.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", r.get("href", r.get("link", ""))),
                snippet=r.get("snippet", r.get("content", r.get("body", ""))),
                source=r.get("source", "duckduckgo"),
                score=r.get("score", 0.0),
                published=r.get("published"),
                raw=r
            ))
    return cleaned


def format_for_llm(results: List[Any]) -> str:
    """Format ranked results as a clean markdown block for LLM consumption."""
    results_list = _ensure_search_results(results)
    if not results_list:
        return "[Web search returned no results for this query. Do NOT fabricate real-time news, current events, or recent information out of memory. Explicitly state to the user that no live search results were found for this query.]"

    lines = [f"Web Search Results ({results_list[0].source if results_list else 'unknown'}):\n"]
    for i, r in enumerate(results_list, start=1):
        lines.append(f"[{i}] {r.title}")
        lines.append(f"URL: {r.url}")
        if r.snippet:
            lines.append(f"Summary: {r.snippet[:400]}")
        if r.published:
            lines.append(f"Published: {r.published}")
        lines.append("")
    return "\n".join(lines)


def format_as_source_documents(results: List[Any]) -> List[Dict[str, Any]]:
    """
    Convert ranked results to source_documents list with explicit web source metadata.
    Each result becomes its own citable web source with distinct UI tagging.
    """
    results_list = _ensure_search_results(results)
    docs = []
    for i, r in enumerate(results_list, start=1):
        docs.append({
            "index":       i,
            "filename":    f"[Web] {r.title}" if r.title else f"[Web] {r.url}",
            "content":     r.snippet,
            "url":         r.url,
            "distance":    round(1.0 - r.score, 4),   # lower distance = higher relevance
            "confidence":  r.score,
            "source":      r.source,
            "published":   r.published,
            "is_web":      True,
            "source_type": "web",
            "used":        True,
        })
    return docs
