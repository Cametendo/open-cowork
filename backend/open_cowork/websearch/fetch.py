"""Fetch a web page and reduce it to readable text.

The server (and, through Cowork, the agent) can be steered by page content and
by URLs a model produces, so by default only public internet addresses are
reachable: loopback, private, link-local, CGNAT (Tailscale) and other
non-global addresses are refused. The check happens at connect time on the
address that is actually used, for every redirect hop, so DNS tricks
(rebinding) can't slip past it.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpcore
import httpx

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0 OpenCowork"
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 5
TIMEOUT = httpx.Timeout(20.0, connect=8.0)
DEFAULT_MAX_CHARS = 12_000
TEXT_TYPES = ("text/", "application/json", "application/xml", "application/xhtml", "application/rss", "application/atom")


class FetchError(Exception):
    pass


def _is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global


class _PublicOnlyBackend(httpcore.AnyIOBackend):
    """Resolves the host itself and only connects to a public address."""

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):  # type: ignore[override]
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise httpcore.ConnectError(f"could not resolve {host}") from e
        addresses = [i[4][0] for i in infos]
        if not addresses or not all(_is_public(a) for a in addresses):
            raise httpcore.ConnectError(f"{host} is not a public internet address")
        return await super().connect_tcp(addresses[0], port, timeout, local_address, socket_options)


def _public_only_client() -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport()
    transport._pool = httpcore.AsyncConnectionPool(  # pin connections to validated addresses
        ssl_context=transport._pool._ssl_context,  # type: ignore[attr-defined]
        max_connections=20,
        network_backend=_PublicOnlyBackend(),
    )
    return httpx.AsyncClient(
        transport=transport, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"}
    )


# --------------------------------------------------------------------------- html → text


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "head", "iframe", "canvas", "form", "nav", "footer", "aside"}
    BLOCK = {
        "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "main", "blockquote", "pre",
        "h1", "h2", "h3", "h4", "h5", "h6", "hr", "dd", "dt", "figcaption",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP and tag != "head":
            self._skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3"):
            self.parts.append("\n## ")
        elif tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP and tag != "head" and self._skip:
            self._skip -= 1
        if tag in self.BLOCK and tag != "li":  # <li> already starts a new line
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    p = _TextExtractor()
    p.feed(html)
    p.close()
    text = "".join(p.parts)
    text = re.sub(r"[ \t\r\f\v ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return re.sub(r"\s+", " ", p.title).strip(), text


# --------------------------------------------------------------------------- fetch


async def fetch_page(
    url: str, *, allow_private: bool = False, max_chars: int = DEFAULT_MAX_CHARS
) -> dict[str, str | bool]:
    """Returns {"url", "title", "text", "truncated"} for the final URL after redirects."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise FetchError("Only http:// and https:// URLs can be fetched.")
    max_chars = max(500, min(int(max_chars or DEFAULT_MAX_CHARS), 50_000))

    client = httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) if allow_private else _public_only_client()
    current = url.strip()
    try:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                async with client.stream("GET", current, follow_redirects=False) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                        current = urljoin(current, resp.headers["location"])
                        if urlparse(current).scheme not in ("http", "https"):
                            raise FetchError("The page redirected to an unsupported address.")
                        continue
                    if resp.status_code >= 400:
                        raise FetchError(f"The page answered with HTTP {resp.status_code}.")
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype and not ctype.startswith(TEXT_TYPES):
                        raise FetchError(f"Can't read '{ctype}' content, only text and HTML pages.")
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            break
                    charset = resp.charset_encoding or "utf-8"
            except httpx.ConnectError as e:
                reason = str(e) or "connection failed"
                if "not a public internet address" in reason:
                    raise FetchError(
                        f"{urlparse(current).hostname} is not a public internet address. Fetching private or local "
                        "addresses is disabled (an admin can allow it in Admin › Web search)."
                    ) from e
                raise FetchError(f"Could not connect to {urlparse(current).hostname}: {reason}") from e
            except httpx.HTTPError as e:
                raise FetchError(f"Could not fetch the page: {e.__class__.__name__} {e}".strip()) from e

            raw = bytes(body[:MAX_BYTES])
            try:
                text = raw.decode(charset, errors="replace")
            except LookupError:
                text = raw.decode("utf-8", errors="replace")
            if ctype in ("", "text/html", "application/xhtml+xml") or text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
                title, text = html_to_text(text)
            else:
                title = ""
            truncated = len(body) > MAX_BYTES or len(text) > max_chars
            return {"url": current, "title": title, "text": text[:max_chars], "truncated": truncated}
        raise FetchError("Too many redirects.")
    finally:
        await client.aclose()
