from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler

from app.pipeline.elo import EloTracker


RESULT_TO_INT = {"H": 0, "D": 1, "A": 2}
INT_TO_RESULT = {value: key for key, value in RESULT_TO_INT.items()}
CLASS_ORDER = ["H", "D", "A"]
FEATURE_COLUMNS = [
    "elo_diff",
    "home_recent_points",
    "away_recent_points",
    "home_recent_goal_diff",
    "away_recent_goal_diff",
    "home_rest_days",
    "away_rest_days",
    "implied_home_edge",
    "implied_draw_edge",
    "implied_away_edge",
]


@dataclass
class TeamState:
    matches_played: int = 0
    points_last5: list[int] | None = None
    goal_diff_last5: list[int] | None = None
    last_match_date: pd.Timestamp | None = None
    current_elo: float = 1500.0

    def __post_init__(self) -> None:
        self.points_last5 = self.points_last5 or []
        self.goal_diff_last5 = self.goal_diff_last5 or []


def rolling_average(values: list[int]) -> float:
    return float(np.mean(values)) if values else 0.0


def implied_probability(odds: float | None) -> float:
    if not odds or odds <= 0:
        return 0.0
    return 1.0 / odds


def build_feature_frame(matches_df: pd.DataFrame) -> pd.DataFrame:
    if matches_df.empty:
        return matches_df.copy()

    tracker = EloTracker()
    states: dict[str, TeamState] = {}
    feature_rows: list[dict[str, object]] = []

    for match in matches_df.sort_values(["match_date", "home_team", "away_team"]).to_dict(orient="records"):
        home_team = match["home_team"]
        away_team = match["away_team"]
        match_date = pd.Timestamp(match["match_date"])
        home_state = states.setdefault(home_team, TeamState())
        away_state = states.setdefault(away_team, TeamState())

        pre = {
            "pre_home_elo": tracker.get_rating(home_team),
            "pre_away_elo": tracker.get_rating(away_team),
        }

        home_rest_days = (
            (match_date - home_state.last_match_date).days if home_state.last_match_date is not None else 7
        )
        away_rest_days = (
            (match_date - away_state.last_match_date).days if away_state.last_match_date is not None else 7
        )

        home_implied = implied_probability(match["bookmaker_home_odds"])
        draw_implied = implied_probability(match["bookmaker_draw_odds"])
        away_implied = implied_probability(match["bookmaker_away_odds"])
        overround = home_implied + draw_implied + away_implied
        if overround > 0:
            home_implied /= overround
            draw_implied /= overround
            away_implied /= overround

        feature_rows.append(
            {
                "match_date": match_date,
                "season_code": match["season_code"],
                "home_team": home_team,
                "away_team": away_team,
                "result": match["full_time_result"],
                "target": RESULT_TO_INT[match["full_time_result"]],
                "elo_diff": pre["pre_home_elo"] - pre["pre_away_elo"],
                "home_recent_points": rolling_average(home_state.points_last5),
                "away_recent_points": rolling_average(away_state.points_last5),
                "home_recent_goal_diff": rolling_average(home_state.goal_diff_last5),
                "away_recent_goal_diff": rolling_average(away_state.goal_diff_last5),
                "home_rest_days": float(home_rest_days),
                "away_rest_days": float(away_rest_days),
                "bookmaker_home_odds": match["bookmaker_home_odds"],
                "bookmaker_draw_odds": match["bookmaker_draw_odds"],
                "bookmaker_away_odds": match["bookmaker_away_odds"],
                "implied_home_edge": home_implied,
                "implied_draw_edge": draw_implied,
                "implied_away_edge": away_implied,
                "full_time_home_goals": match["full_time_home_goals"],
                "full_time_away_goals": match["full_time_away_goals"],
            }
        )

        tracker.rate_match(home_team, away_team, match["full_time_result"])

        home_points = 3 if match["full_time_result"] == "H" else 1 if match["full_time_result"] == "D" else 0
        away_points = 3 if match["full_time_result"] == "A" else 1 if match["full_time_result"] == "D" else 0
        goal_diff = int(match["full_time_home_goals"] - match["full_time_away_goals"])

        home_state.points_last5 = (home_state.points_last5 + [home_points])[-5:]
        away_state.points_last5 = (away_state.points_last5 + [away_points])[-5:]
        home_state.goal_diff_last5 = (home_state.goal_diff_last5 + [goal_diff])[-5:]
        away_state.goal_diff_last5 = (away_state.goal_diff_last5 + [-goal_diff])[-5:]
        home_state.matches_played += 1
        away_state.matches_played += 1
        home_state.last_match_date = match_date
        away_state.last_match_date = match_date

    return pd.DataFrame(feature_rows)


