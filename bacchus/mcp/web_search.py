"""
Web search MCP server for Bacchus with multi-provider support.

Supported providers:
- DuckDuckGo (Default, no key required)
- Brave Search (Requires API Key)
- Tavily (Requires API Key)
- Serper.dev (Requires API Key)
- SerpAPI (Requires API Key)
- Google Custom Search (Requires API Key + CX)
- Firecrawl (Requires API Key)
- Exa (Requires API Key)

Run as: python -m bacchus.mcp.web_search
"""

import abc
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests
import html2text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("web_search")

class SearchProvider(abc.ABC):
    """Abstract base class for search providers."""
    
    def __init__(self, api_key: Optional[str] = None, config: Dict[str, Any] = None):
        self.api_key = api_key
        self.config = config or {}

    @abc.abstractmethod
    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        """
        Perform search and return standardized results.
        
        Returns:
            List of dicts with 'title', 'snippet', 'url' keys.
        """
        pass

class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo provider (using HTML scraping or API if available)."""
    
    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        # Using the Instant Answer API as in original implementation
        # Note: This API is limited and often returns no results for general queries.
        # A better approach for a real app would be using the html scraping method 
        # like the `duckduckgo_search` package does, but we stick to standard lib/requests here.
        try:
            url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_html": 1,
                "t": "bacchus"
            }
            headers = {"User-Agent": "Bacchus/0.1.0"}
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            
            # Abstract
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", "Summary"),
                    "snippet": data["Abstract"],
                    "url": data.get("AbstractURL", "")
                })
                
            # Related Topics
            for topic in data.get("RelatedTopics", []):
                if len(results) >= num_results:
                    break
                if "Text" in topic and "FirstURL" in topic:
                    results.append({
                        "title": topic.get("Text", "").split(" - ")[0],
                        "snippet": topic.get("Text", ""),
                        "url": topic.get("FirstURL", "")
                    })
                    
            return results
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []

class BraveProvider(SearchProvider):
    """Brave Search API provider."""
    
    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            return [{"title": "Error", "snippet": "Brave API key missing", "url": ""}]
            
        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key
            }
            params = {"q": query, "count": min(num_results, 20)}
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            if "web" in data and "results" in data["web"]:
                for item in data["web"]["results"]:
                    results.append({
                        "title": item.get("title", ""),
                        "snippet": item.get("description", ""),
                        "url": item.get("url", "")
                    })
            return results
        except Exception as e:
            logger.error(f"Brave search error: {e}")
            return [{"title": "Error", "snippet": str(e), "url": ""}]

class TavilyProvider(SearchProvider):
    """Tavily Search API provider."""
    
    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            return [{"title": "Error", "snippet": "Tavily API key missing", "url": ""}]
            
        try:
            url = "https://api.tavily.com/search"
            headers = {"Content-Type": "application/json"}
            data = {
                "api_key": self.api_key,
                "query": query,
                "max_results": num_results,
                "search_depth": "basic",
                "include_answer": True
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            # Add AI answer if present
            if data.get("answer"):
                results.append({
                    "title": "Tavily AI Answer",
                    "snippet": data["answer"],
                    "url": ""
                })
                
            for item in data.get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("content", ""),
                    "url": item.get("url", "")
                })
            return results
        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return [{"title": "Error", "snippet": str(e), "url": ""}]

class SerperProvider(SearchProvider):
    """Serper.dev API provider."""
    
    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            return [{"title": "Error", "snippet": "Serper API key missing", "url": ""}]
            
        try:
            url = "https://google.serper.dev/search"
            headers = {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json"
            }
            data = {"q": query, "num": num_results}
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            # Knowledge Graph
            if "knowledgeGraph" in data:
                kg = data["knowledgeGraph"]
                results.append({
                    "title": kg.get("title", "Knowledge Graph"),
                    "snippet": kg.get("description", ""),
                    "url": kg.get("website", "")
                })
                
            # Organic
            for item in data.get("organic", []):
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("link", "")
                })
            return results
        except Exception as e:
            logger.error(f"Serper search error: {e}")
            return [{"title": "Error", "snippet": str(e), "url": ""}]

class SerpAPIProvider(SearchProvider):
    """SerpAPI provider."""
    
    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            return [{"title": "Error", "snippet": "SerpAPI key missing", "url": ""}]
            
        try:
            url = "https://serpapi.com/search"
            params = {
                "api_key": self.api_key,
                "q": query,
                "num": num_results,
                "engine": "google"
            }
            
            response = requests.get(url, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("organic_results", []):
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("link", "")
                })
            return results
        except Exception as e:
            logger.error(f"SerpAPI search error: {e}")
            return [{"title": "Error", "snippet": str(e), "url": ""}]

class GoogleProvider(SearchProvider):
    """Google Custom Search JSON API provider."""
    
    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            return [{"title": "Error", "snippet": "Google API key missing", "url": ""}]
        
        cx = self.config.get("cx", "")
        if not cx:
            return [{"title": "Error", "snippet": "Google CX (Search Engine ID) missing", "url": ""}]
            
        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": self.api_key,
                "cx": cx,
                "q": query,
                "num": min(num_results, 10)
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("items", []):
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("link", "")
                })
            return results
        except Exception as e:
            logger.error(f"Google search error: {e}")
            return [{"title": "Error", "snippet": str(e), "url": ""}]

class FirecrawlProvider(SearchProvider):
    """Firecrawl API provider."""
    
    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            return [{"title": "Error", "snippet": "Firecrawl API key missing", "url": ""}]
            
        try:
            url = "https://api.firecrawl.dev/v0/search"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            data = {
                "query": query,
                "limit": num_results,
                "pageOptions": {"fetchPageContent": False}
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            results = []
            if data.get("success") and "data" in data:
                for item in data["data"]:
                    results.append({
                        "title": item.get("title", "") or item.get("url", ""),
                        "snippet": item.get("markdown", "")[:200] + "..." if item.get("markdown") else "",
                        "url": item.get("url", "")
                    })
            return results
        except Exception as e:
            logger.error(f"Firecrawl search error: {e}")
            return [{"title": "Error", "snippet": str(e), "url": ""}]

class ExaProvider(SearchProvider):
    """Exa (formerly Metaphor) API provider."""
    
    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            return [{"title": "Error", "snippet": "Exa API key missing", "url": ""}]
            
        try:
            url = "https://api.exa.ai/search"
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            data = {
                "query": query,
                "numResults": num_results,
                "useAutoprompt": True
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for item in data.get("results", []):
                results.append({
                    "title": item.get("title", "") or item.get("url", ""),
                    "snippet": f"Score: {item.get('score', 0)}", # Exa mostly returns IDs/URLs unless contents requested
                    "url": item.get("url", "")
                })
            return results
        except Exception as e:
            logger.error(f"Exa search error: {e}")
            return [{"title": "Error", "snippet": str(e), "url": ""}]

class OpenAIProvider(SearchProvider):
    """OpenAI real-time web search provider (gpt-4o-mini-search-preview)."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini-search-preview"):
        super().__init__(api_key)
        self.model = model or "gpt-4o-mini-search-preview"

    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            return [{"title": "Error", "snippet": "OpenAI API key missing", "url": ""}]

        try:
            import urllib.request as _urlreq
            url = "https://api.openai.com/v1/chat/completions"
            payload = json.dumps({
                "model": self.model,
                "messages": [{"role": "user", "content": query}],
                "web_search_options": {}
            }).encode()
            req = _urlreq.Request(url, data=payload, headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            })
            with _urlreq.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
            content = result["choices"][0]["message"]["content"]
            return [{"title": "OpenAI Web Search", "snippet": content, "url": ""}]
        except Exception as e:
            logger.error(f"OpenAI search error: {e}")
            return [{"title": "Error", "snippet": str(e), "url": ""}]


