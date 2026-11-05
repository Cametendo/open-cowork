import asyncio
import json

import httpx
import pytest

from conftest import admin_client_with_connection, auth_headers, read_sse, signup
from open_cowork.cowork.tools import Workspace, execute_tool, tool_specs
from open_cowork.websearch import FetchError, SearchError, WebSettings, fetch_page, search
from open_cowork.websearch import fetch as fetch_mod
from open_cowork.websearch.engines import parse_duckduckgo
from open_cowork.websearch.fetch import _is_public, html_to_text


def run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- engines


DDG_HTML = """
<div class="result results_links results_links_deep web-result">
  <h2 class="result__title"><a rel="nofollow" class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa%3Fx%3D1&amp;rut=abc">Example &amp; A</a></h2>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">First <b>snippet</b> text</a>
</div>
<div class="result result--ad"><h2 class="result__title"><a class="result__a"
   href="https://duckduckgo.com/y.js?ad_provider=bing">Ad</a></h2>
  <a class="result__snippet" href="#">Sponsored</a></div>
<div class="result"><h2 class="result__title"><a class="result__a" href="https://direct.example.net/b">Direct B</a></h2>
  <a class="result__snippet" href="x">Second snippet</a></div>
<div class="result"><h2 class="result__title"><a class="result__a" href="https://nosnippet.example/c">No snippet</a></h2></div>
"""


def test_duckduckgo_parser():
    r = parse_duckduckgo(DDG_HTML)
    assert [x.url for x in r] == ["https://example.com/a?x=1", "https://direct.example.net/b", "https://nosnippet.example/c"]
    assert r[0].title == "Example & A" and r[0].snippet == "First snippet text"
    assert r[2].snippet == ""


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_brave_and_tavily_requests():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.host] = request
        if request.url.host == "api.search.brave.com":
            return httpx.Response(200, json={"web": {"results": [
                {"title": "B1", "url": "https://b.example/1", "description": "desc <strong>bold</strong>"},
                {"title": "bad", "url": "ftp://x", "description": ""},
            ]}})
        return httpx.Response(200, json={"results": [{"title": "T1", "url": "https://t.example/1", "content": "tavily text"}]})

    r = run(search(WebSettings(engine="brave", api_key="k-brave"), "hello world", 4, client=_client(handler)))
    assert [(x.title, x.snippet) for x in r] == [("B1", "desc bold")]
    req = seen["api.search.brave.com"]
    assert req.headers["x-subscription-token"] == "k-brave" and req.url.params["q"] == "hello world" and req.url.params["count"] == "4"

    r = run(search(WebSettings(engine="tavily", api_key="tvly-x"), "q", client=_client(handler)))
    assert r[0].url == "https://t.example/1"
    req = seen["api.tavily.com"]
    assert req.headers["authorization"] == "Bearer tvly-x" and json.loads(req.content)["query"] == "q"


def test_engine_errors():
    def denied(_r):
        return httpx.Response(401)

    with pytest.raises(SearchError, match="API key"):
        run(search(WebSettings(engine="brave"), "q"))
    with pytest.raises(SearchError, match="rejected"):
        run(search(WebSettings(engine="brave", api_key="bad"), "q", client=_client(denied)))
    with pytest.raises(SearchError, match="SearXNG URL"):
        run(search(WebSettings(engine="searxng"), "q"))
    with pytest.raises(SearchError, match="empty"):
        run(search(WebSettings(engine="duckduckgo"), "   "))
    with pytest.raises(SearchError, match="refused"):
        run(search(WebSettings(engine="duckduckgo"), "q", client=_client(lambda r: httpx.Response(202, text="anomaly"))))
    with pytest.raises(SearchError, match="HTTP 500"):
        run(search(WebSettings(engine="tavily", api_key="k"), "q", client=_client(lambda r: httpx.Response(500))))


def test_searxng_against_mock_web(mock_web_url):
    r = run(search(WebSettings(engine="searxng", url=mock_web_url + "/"), "embeddings", 5))
    assert [x.title for x in r] == ["Vector Databases 101", "Second result"]  # javascript: result dropped
    assert r[0].snippet == "All about embeddings"


