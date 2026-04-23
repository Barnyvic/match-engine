from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EloConfig:
    base_rating: float = 1500.0
    k_factor: float = 24.0
    home_advantage: float = 60.0


class EloTracker:
    def __init__(self, config: EloConfig | None = None) -> None:
        self.config = config or EloConfig()
        self.ratings: dict[str, float] = {}

    def get_rating(self, team: str) -> float:
        return self.ratings.get(team, self.config.base_rating)

    def expected_home_score(self, home_team: str, away_team: str) -> float:
        home_rating = self.get_rating(home_team) + self.config.home_advantage
        away_rating = self.get_rating(away_team)
        return 1.0 / (1.0 + 10 ** ((away_rating - home_rating) / 400))

    def rate_match(self, home_team: str, away_team: str, result_code: str) -> dict[str, float]:
        expected_home = self.expected_home_score(home_team, away_team)
        expected_away = 1.0 - expected_home

        actual_home = {"H": 1.0, "D": 0.5, "A": 0.0}[result_code]
        actual_away = 1.0 - actual_home

        old_home = self.get_rating(home_team)
        old_away = self.get_rating(away_team)

        new_home = old_home + self.config.k_factor * (actual_home - expected_home)
        new_away = old_away + self.config.k_factor * (actual_away - expected_away)

        self.ratings[home_team] = new_home
        self.ratings[away_team] = new_away

        return {
            "pre_home_elo": old_home,
            "pre_away_elo": old_away,
            "expected_home_score": expected_home,
            "post_home_elo": new_home,
            "post_away_elo": new_away,
        }
