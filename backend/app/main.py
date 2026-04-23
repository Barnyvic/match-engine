from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.services.pipeline_service import (
    clear_pipeline_snapshot_cache,
    get_pipeline_snapshot,
    list_competitions,
    list_teams_for_competition,
    predict_matchup,
)


app = FastAPI(title="match-engine", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def build_pipeline_snapshot(competition: str = "EPL", force_refresh: bool = False) -> dict[str, object]:
    try:
        return get_pipeline_snapshot(competition=competition, force_refresh=force_refresh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {exc}") from exc


@app.get("/api/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/competitions")
def competitions() -> dict[str, object]:
    return {"competitions": list_competitions()}


@app.get("/api/teams")
def teams(competition: str = Query(default="EPL")) -> dict[str, object]:
    try:
        return {"competition": competition, "teams": list_teams_for_competition(competition)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Team loading failed: {exc}") from exc


@app.get("/api/predictions")
def predictions(
    competition: str = Query(default="EPL"),
    force_refresh: bool = Query(default=False),
) -> dict[str, object]:
    snapshot = build_pipeline_snapshot(competition=competition, force_refresh=force_refresh)
    return {
        "competition": snapshot["competition"],
        "league": snapshot["league"],
        "generated_at": snapshot["generated_at"],
        "metrics": snapshot["metrics"],
        "upcoming_predictions": snapshot["upcoming_predictions"],
        "upcoming_fixtures_count": snapshot["upcoming_fixtures_count"],
        "training_rows": snapshot["training_rows"],
        "ingestion": snapshot["ingestion"],
        "teams": snapshot["teams"],
        "timings": snapshot["timings"],
    }


@app.get("/api/backtest")
def backtest(
    competition: str = Query(default="EPL"),
    force_refresh: bool = Query(default=False),
) -> dict[str, object]:
    snapshot = build_pipeline_snapshot(competition=competition, force_refresh=force_refresh)
    return {
        "competition": snapshot["competition"],
        "league": snapshot["league"],
        "generated_at": snapshot["generated_at"],
        "metrics": snapshot["metrics"],
        "backtest": snapshot["backtest"],
        "timings": snapshot["timings"],
    }


@app.get("/api/matchup")
def matchup(
    competition: str = Query(default="EPL"),
    home_team: str = Query(...),
    away_team: str = Query(...),
) -> dict[str, object]:
    try:
        return predict_matchup(competition=competition, home_team=home_team, away_team=away_team)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Matchup prediction failed: {exc}") from exc


@app.post("/api/refresh")
def refresh(competition: str = Query(default="EPL")) -> dict[str, object]:
    clear_pipeline_snapshot_cache(competition=competition)
    snapshot = build_pipeline_snapshot(competition=competition, force_refresh=True)
    return {
        "status": "refreshed",
        "competition": snapshot["competition"],
        "generated_at": snapshot["generated_at"],
        "upcoming_fixtures_count": snapshot["upcoming_fixtures_count"],
        "training_rows": snapshot["training_rows"],
        "timings": snapshot["timings"],
    }
