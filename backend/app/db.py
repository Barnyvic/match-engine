from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import settings


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_code TEXT NOT NULL,
    season_code TEXT NOT NULL,
    match_date TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    full_time_home_goals INTEGER,
    full_time_away_goals INTEGER,
    full_time_result TEXT,
    bookmaker_home_odds REAL,
    bookmaker_draw_odds REAL,
    bookmaker_away_odds REAL,
    source_url TEXT NOT NULL,
    row_hash TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_matches_league_date
ON matches (league_code, match_date);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_code TEXT NOT NULL,
    season_code TEXT NOT NULL,
    source_url TEXT NOT NULL,
    rows_seen INTEGER NOT NULL DEFAULT 0,
    rows_inserted INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    last_error TEXT,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    ensure_parent(settings.database_path)
    with sqlite3.connect(settings.database_path) as connection:
        connection.executescript(SCHEMA)


@contextmanager
def get_connection() -> sqlite3.Connection:
    init_db()
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()