# --------------------------------------------------------------------------- fetch


def test_html_to_text_strips_noise():
    title, text = html_to_text(
        "<html><head><title> T </title><script>x()</script></head><body><nav>menu</nav><h1>Head</h1>"
        "<p>One &amp; two</p><ul><li>a</li><li>b</li></ul><style>p{}</style><footer>foot</footer></body></html>"
    )
    assert title == "T"
    assert "menu" not in text and "foot" not in text and "x()" not in text and "p{}" not in text
    assert "## Head" in text and "One & two" in text and "- a\n- b" in text


@pytest.mark.parametrize("ip,public", [
    ("8.8.8.8", True), ("2606:4700:4700::1111", True),
    ("127.0.0.1", False), ("10.0.0.5", False), ("192.168.1.1", False), ("172.16.0.1", False),
    ("169.254.169.254", False), ("100.100.100.100", False), ("::1", False), ("fe80::1", False),
    ("::ffff:127.0.0.1", False), ("0.0.0.0", False), ("not-an-ip", False),
])
def test_is_public(ip, public):
    assert _is_public(ip) is public


def test_fetch_blocks_private_by_default(mock_web_url):
    with pytest.raises(FetchError, match="not a public internet address"):
        run(fetch_page(mock_web_url + "/page"))
    with pytest.raises(FetchError, match="Only http"):
        run(fetch_page("file:///etc/passwd"))
    with pytest.raises(FetchError, match="Only http"):
        run(fetch_page("ftp://example.com/x"))
    with pytest.raises(FetchError, match="not a public internet address"):
        run(fetch_page("http://localhost:1/"))
    with pytest.raises(FetchError, match="not a public internet address"):
        run(fetch_page("http://169.254.169.254/latest/meta-data/"))


def test_fetch_pages_when_private_allowed(mock_web_url):
    p = run(fetch_page(mock_web_url + "/page", allow_private=True))
    assert p["title"] == "Vector Databases 101"
    assert "nearest neighbours" in p["text"] and "alert" not in p["text"] and "Copyright" not in p["text"]
    assert run(fetch_page(mock_web_url + "/text", allow_private=True))["text"] == "plain text body"
    assert "hello" in run(fetch_page(mock_web_url + "/json", allow_private=True))["text"]
    # redirects are followed and the final URL is reported
    r = run(fetch_page(mock_web_url + "/redirect?to=/text", allow_private=True))
    assert r["url"].endswith("/text") and r["text"] == "plain text body"
    for path, msg in (("/missing", "HTTP 404"), ("/binary", "octet-stream"), ("/loop", "Too many redirects")):
        with pytest.raises(FetchError, match=msg):
            run(fetch_page(mock_web_url + path, allow_private=True))
    big = run(fetch_page(mock_web_url + "/big", allow_private=True, max_chars=1000))
    assert big["truncated"] is True and len(big["text"]) == 1000


def test_every_redirect_hop_is_checked(mock_web_url, monkeypatch):
    # Pretend only the first server's address is public; the redirect target (::1) must still be refused
    monkeypatch.setattr(fetch_mod, "_is_public", lambda ip: ip == "127.0.0.1")
    port = mock_web_url.rsplit(":", 1)[1]
    assert run(fetch_page(mock_web_url + "/text"))["text"] == "plain text body"
    with pytest.raises(FetchError, match="not a public internet address"):
        run(fetch_page(f"{mock_web_url}/redirect?to=http://[::1]:{port}/text"))


# --------------------------------------------------------------------------- tools


def test_web_tools_are_opt_in(tmp_path):
    names = lambda specs: [s["function"]["name"] for s in specs]
    assert "web_search" not in names(tool_specs(True)) and "fetch_url" not in names(tool_specs(True))
    assert {"web_search", "fetch_url"} <= set(names(tool_specs(False, allow_web=True)))
    ws = Workspace(root=tmp_path)  # web disabled
    for name, args in (("web_search", {"query": "x"}), ("fetch_url", {"url": "https://example.com"})):
        r = run(execute_tool(ws, name, args))
        assert r.is_error and "disabled" in r.content