def build_team_state_snapshot(
    history_features: pd.DataFrame,
) -> tuple[EloTracker, dict[str, TeamState], pd.DataFrame]:
    tracker = EloTracker()
    states: dict[str, TeamState] = {}
    ordered_history = history_features.sort_values("match_date")

    for match in ordered_history.to_dict(orient="records"):
        home_team = match["home_team"]
        away_team = match["away_team"]
        home_state = states.setdefault(home_team, TeamState())
        away_state = states.setdefault(away_team, TeamState())
        match_date = pd.Timestamp(match["match_date"])

        tracker.rate_match(home_team, away_team, match["result"])
        home_points = 3 if match["result"] == "H" else 1 if match["result"] == "D" else 0
        away_points = 3 if match["result"] == "A" else 1 if match["result"] == "D" else 0
        goal_diff = int(match["full_time_home_goals"] - match["full_time_away_goals"])

        home_state.points_last5 = (home_state.points_last5 + [home_points])[-5:]
        away_state.points_last5 = (away_state.points_last5 + [away_points])[-5:]
        home_state.goal_diff_last5 = (home_state.goal_diff_last5 + [goal_diff])[-5:]
        away_state.goal_diff_last5 = (away_state.goal_diff_last5 + [-goal_diff])[-5:]
        home_state.last_match_date = match_date
        away_state.last_match_date = match_date
        home_state.current_elo = tracker.get_rating(home_team)
        away_state.current_elo = tracker.get_rating(away_team)
        home_state.matches_played += 1
        away_state.matches_played += 1

    return tracker, states, ordered_history


def calibration_bins(probs: np.ndarray, actuals: np.ndarray, class_index: int, bins: int = 10) -> list[dict[str, float]]:
    class_probs = probs[:, class_index]
    class_actuals = (actuals == class_index).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    points: list[dict[str, float]] = []
    for lower, upper in zip(edges[:-1], edges[1:]):
        mask = (class_probs >= lower) & (class_probs < upper if upper < 1 else class_probs <= upper)
        if not mask.any():
            continue
        points.append(
            {
                "bin_start": float(lower),
                "bin_end": float(upper),
                "predicted": float(class_probs[mask].mean()),
                "actual": float(class_actuals[mask].mean()),
                "count": int(mask.sum()),
            }
        )
    return points


def walk_forward_validation(
    features_df: pd.DataFrame,
    min_train_matches: int = 380 * 3,
    step_size: int = 50,
) -> dict[str, object]:
    clean = features_df.dropna(subset=FEATURE_COLUMNS + ["target"]).reset_index(drop=True)
    if len(clean) <= min_train_matches + step_size:
        raise ValueError("Not enough matches for walk-forward validation")

    predictions: list[pd.DataFrame] = []
    scaler = StandardScaler()

    for split_start in range(min_train_matches, len(clean), step_size):
        train = clean.iloc[:split_start]
        test = clean.iloc[split_start : min(split_start + step_size, len(clean))]
        if test.empty:
            continue

        x_train = scaler.fit_transform(train[FEATURE_COLUMNS])
        x_test = scaler.transform(test[FEATURE_COLUMNS])

        model = LogisticRegression(max_iter=300)
        model.fit(x_train, train["target"])
        calibrated = CalibratedClassifierCV(estimator=model, method="sigmoid", cv=3)
        calibrated.fit(x_train, train["target"])
        probs = calibrated.predict_proba(x_test)

        batch = test[
            [
                "match_date",
                "home_team",
                "away_team",
                "result",
                "target",
                "bookmaker_home_odds",
                "bookmaker_draw_odds",
                "bookmaker_away_odds",
            ]
        ].copy()
        for index, code in enumerate(CLASS_ORDER):
            batch[f"prob_{code}"] = probs[:, index]
        batch["predicted_result"] = [CLASS_ORDER[int(np.argmax(row))] for row in probs]
        predictions.append(batch)

    combined = pd.concat(predictions, ignore_index=True)
    probs = combined[[f"prob_{code}" for code in CLASS_ORDER]].to_numpy()
    actuals = combined["target"].to_numpy()
    metrics = {
        "matches_scored": int(len(combined)),
        "log_loss": float(log_loss(actuals, probs, labels=[0, 1, 2])),
        "accuracy": float((combined["predicted_result"] == combined["result"]).mean()),
        "calibration": {code: calibration_bins(probs, actuals, RESULT_TO_INT[code]) for code in CLASS_ORDER},
    }
    return {"metrics": metrics, "predictions": combined, "feature_columns": FEATURE_COLUMNS}


def train_latest_model(features_df: pd.DataFrame) -> dict[str, object]:
    clean = features_df.dropna(subset=FEATURE_COLUMNS + ["target"]).reset_index(drop=True)
    scaler = StandardScaler()
    x = scaler.fit_transform(clean[FEATURE_COLUMNS])
    model = LogisticRegression(max_iter=300)
    model.fit(x, clean["target"])
    calibrated_model = CalibratedClassifierCV(estimator=model, method="sigmoid", cv=3)
    calibrated_model.fit(x, clean["target"])
    return {
        "model": model,
        "calibrated_model": calibrated_model,
        "scaler": scaler,
        "training_rows": int(len(clean)),
    }


