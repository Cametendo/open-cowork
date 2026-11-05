"""Admin-editable application settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..app_config import get_config, update_config
from ..db import get_db
from ..deps import get_admin_user
from ..models import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/config")
def read_config(_: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    return get_config(db)


@router.put("/config")
def write_config(body: dict, _: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    try:
        return update_config(db, body)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


class WebSearchTestBody(BaseModel):
    # Unsaved values from the form; anything omitted falls back to what is stored
    engine: str | None = None
    url: str | None = None
    api_key: str | None = None
    query: str = "open source ai"


@router.post("/web-search/test")
async def test_web_search(body: WebSearchTestBody, _: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    from ..app_config import WEB_SEARCH_ENGINES
    from ..websearch import SearchError, load_web_settings, search

    settings = load_web_settings(db)
    if body.engine is not None:
        if body.engine not in WEB_SEARCH_ENGINES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown search engine")
        settings.engine = body.engine
    if body.url is not None:
        settings.url = body.url.strip().rstrip("/")
    if body.api_key:
        settings.api_key = body.api_key.strip()
    try:
        results = await search(settings, body.query, count=3)
    except SearchError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return {"ok": True, "count": len(results), "results": [r.as_dict() for r in results]}