def test_web_tool_results(tmp_path, mock_web_url):
    ws = Workspace(root=tmp_path, web=WebSettings(enabled=True, engine="searxng", url=mock_web_url, allow_private_hosts=True))
    r = run(execute_tool(ws, "web_search", {"query": "vectors"}))
    assert not r.is_error and "[1] Vector Databases 101" in r.content and "untrusted" in r.content
    assert [s["title"] for s in r.meta["sources"]] == ["Vector Databases 101", "Second result"]
    r = run(execute_tool(ws, "fetch_url", {"url": mock_web_url + "/page"}))
    assert not r.is_error and r.content.startswith("Vector Databases 101\n") and "nearest neighbours" in r.content
    # private addresses stay blocked unless the admin allows them
    ws.web.allow_private_hosts = False
    r = run(execute_tool(ws, "fetch_url", {"url": mock_web_url + "/page"}))
    assert r.is_error and "not a public internet address" in r.content
    r = run(execute_tool(ws, "fetch_url", {"url": "nope"}))
    assert r.is_error and "Only http" in r.content


# --------------------------------------------------------------------------- admin + chat + cowork


def configure(client, h, mock_web_url, **extra):
    r = client.put(
        "/api/admin/config",
        json={"web_search_enabled": True, "web_search_engine": "searxng", "web_search_url": mock_web_url, **extra},
        headers=h,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_admin_settings_and_secret_key(client, mock_llm_url):
    h = admin_client_with_connection(client, mock_llm_url)
    cfg = client.get("/api/admin/config", headers=h).json()
    assert cfg["web_search_enabled"] is False and cfg["web_search_engine"] == "duckduckgo" and cfg["web_search_has_key"] is False
    assert client.get("/api/config").json()["features"]["web_search"] is False

    for bad in ({"web_search_engine": "bing"}, {"web_search_result_count": 0}, {"web_search_result_count": 11}, {"web_search_url": "ftp://x"}):
        assert client.put("/api/admin/config", json=bad, headers=h).status_code == 400

    cfg = client.put("/api/admin/config", json={"web_search_enabled": True, "web_search_engine": "brave", "web_search_api_key": " secret-key "}, headers=h).json()
    assert cfg["web_search_has_key"] is True and "secret-key" not in json.dumps(cfg)
    assert client.get("/api/config").json()["features"]["web_search"] is True

    # stored encrypted, decrypted for use
    from open_cowork.db import SessionLocal
    from open_cowork.models import ConfigEntry
    from open_cowork.websearch import load_web_settings

    with SessionLocal() as db:
        assert "secret-key" not in db.get(ConfigEntry, "web_search_api_key").value
        assert load_web_settings(db).api_key == "secret-key"
    # saving other settings keeps the key; an empty string clears it
    assert client.put("/api/admin/config", json={"web_search_result_count": 3}, headers=h).json()["web_search_has_key"] is True
    assert client.put("/api/admin/config", json={"web_search_api_key": ""}, headers=h).json()["web_search_has_key"] is False


def test_admin_test_endpoint_and_permissions(client, mock_llm_url, mock_web_url):
    h = admin_client_with_connection(client, mock_llm_url)
    r = client.post("/api/admin/web-search/test", json={"engine": "searxng", "url": mock_web_url}, headers=h)
    assert r.status_code == 200 and r.json()["count"] == 2 and r.json()["results"][0]["title"] == "Vector Databases 101"
    bad = client.post("/api/admin/web-search/test", json={"engine": "searxng", "url": "http://127.0.0.1:9"}, headers=h)
    assert bad.status_code == 400 and "Could not reach" in bad.json()["detail"]
    assert client.post("/api/admin/web-search/test", json={"engine": "brave"}, headers=h).status_code == 400

    client.put("/api/admin/config", json={"default_user_role": "user"}, headers=h)
    uh = auth_headers(signup(client, email="u@example.com").json()["token"])
    assert client.post("/api/admin/web-search/test", json={}, headers=uh).status_code == 403


def test_chat_with_web_search(client, mock_llm_url, mock_web_url):
    h = admin_client_with_connection(client, mock_llm_url)
    chat = client.post("/api/chats", json={}, headers=h).json()
    url = f"/api/chats/{chat['id']}/messages"
    body = {"model": "mock-llama:latest", "content": "what are vector databases?", "web_search": True}

    # disabled by the admin
    assert client.post(url, json=body, headers=h).status_code == 400

    configure(client, h, mock_web_url)
    with client.stream("POST", url, json=body, headers=h) as r:
        events = read_sse(r)
    types = [e["type"] for e in events]
    assert types.index("searching") < types.index("sources") < types.index("done")
    sources = next(e for e in events if e["type"] == "sources")
    assert sources["query"] == "what are vector databases?" and len(sources["sources"]) == 2
    answer = "".join(e["text"] for e in events if e["type"] == "delta")
    # the (echoing) model saw the results, the instructions and the original question
    assert "[1] Vector Databases 101" in answer and "untrusted" in answer and "User question: what are vector databases?" in answer

    saved = client.get(f"/api/chats/{chat['id']}", headers=h).json()["messages"]
    assert saved[0]["content"] == "what are vector databases?"  # the stored user message is untouched
    assert saved[1]["sources"][0]["title"] == "Vector Databases 101" and saved[1]["search_query"] == "what are vector databases?"

    # without the flag nothing is searched
    with client.stream("POST", url, json={"model": "mock-llama:latest", "content": "plain"}, headers=h) as r:
        events = read_sse(r)
    assert "searching" not in [e["type"] for e in events]

    # engine failure: the answer still arrives, with the error recorded
    configure(client, h, "http://127.0.0.1:9")
    with client.stream("POST", url, json={**body, "content": "again"}, headers=h) as r:
        events = read_sse(r)
    assert any(e["type"] == "search_error" for e in events) and any(e["type"] == "done" for e in events)
    assert next(e for e in events if e["type"] == "done")["message"]["sources"] == []


def collect_run(client, h, sid):
    events = []
    with client.stream("GET", f"/api/cowork/sessions/{sid}/stream", headers=h) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                events.append(ev)
                if ev["type"] == "run_end":
                    break
    return events


def test_cowork_agent_uses_web_tools(client, mock_llm_url, mock_web_url):
    h = admin_client_with_connection(client, mock_llm_url)
    configure(client, h, mock_web_url, web_allow_private_hosts=True)
    prompt = (
        'research '
        '[[tool:web_search {"query": "vector databases"}]]'
        f'[[tool:fetch_url {{"url": "{mock_web_url}/page"}}]]'
        '[[tool:fetch_url {"url": "http://169.254.169.254/"}]]'
    )
    s = client.post("/api/cowork/sessions", json={"prompt": prompt, "model": "mock-llama:latest", "approval_mode": "ask"}, headers=h).json()
    events = collect_run(client, h, s["id"])
    # read-only web tools never wait for approval, even in "ask" mode
    assert not any(e["type"] == "approval_required" for e in events) and events[-1]["status"] == "completed"
    results = [e["message"] for e in events if e["type"] == "tool_result"]
    assert [r["name"] for r in results] == ["web_search", "fetch_url", "fetch_url"]
    assert "[1] Vector Databases 101" in results[0]["content"] and results[0]["meta"]["sources"][0]["title"] == "Vector Databases 101"
    assert "nearest neighbours" in results[1]["content"]
    # 169.254.169.254 is allowed here only because the admin enabled private hosts; the request just fails to connect
    assert results[2]["is_error"]


def test_cowork_web_tools_hidden_when_disabled(client, mock_llm_url):
    h = admin_client_with_connection(client, mock_llm_url)
    prompt = 'x [[tool:web_search {"query": "q"}]]'
    s = client.post("/api/cowork/sessions", json={"prompt": prompt, "model": "mock-llama:latest", "approval_mode": "auto"}, headers=h).json()
    results = [e["message"] for e in collect_run(client, h, s["id"]) if e["type"] == "tool_result"]
    assert results[0]["is_error"] and "disabled" in results[0]["content"]
