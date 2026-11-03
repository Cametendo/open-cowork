"""Static (environment) settings.

Values here come from environment variables and are read once at startup.
Settings that admins can change at runtime (sign-ups, default role, Cowork
limits, ...) live in the database; see ``app_config.py``. Environment values
only seed those on first boot, like Open WebUI's "persistent config".
"""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

# Release images set OPEN_COWORK_VERSION from the git tag; this is the fallback.
VERSION = os.environ.get("OPEN_COWORK_VERSION") or "0.1.0"

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else default.resolve()


class Settings:
    def __init__(self) -> None:
        self.app_name: str = os.environ.get("WEBUI_NAME", "Open Cowork")
        self.host: str = os.environ.get("HOST", "0.0.0.0")
        self.port: int = env_int("PORT", 8080)

        # Directories
        self.data_dir: Path = env_path("DATA_DIR", BACKEND_DIR / "data")
        # Where GitHub repositories are cloned. Kept at the top level so it is
        # easy to find on the host (``./repo`` locally, ``/repo`` in Docker).
        self.repo_dir: Path = env_path("REPO_DIR", PROJECT_ROOT / "repo")
        # Scratch folders for Cowork tasks that are not tied to a repository.
        self.workspace_dir: Path = env_path("WORKSPACE_DIR", PROJECT_ROOT / "workspaces")
        self.frontend_dir: Path = env_path("FRONTEND_DIR", PROJECT_ROOT / "frontend" / "dist")

        for d in (self.data_dir, self.repo_dir, self.workspace_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.database_url: str = os.environ.get("DATABASE_URL") or (
            f"sqlite:///{self.data_dir / 'open-cowork.db'}"
        )
        self.secret_key: str = os.environ.get("WEBUI_SECRET_KEY") or self._load_or_create_secret()
        self.jwt_expires_hours: int = env_int("JWT_EXPIRES_HOURS", 24 * 7)
        cors = os.environ.get("CORS_ALLOW_ORIGINS", "")
        self.cors_origins: list[str] = [o.strip() for o in cors.split(";") if o.strip()]

        # GitHub (override for GitHub Enterprise)
        self.github_api_url: str = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
        self.github_url: str = os.environ.get("GITHUB_URL", "https://github.com").rstrip("/")

        # Seeds for the persistent (DB-backed) config, used on first boot only.
        self.seed_enable_signup: bool = env_bool("ENABLE_SIGNUP", True)
        self.seed_default_user_role: str = os.environ.get("DEFAULT_USER_ROLE", "pending")
        self.seed_enable_ollama: bool = env_bool("ENABLE_OLLAMA_API", True)
        self.seed_ollama_base_url: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.seed_enable_openai: bool = env_bool("ENABLE_OPENAI_API", True)
        self.seed_openai_base_url: str = os.environ.get("OPENAI_API_BASE_URL", "")
        self.seed_openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
        self.seed_cowork_allow_shell: bool = env_bool("COWORK_ALLOW_SHELL", True)

    def _load_or_create_secret(self) -> str:
        path = self.data_dir / ".webui_secret_key"
        if path.exists():
            return path.read_text().strip()
        key = secrets.token_urlsafe(48)
        path.write_text(key)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