class GeminiProvider(SearchProvider):
    """Google Gemini with Google Search grounding."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        super().__init__(api_key)
        self.model = model or "gemini-1.5-flash"

    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            return [{"title": "Error", "snippet": "Gemini API key missing", "url": ""}]

        try:
            import urllib.request as _urlreq
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:generateContent?key={self.api_key}"
            )
            payload = json.dumps({
                "contents": [{"parts": [{"text": query}]}],
                "tools": [{"google_search": {}}]
            }).encode()
            req = _urlreq.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with _urlreq.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
            parts = result["candidates"][0]["content"]["parts"]
            content = "\n".join(p.get("text", "") for p in parts if "text" in p)
            return [{"title": "Gemini Search Result", "snippet": content, "url": ""}]
        except Exception as e:
            logger.error(f"Gemini search error: {e}")
            return [{"title": "Error", "snippet": str(e), "url": ""}]


class SearchAPIProvider(SearchProvider):
    """SearchAPI.io provider."""

    def search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            return [{"title": "Error", "snippet": "SearchAPI key missing", "url": ""}]

        try:
            url = "https://www.searchapi.io/api/v1/search"
            params = {
                "api_key": self.api_key,
                "engine": "google",
                "q": query,
                "num": num_results
            }
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            results = []
            for item in data.get("organic_results", []):
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("link", "")
                })
            return results
        except Exception as e:
            logger.error(f"SearchAPI search error: {e}")
            return [{"title": "Error", "snippet": str(e), "url": ""}]


class WebSearchServer:
    """MCP server for web search operations."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize web search server.

        Args:
            config: Configuration dictionary with provider, api_key, max_results, etc.
        """
        self.provider_name = config.get("provider", "duckduckgo")
        self.api_key = config.get("api_key", "")
        self.max_results = int(config.get("max_results", 10))
        self.timeout = int(config.get("timeout", 10))
        self.fetch_max_length = int(config.get("fetch_max_length", 8000))
        self.cx = config.get("cx", "")
        self.model = config.get("model", "")
        self.user_agent = "Bacchus/0.1.0 (Windows; NPU Chat Application)"
        self.provider = self._get_provider(self.provider_name)

    def _get_provider(self, name: str) -> SearchProvider:
        """Factory method to get search provider."""
        name = name.lower()
        key = self.api_key

        if name == "brave":
            return BraveProvider(key)
        elif name == "tavily":
            return TavilyProvider(key)
        elif name == "serper":
            return SerperProvider(key)
        elif name == "serpapi":
            return SerpAPIProvider(key)
        elif name == "google":
            return GoogleProvider(key, config={"cx": self.cx})
        elif name == "firecrawl":
            return FirecrawlProvider(key)
        elif name == "exa":
            return ExaProvider(key)
        elif name == "openai":
            return OpenAIProvider(key, self.model)
        elif name == "gemini":
            return GeminiProvider(key, self.model)
        elif name == "searchapi":
            return SearchAPIProvider(key)
        else:
            return DuckDuckGoProvider()

    def search(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """Search the web using configured provider."""
        if not query or not query.strip():
            return {"content": [{"type": "text", "text": "Error: Search query cannot be empty"}]}

        num_results = min(num_results, self.max_results)
        
        results = self.provider.search(query, num_results)
        
        if not results:
            return {"content": [{"type": "text", "text": f"No results found for: {query}"}]}
            
        # Format results
        output_lines = [f"Search results for: {query} (via {self.provider_name})\n"]
        for i, result in enumerate(results, 1):
            output_lines.append(f"{i}. {result['title']}")
            if result['snippet']:
                output_lines.append(f"   {result['snippet']}")
            output_lines.append(f"   URL: {result['url']}\n")

        return {"content": [{"type": "text", "text": "\n".join(output_lines)}]}

    def fetch_webpage(self, url: str, max_length: int = 0) -> Dict[str, Any]:
        """Fetch and clean webpage content, stripping navigation and boilerplate."""
        if not url or not url.startswith(("http://", "https://")):
            return {"content": [{"type": "text", "text": "Error: Invalid URL"}]}

        limit = max_length if max_length > 0 else self.fetch_max_length

        try:
            headers = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml"
            }

            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            # Decode content
            response.encoding = response.apparent_encoding or 'utf-8'
            html_str = response.text

            # Use BeautifulSoup to extract main content and strip boilerplate
            try:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(html_str, 'html.parser')

                # Remove noise elements: navigation, headers, footers, sidebars, TOC, scripts, styles
                REMOVE_TAGS = ['nav', 'header', 'footer', 'aside', 'script', 'style', 'noscript']
                REMOVE_IDS = {
                    'navigation', 'sidebar', 'header', 'footer', 'menu', 'toc',
                    'mw-head', 'mw-navigation', 'mw-panel', 'mw-page-base', 'mw-head-base',
                    'siteSub', 'contentSub', 'jump-to-nav', 'mw-fr-revisiondetails-wrapper',
                    'catlinks', 'footer', 'p-cactions',
                }
                REMOVE_CLASSES = {
                    'navigation', 'sidebar', 'menu', 'navbar', 'nav', 'header', 'footer',
                    'toc', 'mw-editsection', 'printfooter', 'mw-jump-link', 'noprint',
                    'mw-indicators', 'mw-parser-output-toc',
                }

                for tag in soup(REMOVE_TAGS):
                    tag.decompose()
                for el in soup.find_all(id=lambda x: x and x.lower() in REMOVE_IDS):
                    el.decompose()
                for el in soup.find_all(class_=lambda x: x and any(
                    c.lower() in REMOVE_CLASSES for c in (x if isinstance(x, list) else [x])
                )):
                    el.decompose()

                # Try to find the main content container
                main_content = (
                    soup.find('main') or
                    soup.find('article') or
                    soup.find(id='mw-content-text') or     # Wikipedia
                    soup.find(id='content') or
                    soup.find(id='main-content') or
                    soup.find(id='bodyContent') or          # MediaWiki
                    soup.find(role='main') or
                    soup.find('div', class_='mw-parser-output') or
                    soup.find('div', class_='post-content') or
                    soup.find('div', class_='article-content') or
                    soup.find('div', class_='entry-content') or
                    soup.body
                )

                html_to_convert = str(main_content) if main_content else html_str

            except ImportError:
                # BeautifulSoup not available; fall back to full HTML
                html_to_convert = html_str

            # Convert cleaned HTML to markdown
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.skip_internal_links = True
            h.body_width = 0

            text_content = h.handle(html_to_convert)

            # Clean up blank lines
            lines = [line.strip() for line in text_content.split('\n')]
            text_content = '\n'.join(line for line in lines if line)

            if len(text_content) > limit:
                text_content = text_content[:limit] + f"\n\n[Content truncated at {limit} characters]"

            return {
                "content": [{
                    "type": "text",
                    "text": f"Content from {url}:\n\n{text_content}"
                }]
            }

        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error fetching webpage: {str(e)}"}]}

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools."""
        return [
            {
                "name": "search_web",
                "description": f"Search the internet using {self.provider_name}",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "num_results": {"type": "integer", "description": "Number of results", "default": 5}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "fetch_webpage",
                "description": "Fetch and read webpage content. Navigation and boilerplate are stripped automatically.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to fetch"},
                        "max_length": {
                            "type": "integer",
                            "description": (
                                f"Max character length of returned content (default: {self.fetch_max_length}). "
                                "Omit or use 0 to use the default. Avoid setting this below 2000."
                            ),
                            "default": self.fetch_max_length
                        }
                    },
                    "required": ["url"]
                }
            }
        ]

