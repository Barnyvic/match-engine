from __future__ import annotations

from typing import Any

import pandas as pd

from app.pipeline.context_provider import get_context_adjustment


def apply_context_adjustment(row: pd.Series, context_score: int) -> dict[str, float]:
    home = max(0.01, float(row["prob_H"]) + context_score * 0.025)
    away = max(0.01, float(row["prob_A"]) - context_score * 0.025)
    draw = max(0.01, float(row["prob_D"]))
    total = home + draw + away
    return {"prob_H": home / total, "prob_D": draw / total, "prob_A": away / total}


def apply_form_sanity_adjustment(row: pd.Series, probabilities: dict[str, float]) -> dict[str, float]:
    home_form = float(row.get("home_recent_points", 0.0))
    away_form = float(row.get("away_recent_points", 0.0))
    home_goal_diff = float(row.get("home_recent_goal_diff", 0.0))
    away_goal_diff = float(row.get("away_recent_goal_diff", 0.0))
    form_gap = home_form - away_form
    goal_diff_gap = home_goal_diff - away_goal_diff

    # If recent form strongly favors away but model still prefers home, damp the home edge.
    if form_gap <= -0.8 and goal_diff_gap <= -0.6 and probabilities["prob_H"] > probabilities["prob_A"]:
        shift = min(0.08, (abs(form_gap) * 0.04) + (abs(goal_diff_gap) * 0.02))
        adjusted = {
            "prob_H": max(0.01, probabilities["prob_H"] - shift),
            "prob_D": max(0.01, probabilities["prob_D"]),
            "prob_A": max(0.01, probabilities["prob_A"] + shift),
        }
        total = adjusted["prob_H"] + adjusted["prob_D"] + adjusted["prob_A"]
        return {
            "prob_H": adjusted["prob_H"] / total,
            "prob_D": adjusted["prob_D"] / total,
            "prob_A": adjusted["prob_A"] / total,
        }
    return probabilities


def confidence_tier(probabilities: dict[str, float]) -> str:
    top_probability = max(probabilities.values())
    if top_probability >= 0.56:
        return "HIGH"
    if top_probability >= 0.45:
        return "MEDIUM"
    return "LOW"


def combine_fixture_prediction(row: pd.Series) -> dict[str, Any]:
    context = get_context_adjustment(row["home_team"], row["away_team"])
    adjusted = apply_context_adjustment(row, int(context.get("context_score", 0)))
    adjusted = apply_form_sanity_adjustment(row, adjusted)
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
