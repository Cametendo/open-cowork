"""Schema migrations: fresh installs, 0.1.0 databases and future upgrades."""

import os
import sqlite3
import textwrap

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from open_cowork.db import Base
from open_cowork.migrate import BASELINE_REVISION, MIGRATIONS_DIR, alembic_config, current_revision, head_revision, run_migrations


def _engine(tmp_path, name="app.db"):
    return create_engine(f"sqlite:///{tmp_path / name}")


def _add_user(engine, email="admin@example.com"):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, name, password_hash, role, settings, created_at, last_active_at) "
                "VALUES (:id, :email, 'Admin', 'x', 'admin', '{}', 0, 0)"
            ),
            {"id": email, "email": email},
        )


def test_models_match_migrations(tmp_path):
    """Fails when models.py changes without a matching migration."""
    engine = _engine(tmp_path)
    assert run_migrations(engine) == head_revision()
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models.py and the migrations differ — add a migration: {diff}"


def test_database_from_0_1_0_is_adopted(tmp_path):
    engine = _engine(tmp_path)
    # Recreate a 0.1.0 database exactly: baseline schema, no migration history
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, BASELINE_REVISION)
        conn.exec_driver_sql("DROP TABLE alembic_version")
    _add_user(engine)
    assert current_revision(engine) is None

    assert run_migrations(engine) == head_revision()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT role FROM users")).scalar_one() == "admin"
    # running again is a no-op
    assert run_migrations(engine) == head_revision()


def test_future_migration_upgrades_existing_data_and_backs_up(tmp_path):
    engine = _engine(tmp_path)
    run_migrations(engine)
    _add_user(engine)
    previous = head_revision()

    extra = tmp_path / "versions"
    extra.mkdir()
    (extra / "9999_add_timezone.py").write_text(
        textwrap.dedent(
            f'''
            import sqlalchemy as sa
            from alembic import op

            revision = "9999"
            down_revision = "{previous}"
            branch_labels = None
            depends_on = None

            def upgrade():
                with op.batch_alter_table("users") as batch:
                    batch.add_column(sa.Column("timezone", sa.String(64), nullable=True))

            def downgrade():
                with op.batch_alter_table("users") as batch:
                    batch.drop_column("timezone")
            '''
        )
    )
    cfg = alembic_config()
    cfg.set_main_option("version_locations", os.pathsep.join([str(MIGRATIONS_DIR / "versions"), str(extra)]))

    assert run_migrations(engine, cfg) == "9999"
    columns = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "timezone" in columns
    with engine.connect() as conn:
        assert conn.execute(text("SELECT email FROM users")).scalar_one() == "admin@example.com"

    backups = list(tmp_path.glob(f"app.backup-{previous}-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as b:
        assert b.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        assert "timezone" not in {r[1] for r in b.execute("PRAGMA table_info(users)")}