def run_server():
    """Run the web search MCP server."""
    try:
        config = json.loads(os.environ.get("BACCHUS_MCP_CONFIG", "{}"))
    except Exception:
        config = {}

    try:
        secrets = json.loads(os.environ.get("BACCHUS_MCP_SECRETS", "{}"))
    except Exception:
        secrets = {}

    provider = config.get("provider", "duckduckgo")
    provider_secrets = secrets.get("web_search", {}).get(provider, {})
    config["api_key"] = provider_secrets.get("api_key", "")
    if provider == "google":
        config.setdefault("cx", provider_secrets.get("cx", ""))
    if provider in ("openai", "gemini"):
        config.setdefault("model", provider_secrets.get("model", ""))

    server = WebSearchServer(config)
    
    # JSON-RPC 2.0 loop
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            req_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})
            
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "web_search", "version": "0.1.0"}
                    }
                }
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"tools": server.get_tools()}
                }
            elif method == "tools/call":
                name = params.get("name")
                args = params.get("arguments", {})
                
                if name == "search_web":
                    res = server.search(args.get("query", ""), args.get("num_results", 5))
                elif name == "fetch_webpage":
                    res = server.fetch_webpage(args.get("url", ""), args.get("max_length", 0))
                else:
                    res = {"content": [{"type": "text", "text": f"Unknown tool: {name}"}]}
                    
                response = {"jsonrpc": "2.0", "id": req_id, "result": res}
            elif method == "shutdown":
                break
            else:
                continue
                
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            
        except Exception as e:
            logger.error(f"Error: {e}")

if __name__ == "__main__":
    run_server()
