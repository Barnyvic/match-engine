from app.pipeline.elo import EloConfig, EloTracker


def test_elo_home_win_increases_home_rating():
    tracker = EloTracker(EloConfig(base_rating=1500, k_factor=20, home_advantage=50))
    result = tracker.rate_match("Arsenal", "Chelsea", "H")
    assert result["post_home_elo"] > result["pre_home_elo"]
    assert result["post_away_elo"] < result["pre_away_elo"]


def test_elo_draw_preserves_total_rating_mass():
    tracker = EloTracker(EloConfig(base_rating=1500, k_factor=20, home_advantage=0))
    result = tracker.rate_match("Arsenal", "Chelsea", "D")
    total_before = result["pre_home_elo"] + result["pre_away_elo"]
    total_after = result["post_home_elo"] + result["post_away_elo"]
    assert round(total_before, 6) == round(total_after, 6)
