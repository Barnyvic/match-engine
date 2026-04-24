from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import pandas as pd
import requests

from app.db import get_connection


LEAGUES = {
    "EPL": {
        "league_code": "E0",
        "name": "English Premier League",
        "season_start_years": list(range(2010, 2026)),
    },
    "SERIE_A": {
        "league_code": "I1",
        "name": "Serie A",
        "season_start_years": list(range(2010, 2026)),
    },
    "CHAMPIONS_LEAGUE": {
        "league_code": "CL",
        "name": "UEFA Champions League",
        "season_start_years": [],
        "supported": False,
    },
}


@dataclass(frozen=True)
class SeasonSource:
    league_key: str
    season_code: str
    source_url: str


DEFAULT_HEADERS = {"User-Agent": "match-engine/1.0"}


def season_code_from_year(start_year: int) -> str:
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def build_season_sources(league_key: str = "EPL") -> list[SeasonSource]:
    league = LEAGUES[league_key]
    if not league.get("supported", True):
        return []
    return [
        SeasonSource(
            league_key=league_key,
            season_code=season_code_from_year(start_year),
            source_url=f"https://www.football-data.co.uk/mmz4281/{season_code_from_year(start_year)}/{league['league_code']}.csv",
        )
        for start_year in league["season_start_years"]
    ]


def normalize_match_date(value: object) -> str:
    if pd.isna(value):
        raise ValueError("Missing match date")
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Invalid match date: {value!r}")
    return parsed.strftime("%Y-%m-%d")


def row_hash(*parts: object) -> str:
    joined = "||".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def fetch_csv(source_url: str, timeout: int = 30) -> pd.DataFrame:
    response = requests.get(source_url, timeout=timeout, headers=DEFAULT_HEADERS)
    response.raise_for_status()
    text = response.text.lstrip()
    if text.startswith("<"):
        raise ValueError(f"Expected CSV from {source_url}, received HTML instead.")
    return pd.read_csv(io.StringIO(text))


