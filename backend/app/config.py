from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BASE_DIR.parent


def parse_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_env_file(env_path: Path) -> None:
    for key, value in parse_env_file(env_path).items():
        os.environ.setdefault(key, value)


def get_runtime_setting(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key)
    if value:
        return value
    return parse_env_file(PROJECT_DIR / ".env").get(key, default)


load_env_file(PROJECT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    database_path: Path = PROJECT_DIR / "database.sqlite3"
    data_dir: Path = PROJECT_DIR / "data"
    reports_dir: Path = PROJECT_DIR / "reports"
    groq_api_key: str | None = get_runtime_setting("GROQ_API_KEY")
    frontend_origin: str = get_runtime_setting("FRONTEND_ORIGIN", "http://localhost:3000") or "http://localhost:3000"
    api_host: str = get_runtime_setting("API_HOST", "0.0.0.0") or "0.0.0.0"
    api_port: int = int(get_runtime_setting("API_PORT", "8000") or "8000")
    snapshot_ttl_seconds: int = int(get_runtime_setting("SNAPSHOT_TTL_SECONDS", "900") or "900")


settings = Settings()
