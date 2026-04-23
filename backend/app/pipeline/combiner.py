from __future__ import annotations

from typing import Any

import pandas as pd

from app.pipeline.llm_layer import groq_context_adjustment


def apply_context_adjustment(row: pd.Series, context_score: int) -> dict[str, float]:
    home = max(0.01, float(row["prob_H"]) + context_score * 0.025)
    away = max(0.01, float(row["prob_A"]) - context_score * 0.025)
    draw = max(0.01, float(row["prob_D"]))
    total = home + draw + away
    return {"prob_H": home / total, "prob_D": draw / total, "prob_A": away / total}


def confidence_tier(probabilities: dict[str, float]) -> str:
    top_probability = max(probabilities.values())
    if top_probability >= 0.56:
        return "HIGH"
    if top_probability >= 0.45:
        return "MEDIUM"
    return "LOW"


def combine_fixture_prediction(row: pd.Series) -> dict[str, Any]:
    context = groq_context_adjustment(row["home_team"], row["away_team"])
    adjusted = apply_context_adjustment(row, int(context.get("context_score", 0)))
    predicted_result = max(adjusted, key=adjusted.get).replace("prob_", "")
    return {
        "match_date": pd.Timestamp(row["match_date"]).strftime("%Y-%m-%d"),
        "home_team": row["home_team"],
        "away_team": row["away_team"],
        "base_probabilities": {
            "home": round(float(row["prob_H"]), 4),
            "draw": round(float(row["prob_D"]), 4),
            "away": round(float(row["prob_A"]), 4),
        },
        "adjusted_probabilities": {
            "home": round(adjusted["prob_H"], 4),
            "draw": round(adjusted["prob_D"], 4),
            "away": round(adjusted["prob_A"], 4),
        },
        "predicted_result": predicted_result,
        "confidence_tier": confidence_tier(adjusted),
        "bookmaker_odds": {
            "home": row.get("bookmaker_home_odds"),
            "draw": row.get("bookmaker_draw_odds"),
            "away": row.get("bookmaker_away_odds"),
        },
        "context": context,
    }
