from __future__ import annotations

from typing import Any

import pandas as pd


OUTCOME_TO_COLUMN = {
    "H": ("prob_H", "bookmaker_home_odds"),
    "D": ("prob_D", "bookmaker_draw_odds"),
    "A": ("prob_A", "bookmaker_away_odds"),
}


def overround_from_row(row: pd.Series) -> float:
    inverse_sum = 0.0
    for _, odds_column in OUTCOME_TO_COLUMN.values():
        odds = row.get(odds_column)
        if odds and odds > 0:
            inverse_sum += 1.0 / float(odds)
    return inverse_sum


def edge_for_outcome(row: pd.Series, outcome: str) -> float:
    prob_column, odds_column = OUTCOME_TO_COLUMN[outcome]
    odds = row.get(odds_column)
    if not odds or odds <= 0:
        return -1.0
    return float(row[prob_column]) - (1.0 / float(odds))


def run_backtest(predictions: pd.DataFrame, edge_threshold: float = 0.03) -> dict[str, Any]:
    if predictions.empty:
        return {"bets": [], "summary": {"bets_placed": 0, "roi": 0.0, "win_rate": 0.0}}

    bets: list[dict[str, Any]] = []
    bankroll = 0.0
    wins = 0

    for row in predictions.to_dict(orient="records"):
        series = pd.Series(row)
        edges = {outcome: edge_for_outcome(series, outcome) for outcome in OUTCOME_TO_COLUMN}
        best_outcome = max(edges, key=edges.get)
        best_edge = edges[best_outcome]
        if best_edge < edge_threshold:
            continue

        _, odds_column = OUTCOME_TO_COLUMN[best_outcome]
        odds = float(series[odds_column])
        profit = odds - 1.0 if series["result"] == best_outcome else -1.0
        bankroll += profit
        if profit > 0:
            wins += 1

        bets.append(
            {
                "match_date": pd.Timestamp(series["match_date"]).strftime("%Y-%m-%d"),
                "home_team": series["home_team"],
                "away_team": series["away_team"],
                "bet_on": best_outcome,
                "edge": round(best_edge, 4),
                "odds": odds,
                "result": series["result"],
                "profit": round(profit, 4),
                "bookmaker_margin": round(overround_from_row(series) - 1.0, 4),
            }
        )

    total_bets = len(bets)
    roi = bankroll / total_bets if total_bets else 0.0
    win_rate = wins / total_bets if total_bets else 0.0
    return {
        "bets": bets,
        "summary": {
            "bets_placed": total_bets,
            "total_profit_units": round(bankroll, 4),
            "roi": round(roi, 4),
            "win_rate": round(win_rate, 4),
            "edge_threshold": edge_threshold,
        },
    }
