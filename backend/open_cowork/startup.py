"""Router registry and startup/shutdown hooks."""

from __future__ import annotations

from fastapi import APIRouter


def routers() -> list[APIRouter]:
    from .routers import admin, auth, chats, connections, cowork, github, users

    return [auth.router, users.router, admin.router, connections.router, chats.router, cowork.router, github.router]


def run() -> None:
    """Called once the database is ready."""
    from .db import SessionLocal
    from .models import CoworkSession
    from .providers.registry import seed_connections

    with SessionLocal() as db:
        seed_connections(db)
        # Runs don't survive a restart
        db.query(CoworkSession).filter(CoworkSession.status == "running").update({"status": "idle"})
        db.commit()


async def shutdown() -> None:
    """Called when the server stops."""
    from .cowork.runner import manager

    await manager.shutdown()
