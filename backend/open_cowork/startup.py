"""Router registry and startup/shutdown hooks."""

from __future__ import annotations

from fastapi import APIRouter


def routers() -> list[APIRouter]:
    from .routers import admin, auth, chats, connections, users

    return [auth.router, users.router, admin.router, connections.router, chats.router]


def run() -> None:
    """Called once the database is ready."""
    from .db import SessionLocal
    from .providers.registry import seed_connections

    with SessionLocal() as db:
        seed_connections(db)


async def shutdown() -> None:
    """Called when the server stops."""
