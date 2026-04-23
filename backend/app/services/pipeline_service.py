from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from time import perf_counter
from typing import Any

import pandas as pd

from app.config import settings
from app.db import init_db
from app.pipeline.backtest import run_backtest
from app.pipeline.combiner import combine_fixture_prediction
from app.pipeline.data_pipeline import LEAGUES, fetch_upcoming_fixtures, ingest_league_history, load_league_teams, load_matches_df
from app.pipeline.model import (
    build_feature_frame,
    build_fixture_features,
    build_matchup_feature_row,
    build_team_state_snapshot,
    score_fixtures,
    train_latest_model,
    walk_forward_validation,
)


@dataclass
class SnapshotCache:
    payloads: dict[str, dict[str, Any]] | None = None
    created_at: dict[str, datetime] | None = None


_cache = SnapshotCache(payloads={}, created_at={})
_lock = Lock()


def _resolve_league(competition: str) -> dict[str, Any]:
    if competition not in LEAGUES:
        raise ValueError(f"Unsupported competition: {competition}")
    league = LEAGUES[competition]
    if not league.get("supported", True):
        raise ValueError(f"{league['name']} is not supported yet by the current data source.")
    return league


def _build_snapshot(competition: str) -> dict[str, Any]:
    init_db()
    league = _resolve_league(competition)
    league_code = league["league_code"]
    timings: dict[str, float] = {}

    started = perf_counter()
    ingest_summary = ingest_league_history(competition)
    timings["ingestion_seconds"] = round(perf_counter() - started, 3)

    started = perf_counter()
    matches_df = load_matches_df(league_code)
    if matches_df.empty:
        raise RuntimeError("No historical matches available after ingestion.")
    features_df = build_feature_frame(matches_df)
    validation = walk_forward_validation(features_df)
    trained = train_latest_model(features_df)
    timings["training_seconds"] = round(perf_counter() - started, 3)

    started = perf_counter()
    fixtures_df = fetch_upcoming_fixtures(league_code)
    fixture_features = build_fixture_features(features_df, fixtures_df)
    fixture_scores = score_fixtures(trained, fixture_features)
    upcoming_predictions = [combine_fixture_prediction(row) for _, row in fixture_scores.iterrows()]
    timings["fixture_scoring_seconds"] = round(perf_counter() - started, 3)

    started = perf_counter()
    backtest = run_backtest(validation["predictions"])
    timings["backtest_seconds"] = round(perf_counter() - started, 3)

    return {
        "competition": competition,
        "league": league["name"],
        "league_code": league_code,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "ingestion": ingest_summary,
        "training_rows": trained["training_rows"],
        "metrics": validation["metrics"],
        "backtest": backtest,
        "upcoming_predictions": upcoming_predictions,
        "upcoming_fixtures_count": int(len(upcoming_predictions)),
        "teams": load_league_teams(league_code),
        "history_features": features_df,
        "matches_df": matches_df,
        "trained": trained,
        "timings": timings,
    }


def _serialize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in snapshot.items()
        if key not in {"history_features", "matches_df", "trained"}
    }


def get_pipeline_snapshot(competition: str, force_refresh: bool = False) -> dict[str, Any]:
    with _lock:
        now = datetime.utcnow()
        created_at = (_cache.created_at or {}).get(competition)
        expires_at = (created_at + timedelta(seconds=settings.snapshot_ttl_seconds)) if created_at else None
        existing = (_cache.payloads or {}).get(competition)
        if not force_refresh and existing is not None and expires_at and now < expires_at:
            return existing

        payload = _build_snapshot(competition)
        (_cache.payloads or {})[competition] = payload
        (_cache.created_at or {})[competition] = now
        return payload


def clear_pipeline_snapshot_cache(competition: str | None = None) -> None:
    with _lock:
        if competition is None:
            _cache.payloads = {}
            _cache.created_at = {}
            return
        (_cache.payloads or {}).pop(competition, None)
        (_cache.created_at or {}).pop(competition, None)


def list_competitions() -> list[dict[str, Any]]:
    competitions: list[dict[str, Any]] = []
    for key, league in LEAGUES.items():
        competitions.append(
            {
                "key": key,
                "name": league["name"],
                "league_code": league["league_code"],
                "supported": league.get("supported", True),
            }
        )
    return competitions