def build_fixture_features(history_features: pd.DataFrame, fixtures_df: pd.DataFrame) -> pd.DataFrame:
    if fixtures_df.empty:
        return fixtures_df.copy()

    tracker, states, _ = build_team_state_snapshot(history_features)

    rows: list[dict[str, object]] = []
    for fixture in fixtures_df.sort_values("match_date").to_dict(orient="records"):
        home_team = fixture["home_team"]
        away_team = fixture["away_team"]
        home_state = states.setdefault(home_team, TeamState())
        away_state = states.setdefault(away_team, TeamState())
        match_date = pd.Timestamp(fixture["match_date"])

        home_implied = implied_probability(fixture["bookmaker_home_odds"])
        draw_implied = implied_probability(fixture["bookmaker_draw_odds"])
        away_implied = implied_probability(fixture["bookmaker_away_odds"])
        overround = home_implied + draw_implied + away_implied
        if overround > 0:
            home_implied /= overround
            draw_implied /= overround
            away_implied /= overround

        rows.append(
            {
                "match_date": match_date,
                "home_team": home_team,
                "away_team": away_team,
                "elo_diff": tracker.get_rating(home_team) - tracker.get_rating(away_team),
                "home_recent_points": rolling_average(home_state.points_last5),
                "away_recent_points": rolling_average(away_state.points_last5),
                "home_recent_goal_diff": rolling_average(home_state.goal_diff_last5),
                "away_recent_goal_diff": rolling_average(away_state.goal_diff_last5),
                "home_rest_days": float((match_date - home_state.last_match_date).days if home_state.last_match_date else 7),
                "away_rest_days": float((match_date - away_state.last_match_date).days if away_state.last_match_date else 7),
                "bookmaker_home_odds": fixture["bookmaker_home_odds"],
                "bookmaker_draw_odds": fixture["bookmaker_draw_odds"],
                "bookmaker_away_odds": fixture["bookmaker_away_odds"],
                "implied_home_edge": home_implied,
                "implied_draw_edge": draw_implied,
                "implied_away_edge": away_implied,
            }
        )
    return pd.DataFrame(rows)


def build_matchup_feature_row(
    history_features: pd.DataFrame,
    home_team: str,
    away_team: str,
    match_date: pd.Timestamp | None = None,
    bookmaker_home_odds: float | None = None,
    bookmaker_draw_odds: float | None = None,
    bookmaker_away_odds: float | None = None,
) -> pd.DataFrame:
    tracker, states, _ = build_team_state_snapshot(history_features)
    home_state = states.setdefault(home_team, TeamState(current_elo=tracker.get_rating(home_team)))
    away_state = states.setdefault(away_team, TeamState(current_elo=tracker.get_rating(away_team)))
    default_match_date = pd.Timestamp.utcnow().tz_localize(None).normalize()
    match_date = pd.Timestamp(match_date or default_match_date).tz_localize(None)

    home_implied = implied_probability(bookmaker_home_odds)
    draw_implied = implied_probability(bookmaker_draw_odds)
    away_implied = implied_probability(bookmaker_away_odds)
    overround = home_implied + draw_implied + away_implied
    if overround > 0:
        home_implied /= overround
        draw_implied /= overround
        away_implied /= overround

    return pd.DataFrame(
        [
            {
                "match_date": match_date,
                "home_team": home_team,
                "away_team": away_team,
                "elo_diff": tracker.get_rating(home_team) - tracker.get_rating(away_team),
                "home_recent_points": rolling_average(home_state.points_last5),
                "away_recent_points": rolling_average(away_state.points_last5),
                "home_recent_goal_diff": rolling_average(home_state.goal_diff_last5),
                "away_recent_goal_diff": rolling_average(away_state.goal_diff_last5),
                "home_rest_days": float((match_date - home_state.last_match_date).days if home_state.last_match_date else 7),
                "away_rest_days": float((match_date - away_state.last_match_date).days if away_state.last_match_date else 7),
                "bookmaker_home_odds": bookmaker_home_odds,
                "bookmaker_draw_odds": bookmaker_draw_odds,
                "bookmaker_away_odds": bookmaker_away_odds,
                "implied_home_edge": home_implied,
                "implied_draw_edge": draw_implied,
                "implied_away_edge": away_implied,
            }
        ]
    )


def score_fixtures(trained: dict[str, object], fixture_features: pd.DataFrame) -> pd.DataFrame:
    if fixture_features.empty:
        return fixture_features.copy()

    x = trained["scaler"].transform(fixture_features[FEATURE_COLUMNS])
    predictor = trained.get("calibrated_model") or trained["model"]
    probs = predictor.predict_proba(x)
    scored = fixture_features.copy()
    for index, code in enumerate(CLASS_ORDER):
        scored[f"prob_{code}"] = probs[:, index]
    scored["predicted_result"] = [CLASS_ORDER[int(np.argmax(row))] for row in probs]
    return scored
