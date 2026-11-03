"""Router registry and startup/shutdown hooks."""

from __future__ import annotations

from fastapi import APIRouter


def routers() -> list[APIRouter]:
    from .routers import admin, auth, users

    return [auth.router, users.router, admin.router]


def run() -> None:
    """Called once the database is ready."""


async def shutdown() -> None:
    """Called when the server stops."""
