from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import startup
from .app_config import get_config
from .config import VERSION, get_settings
from .db import get_db, init_db
from .models import User

log = logging.getLogger("open_cowork")
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    startup.run()
    log.info("Open Cowork %s ready — data: %s, repos: %s", VERSION, settings.data_dir, settings.repo_dir)
    yield
    await startup.shutdown()


app = FastAPI(title="Open Cowork", version=VERSION, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

for r in startup.routers():
    app.include_router(r)


@app.get("/api/config")
def public_config(db: Session = Depends(get_db)):
    """Unauthenticated bootstrap info for the login screen."""
    cfg = get_config(db)
    user_count = db.query(func.count(User.id)).scalar() or 0
    return {
        "name": cfg["webui_name"],
        "version": VERSION,
        "onboarding": user_count == 0,
        "features": {
            "enable_signup": bool(cfg["enable_signup"]) or user_count == 0,
            "cowork": cfg["cowork_enabled"],
            "github": cfg["github_enabled"],
        },
    }


@app.get("/api/health")
def health():
    return {"status": True, "version": VERSION}


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


# ---------------------------------------------------------------------------
# Single-page frontend
# ---------------------------------------------------------------------------

_FALLBACK_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Open Cowork</title></head>
<body style="font-family:system-ui;background:#0b0b0f;color:#e5e5e5;display:grid;place-items:center;height:100vh">
<div><h1>Open Cowork API is running</h1><p>The frontend has not been built. Run
<code>npm install &amp;&amp; npm run build</code> in <code>frontend/</code>, or use the Vite dev server.</p>
<p><a style="color:#8ab4ff" href="/api/docs">API docs</a></p></div></body></html>"""


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not found")
    root: Path = settings.frontend_dir
    index = root / "index.html"
    if not index.exists():
        return HTMLResponse(_FALLBACK_HTML)
    if full_path:
        candidate = (root / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(root.resolve()):
            headers = {}
            if "/assets/" in f"/{full_path}":
                headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return FileResponse(candidate, headers=headers)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})

