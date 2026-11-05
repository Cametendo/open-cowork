"""Search engines: DuckDuckGo (no key), SearXNG (self-hosted), Brave and Tavily (API key)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .settings import WebSettings

ENGINES = ("duckduckgo", "searxng", "brave", "tavily")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0 OpenCowork"
TIMEOUT = httpx.Timeout(15.0, connect=8.0)


class SearchError(Exception):
    pass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

    def as_dict(self) -> dict[str, str]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


def _clean(text: str, limit: int = 400) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def _http_url(url: str) -> bool:
    return urlparse(url).scheme in ("http", "https")


# --------------------------------------------------------------------------- DuckDuckGo


class _DDGParser(HTMLParser):
    """Extracts result links and snippets from html.duckduckgo.com."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._mode: str | None = None  # "title" | "snippet"
        self._buf: list[str] = []
        self._href = ""
        self._open: tuple[str, str] | None = None  # (title, url) waiting for its snippet

    def _flush(self, snippet: str = "") -> None:
        if self._open:
            self.results.append(SearchResult(self._open[0], self._open[1], snippet))
            self._open = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if "result__a" in classes:
            self._flush()  # the previous result had no snippet
            self._mode, self._buf, self._href = "title", [], a.get("href") or ""
        elif "result__snippet" in classes:
            self._mode, self._buf = "snippet", []

    def handle_data(self, data: str) -> None:
        if self._mode:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._mode:
            return
        text = _clean("".join(self._buf))
        if self._mode == "title":
            url = _ddg_target(self._href)
            self._open = (text, url) if url else None
        elif self._mode == "snippet":
            self._flush(text)
        self._mode = None


def _ddg_target(href: str) -> str:
    """DuckDuckGo wraps result links: //duckduckgo.com/l/?uddg=<encoded target>."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        href = unquote(target)
    if not _http_url(href) or urlparse(href).netloc.endswith("duckduckgo.com"):
        return ""  # ads and internal links
    return href


def parse_duckduckgo(html: str) -> list[SearchResult]:
    parser = _DDGParser()
    parser.feed(html)
    parser.close()
    parser._flush()  # the last result may have no snippet
    return parser.results


async def _duckduckgo(client: httpx.AsyncClient, query: str, count: int, _s: WebSettings) -> list[SearchResult]:
    resp = await client.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "wt-wt"})
    if resp.status_code in (202, 403, 429):
        raise SearchError(
            "DuckDuckGo refused the request (it limits automated searches). "
            "Try again later, or switch to SearXNG, Brave or Tavily in Admin › Web search."
        )
    resp.raise_for_status()
    results = parse_duckduckgo(resp.text)
    if not results and "result" not in resp.text:
        raise SearchError("DuckDuckGo returned a page without results (possibly a bot check). Try another engine.")
    return results[:count]


# --------------------------------------------------------------------------- SearXNG


async def _searxng(client: httpx.AsyncClient, query: str, count: int, s: WebSettings) -> list[SearchResult]:
    if not s.url:
        raise SearchError("No SearXNG URL is configured (Admin › Web search).")
    resp = await client.get(s.url.rstrip("/") + "/search", params={"q": query, "format": "json"})
    if resp.status_code == 403:
        raise SearchError(
            "SearXNG refused the request. Enable the JSON format in its settings.yml "
            "(search: formats: [html, json]) and allow this server to use it."
        )
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError as e:
        raise SearchError("SearXNG did not return JSON. Enable the json format in its settings.yml.") from e
    out = [
        SearchResult(_clean(r.get("title"), 200), r["url"], _clean(r.get("content")))
        for r in data.get("results", [])
        if isinstance(r, dict) and _http_url(r.get("url", ""))
    ]
    return out[:count]


# --------------------------------------------------------------------------- Brave


async def _brave(client: httpx.AsyncClient, query: str, count: int, s: WebSettings) -> list[SearchResult]:
    if not s.api_key:
        raise SearchError("No Brave Search API key is configured (Admin › Web search).")
    resp = await client.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": count},
        headers={"X-Subscription-Token": s.api_key, "Accept": "application/json"},
    )
    if resp.status_code in (401, 403):
        raise SearchError("Brave rejected the API key.")
    resp.raise_for_status()
    items = (resp.json().get("web") or {}).get("results", [])
    return [
        SearchResult(_clean(r.get("title"), 200), r["url"], _clean(re.sub(r"<[^>]+>", "", r.get("description", ""))))
        for r in items
        if _http_url(r.get("url", ""))
    ][:count]


# --------------------------------------------------------------------------- Tavily


async def _tavily(client: httpx.AsyncClient, query: str, count: int, s: WebSettings) -> list[SearchResult]:
    if not s.api_key:
        raise SearchError("No Tavily API key is configured (Admin › Web search).")
    resp = await client.post(
        "https://api.tavily.com/search",
        json={"query": query, "max_results": count},
        headers={"Authorization": f"Bearer {s.api_key}"},
    )
    if resp.status_code in (401, 403):
        raise SearchError("Tavily rejected the API key.")
    resp.raise_for_status()
    return [
        SearchResult(_clean(r.get("title"), 200), r["url"], _clean(r.get("content")))
        for r in resp.json().get("results", [])
        if _http_url(r.get("url", ""))
    ][:count]


_IMPL = {"duckduckgo": _duckduckgo, "searxng": _searxng, "brave": _brave, "tavily": _tavily}


async def search(
    settings: WebSettings, query: str, count: int | None = None, client: httpx.AsyncClient | None = None
) -> list[SearchResult]:
    query = _clean(query, 400)
    if not query:
        raise SearchError("The search query is empty.")
    impl = _IMPL.get(settings.engine)
    if impl is None:
        raise SearchError(f"Unknown search engine '{settings.engine}'.")
    n = max(1, min(int(count or settings.result_count), 10))
    own = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    try:
        return await impl(client, query, n, settings)
    except httpx.HTTPStatusError as e:
        raise SearchError(f"{settings.engine} answered with HTTP {e.response.status_code}.") from e
    except httpx.HTTPError as e:
        raise SearchError(f"Could not reach {settings.engine}: {e.__class__.__name__} {e}".strip()) from e
    finally:
        if own:
            await client.aclose()
