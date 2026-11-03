"""Alembic environment.

At runtime ``open_cowork.migrate.run_migrations`` hands us a live connection via
``config.attributes["connection"]``. When run from the ``alembic`` CLI (to create
a new revision), we connect with the app's configured database instead.
"""

from __future__ import annotations

from alembic import context

from open_cowork import models  # noqa: F401  (registers tables on Base.metadata)
from open_cowork.db import Base, engine

target_metadata = Base.metadata


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't ALTER most things in place; batch mode recreates tables safely
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    with engine.connect() as conn:
        _run(conn)
        conn.commit()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