def transform_matches(raw_df: pd.DataFrame, league_code: str, season_code: str, source_url: str) -> list[tuple]:
    required_columns = ["Date", "HomeTeam", "AwayTeam"]
    missing = [column for column in required_columns if column not in raw_df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")

    records: list[tuple] = []
    for row in raw_df.to_dict(orient="records"):
        match_date = normalize_match_date(row["Date"])
        home_team = str(row["HomeTeam"]).strip()
        away_team = str(row["AwayTeam"]).strip()
        full_time_result = row.get("FTR")
        full_time_home_goals = pd.to_numeric(row.get("FTHG"), errors="coerce")
        full_time_away_goals = pd.to_numeric(row.get("FTAG"), errors="coerce")
        bookmaker_home_odds = pd.to_numeric(row.get("B365H") or row.get("AvgH"), errors="coerce")
        bookmaker_draw_odds = pd.to_numeric(row.get("B365D") or row.get("AvgD"), errors="coerce")
        bookmaker_away_odds = pd.to_numeric(row.get("B365A") or row.get("AvgA"), errors="coerce")
        hashed = row_hash(league_code, season_code, match_date, home_team, away_team)

        records.append(
            (
                league_code,
                season_code,
                match_date,
                home_team,
                away_team,
                None if pd.isna(full_time_home_goals) else int(full_time_home_goals),
                None if pd.isna(full_time_away_goals) else int(full_time_away_goals),
                None if pd.isna(full_time_result) else str(full_time_result),
                None if pd.isna(bookmaker_home_odds) else float(bookmaker_home_odds),
                None if pd.isna(bookmaker_draw_odds) else float(bookmaker_draw_odds),
                None if pd.isna(bookmaker_away_odds) else float(bookmaker_away_odds),
                source_url,
                hashed,
            )
        )
    return records


def record_ingestion_run(
    league_code: str,
    season_code: str,
    source_url: str,
    rows_seen: int,
    rows_inserted: int,
    status: str,
    last_error: str | None = None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO ingestion_runs (
                league_code, season_code, source_url, rows_seen, rows_inserted, status, last_error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (league_code, season_code, source_url, rows_seen, rows_inserted, status, last_error),
        )


def upsert_matches(rows: Iterable[tuple]) -> int:
    inserted = 0
    with get_connection() as connection:
        for row in rows:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO matches (
                    league_code,
                    season_code,
                    match_date,
                    home_team,
                    away_team,
                    full_time_home_goals,
                    full_time_away_goals,
                    full_time_result,
                    bookmaker_home_odds,
                    bookmaker_draw_odds,
                    bookmaker_away_odds,
                    source_url,
                    row_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            inserted += cursor.rowcount
    return inserted


def ingest_season(source: SeasonSource) -> dict[str, object]:
    league_code = LEAGUES[source.league_key]["league_code"]
    try:
        raw_df = fetch_csv(source.source_url)
        rows = transform_matches(raw_df, league_code=league_code, season_code=source.season_code, source_url=source.source_url)
        inserted = upsert_matches(rows)
        record_ingestion_run(league_code, source.season_code, source.source_url, len(rows), inserted, "success")
        return {
            "season_code": source.season_code,
            "rows_seen": len(rows),
            "rows_inserted": inserted,
            "status": "success",
        }
    except Exception as exc:  # pragma: no cover - exercised via runtime failures
        record_ingestion_run(league_code, source.season_code, source.source_url, 0, 0, "failed", str(exc))
        return {"season_code": source.season_code, "rows_seen": 0, "rows_inserted": 0, "status": "failed", "error": str(exc)}


def ingest_league_history(league_key: str = "EPL") -> dict[str, object]:
    if not LEAGUES[league_key].get("supported", True):
        return {
            "league": LEAGUES[league_key]["name"],
            "league_code": LEAGUES[league_key]["league_code"],
            "season_results": [],
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "supported": False,
        }

    results = [ingest_season(source) for source in build_season_sources(league_key)]
    return {
        "league": LEAGUES[league_key]["name"],
        "league_code": LEAGUES[league_key]["league_code"],
        "season_results": results,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "supported": True,
    }


def load_matches_df(league_code: str = "E0") -> pd.DataFrame:
    with get_connection() as connection:
        df = pd.read_sql_query(
            """
            SELECT
                league_code,
                season_code,
                match_date,
                home_team,
                away_team,
                full_time_home_goals,
                full_time_away_goals,
                full_time_result,
                bookmaker_home_odds,
                bookmaker_draw_odds,
                bookmaker_away_odds
            FROM matches
            WHERE league_code = ?
              AND full_time_result IN ('H', 'D', 'A')
            ORDER BY match_date ASC, id ASC
            """,
            connection,
            params=(league_code,),
        )

    if df.empty:
        return df

    df["match_date"] = pd.to_datetime(df["match_date"])
    return df


def fetch_upcoming_fixtures(league_code: str = "E0") -> pd.DataFrame:
    with get_connection() as connection:
        db_fixtures = pd.read_sql_query(
            """
            SELECT
                match_date,
                home_team,
                away_team,
                bookmaker_home_odds,
                bookmaker_draw_odds,
                bookmaker_away_odds
            FROM matches
            WHERE league_code = ?
              AND (full_time_result IS NULL OR full_time_result = '')
            ORDER BY match_date ASC, id ASC
            """,
            connection,
            params=(league_code,),
        )

    if not db_fixtures.empty:
        db_fixtures["match_date"] = pd.to_datetime(db_fixtures["match_date"], errors="coerce")
        return db_fixtures.dropna(subset=["match_date", "home_team", "away_team"])

    matching_key = next((key for key, config in LEAGUES.items() if config["league_code"] == league_code), "EPL")
    sources = build_season_sources(matching_key)
    if not sources:
        return pd.DataFrame(
            columns=[
                "match_date",
                "home_team",
                "away_team",
                "bookmaker_home_odds",
                "bookmaker_draw_odds",
                "bookmaker_away_odds",
            ]
        )

    latest_source = sources[-1]
    raw_df = fetch_csv(latest_source.source_url)
    raw_df["FTR"] = raw_df.get("FTR")
    filtered = raw_df[raw_df["FTR"].isna()].copy()
    if filtered.empty:
        return pd.DataFrame(
            columns=[
                "match_date",
                "home_team",
                "away_team",
                "bookmaker_home_odds",
                "bookmaker_draw_odds",
                "bookmaker_away_odds",
            ]
        )

    filtered["match_date"] = pd.to_datetime(filtered["Date"], dayfirst=True, errors="coerce")
    filtered["bookmaker_home_odds"] = pd.to_numeric(filtered.get("B365H"), errors="coerce")
    filtered["bookmaker_draw_odds"] = pd.to_numeric(filtered.get("B365D"), errors="coerce")
    filtered["bookmaker_away_odds"] = pd.to_numeric(filtered.get("B365A"), errors="coerce")
    filtered = filtered.rename(columns={"HomeTeam": "home_team", "AwayTeam": "away_team"})
    return filtered[
        [
            "match_date",
            "home_team",
            "away_team",
            "bookmaker_home_odds",
            "bookmaker_draw_odds",
            "bookmaker_away_odds",
        ]
    ].dropna(subset=["match_date", "home_team", "away_team"])


def load_league_teams(league_code: str) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT team_name
            FROM (
                SELECT home_team AS team_name
                FROM matches
                WHERE league_code = ?
                UNION
                SELECT away_team AS team_name
                FROM matches
                WHERE league_code = ?
            )
            ORDER BY team_name ASC
            """,
            (league_code, league_code),
        ).fetchall()
    return [row["team_name"] for row in rows]


def load_league_teams_from_source(league_key: str) -> list[str]:
    if league_key not in LEAGUES:
        return []
    sources = build_season_sources(league_key)
    if not sources:
        return []
    latest_source = sources[-1]
    raw_df = fetch_csv(latest_source.source_url)
    if "HomeTeam" not in raw_df.columns or "AwayTeam" not in raw_df.columns:
        return []
    teams = sorted(
        {
            str(team).strip()
            for team in list(raw_df["HomeTeam"].dropna().tolist()) + list(raw_df["AwayTeam"].dropna().tolist())
            if str(team).strip()
        }
    )
    return teams
