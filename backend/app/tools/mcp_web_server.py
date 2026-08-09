"""
app/tools/mcp_web_server.py — Web MCP Stdio Server (MCP JSON-RPC 2.0).

Exposes Web MCP tools over standard Model Context Protocol (MCP) JSON-RPC 2.0 stdio:
  - web_search: Searches the web via multi-provider fallback (Tavily, SerpAPI, Exa, DDG).
  - web_fetch: Fetches a URL and extracts clean readable markdown text content.
  - web_extract: Extracts structured components (links, headings, tables) from a URL.
"""

import sys
import json
import urllib.request
import urllib.parse
import re
import html
from typing import Dict, Any, Optional

def send_response(req_id: Any, result: Optional[Dict[str, Any]] = None, error: Optional[Dict[str, Any]] = None):
    resp = {
        "jsonrpc": "2.0",
        "id": req_id
    }
    if result is not None:
        resp["result"] = result
    if error is not None:
        resp["error"] = error
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()

import os
import asyncio

# Ensure parent directory (backend) is on sys.path for app module imports
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

def handle_web_search(query: str, max_results: int = 5) -> str:
    """Unified multi-provider web search for MCP server with DDG fallback."""
    try:
        from app.services.web_search import unified_web_search, format_for_llm
        results = asyncio.run(unified_web_search(query))
        if results:
            return format_for_llm(results[:max_results])
    except Exception as exc:
        pass

    # Fallback to DDGS SDK or robust HTML parsing
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
            if raw:
                formatted = []
                for item in raw:
                    t = item.get("title", "")
                    u = item.get("href", item.get("link", ""))
                    s = item.get("body", item.get("snippet", ""))
                    if t and u:
                        formatted.append(f"Title: {t}\nURL: {u}\nSnippet: {s}\n")
                if formatted:
                    return "\n".join(formatted)
    except Exception:
        pass

    # HTML fallback with flexible anchor & snippet match patterns
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    encoded_query = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{encoded_query}"
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_html = resp.read().decode("utf-8", errors="ignore")
            
        results = []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(raw_html, "html.parser")
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
                        results.append(f"Title: {title}\nURL: {href}\nSnippet: {snippet}\n")
                    if len(results) >= max_results:
                        break
        except Exception:
            pass

        if not results:
            # Multi-pattern regex fallback for raw HTML
            patterns = [
                r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?(?:<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>)?',
                r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*result__url[^"]*"[^>]*>(.*?)</a>',
            ]
            for pat in patterns:
                for match in re.finditer(pat, raw_html, re.DOTALL | re.IGNORECASE):
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
                        results.append(f"Title: {title}\nURL: {href}\nSnippet: {snippet}\n")
                if results:
                    break
                    
        if results:
            return "\n".join(results)
        return "No web search results found."
    except Exception as exc:
        return f"Web search error: {exc}"

def handle_web_fetch(url: str, max_chars: int = 4000) -> str:
    """Fetches a URL and returns clean readable text."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_bytes = resp.read()
            raw_html = raw_bytes.decode("utf-8", errors="ignore")

        # Strip scripts, styles, comments cleanly
        text = re.sub(r"<script[^>]*>.*?</script>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)
        return clean_text[:max_chars] if clean_text else "Webpage retrieved with no visible body text."
    except Exception as exc:
        return f"Failed to fetch webpage ({url}): {exc}"

def handle_web_extract(url: str) -> str:
    """Extracts structured elements (headings, links, metadata) from a webpage."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_html = resp.read().decode("utf-8", errors="ignore")

        headings = re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>', raw_html, re.DOTALL | re.IGNORECASE)
        links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw_html, re.DOTALL | re.IGNORECASE)

        clean_headings = [re.sub(r"<[^>]+>", "", h).strip() for h in headings if h.strip()][:10]
        clean_links = []
        for href, label in links:
            lbl = re.sub(r"<[^>]+>", "", label).strip()
            if lbl and href and not href.startswith("#"):
                clean_links.append(f"- [{lbl}]({href})")
            if len(clean_links) >= 10:
                break

        out = [f"### Page Extraction for: {url}", "#### Headings:"]
        out.extend([f"- {h}" for h in clean_headings] or ["(None)"])
        out.append("\n#### Key Links:")
        out.extend(clean_links or ["(None)"])
        return "\n".join(out)
    except Exception as exc:
        return f"Failed to extract structured web data from ({url}): {exc}"


def main():
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue

            req_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            # Notification (no req_id)
            if req_id is None:
                continue

            if method == "initialize":
                send_response(req_id, result={
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "Web-MCP-Server", "version": "1.0.0"}
                })

            elif method == "tools/list":
                tools = [
                    {
                        "name": "web_search",
                        "description": "Searches the web for real-time information, news, weather, and reference topics.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query text"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "web_fetch",
                        "description": "Fetches a URL webpage and extracts clean readable markdown text content.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "description": "Webpage URL to fetch"}
                            },
                            "required": ["url"]
                        }
                    },
                    {
                        "name": "web_extract",
                        "description": "Extracts structured elements such as headings, metadata, and key links from a web page URL.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "description": "Webpage URL to extract data from"}
                            },
                            "required": ["url"]
                        }
                    }
                ]
                send_response(req_id, result={"tools": tools})

            elif method == "tools/call":
                tool_name = params.get("name")
                args = params.get("arguments", {})
                
                result_text = ""
                if tool_name == "web_search":
                    result_text = handle_web_search(args.get("query", ""))
                elif tool_name == "web_fetch":
                    result_text = handle_web_fetch(args.get("url", ""))
                elif tool_name == "web_extract":
                    result_text = handle_web_extract(args.get("url", ""))
                else:
                    result_text = f"Unknown web tool: {tool_name}"

                send_response(req_id, result={
                    "content": [
                        {
                            "type": "text",
                            "text": result_text
                        }
                    ]
                })

            else:
                send_response(req_id, error={"code": -32601, "message": f"Method '{method}' not found."})

        except Exception as e:
            sys.stderr.write(f"Exception in web mcp server loop: {e}\n")
            sys.stderr.flush()

if __name__ == "__main__":
    main()
