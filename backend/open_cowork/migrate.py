"""Database schema upgrades, applied automatically on startup.

Every schema change ships as an Alembic revision in ``migrations/versions``.
On startup the database is brought to the newest revision, so updating to a new
image (or ``git pull`` + restart) upgrades existing data instead of breaking.

Before an existing SQLite database is upgraded, a copy is written next to it
(``open-cowork.backup-<revision>-<timestamp>.db``); the five newest are kept.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
# The schema shipped in 0.1.0, before migrations existed
BASELINE_REVISION = "0001"
KEEP_BACKUPS = 5


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("path_separator", "os")
    return cfg


def head_revision(cfg: Config | None = None) -> str | None:
    return ScriptDirectory.from_config(cfg or alembic_config()).get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def backup_sqlite(engine: Engine, label: str) -> Path | None:
    """Copy a SQLite database with the online backup API. Returns the backup path."""
    url = engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    src = Path(url.database)
    if not src.exists() or src.stat().st_size == 0:
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = src.with_name(f"{src.stem}.backup-{label}-{stamp}{src.suffix}")
    with sqlite3.connect(src) as source, sqlite3.connect(dest) as target:
        source.backup(target)
    backups = sorted(src.parent.glob(f"{src.stem}.backup-*{src.suffix}"), key=lambda p: p.stat().st_mtime)
    for old in backups[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)
    return dest


def run_migrations(engine: Engine, cfg: Config | None = None) -> str | None:
    """Bring the database schema up to date. Returns the revision it ends on."""
    cfg = cfg or alembic_config()
    head = head_revision(cfg)
    tables = set(inspect(engine).get_table_names())
    current = current_revision(engine)

    if current is None and "users" in tables:
        # Created by 0.1.0 (before migrations): that schema is the baseline revision.
        log.info("Existing database without migration history; marking it as revision %s", BASELINE_REVISION)
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.stamp(cfg, BASELINE_REVISION)
        current = BASELINE_REVISION

    if current == head:
        return current

    if current is not None:
        backup = backup_sqlite(engine, current)
        if backup:
            log.warning("Upgrading database from %s to %s (backup: %s)", current, head, backup)
    else:
        log.info("Creating database schema (revision %s)", head)

    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    return current_revision(engine)