def list_teams_for_competition(competition: str) -> list[str]:
    snapshot = get_pipeline_snapshot(competition)
    return snapshot["teams"]


def _result_label(code: str) -> str:
    return {"H": "Home Win", "D": "Draw", "A": "Away Win"}[code]


def _recent_form(history: pd.DataFrame, team: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = history[(history["home_team"] == team) | (history["away_team"] == team)].sort_values("match_date").tail(limit)
    form: list[dict[str, Any]] = []
    for row in rows.to_dict(orient="records"):
        is_home = row["home_team"] == team
        goals_for = row["full_time_home_goals"] if is_home else row["full_time_away_goals"]
        goals_against = row["full_time_away_goals"] if is_home else row["full_time_home_goals"]
        result = row["full_time_result"]
        outcome = "W" if (is_home and result == "H") or ((not is_home) and result == "A") else "D" if result == "D" else "L"
        form.append(
            {
                "date": pd.Timestamp(row["match_date"]).strftime("%Y-%m-%d"),
                "opponent": row["away_team"] if is_home else row["home_team"],
                "outcome": outcome,
                "goals_for": int(goals_for),
                "goals_against": int(goals_against),
            }
        )
    return form


def _head_to_head(history: pd.DataFrame, home_team: str, away_team: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = history[
        ((history["home_team"] == home_team) & (history["away_team"] == away_team))
        | ((history["home_team"] == away_team) & (history["away_team"] == home_team))
    ].sort_values("match_date").tail(limit)
    items: list[dict[str, Any]] = []
    for row in rows.to_dict(orient="records"):
        items.append(
            {
                "date": pd.Timestamp(row["match_date"]).strftime("%Y-%m-%d"),
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "score": f"{int(row['full_time_home_goals'])}-{int(row['full_time_away_goals'])}",
                "result": _result_label(row["full_time_result"]),
            }
        )
    return items


def predict_matchup(competition: str, home_team: str, away_team: str) -> dict[str, Any]:
    if home_team == away_team:
        raise ValueError("Home and away teams must be different.")

    snapshot = get_pipeline_snapshot(competition)
    teams = snapshot["teams"]
    if home_team not in teams:
        raise ValueError(f"{home_team} is not available in {snapshot['league']}.")
    if away_team not in teams:
        raise ValueError(f"{away_team} is not available in {snapshot['league']}.")

    matchup_features = build_matchup_feature_row(snapshot["history_features"], home_team, away_team)
    scored = score_fixtures(snapshot["trained"], matchup_features)
    prediction = combine_fixture_prediction(scored.iloc[0])
    _, states, _ = build_team_state_snapshot(snapshot["history_features"])
    home_state = states.get(home_team)
    away_state = states.get(away_team)

    probability_chart = [
        {"label": "Home Win", "value": prediction["adjusted_probabilities"]["home"]},
        {"label": "Draw", "value": prediction["adjusted_probabilities"]["draw"]},
        {"label": "Away Win", "value": prediction["adjusted_probabilities"]["away"]},
    ]

    summary = {
        "headline": f"{home_team} vs {away_team}",
        "predicted_outcome": _result_label(prediction["predicted_result"]),
        "confidence_tier": prediction["confidence_tier"],
        "competition": snapshot["league"],
    }

    stats = {
        "home_elo": round(home_state.current_elo, 1) if home_state else 1500.0,
        "away_elo": round(away_state.current_elo, 1) if away_state else 1500.0,
        "elo_gap": round((home_state.current_elo if home_state else 1500.0) - (away_state.current_elo if away_state else 1500.0), 1),
        "home_form_points": sum(home_state.points_last5) if home_state else 0,
        "away_form_points": sum(away_state.points_last5) if away_state else 0,
        "home_rest_days": int(scored.iloc[0]["home_rest_days"]),
        "away_rest_days": int(scored.iloc[0]["away_rest_days"]),
    }

    return {
        "generated_at": snapshot["generated_at"],
        "competition": competition,
        "league": snapshot["league"],
        "summary": summary,
        "prediction": prediction,
        "probability_chart": probability_chart,
        "stats": stats,
        "form": {
            "home_team": _recent_form(snapshot["matches_df"], home_team),
            "away_team": _recent_form(snapshot["matches_df"], away_team),
        },
        "head_to_head": _head_to_head(snapshot["matches_df"], home_team, away_team),
    }
