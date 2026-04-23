from fastapi.testclient import TestClient

from app.main import app


def test_predictions_endpoint_returns_snapshot(monkeypatch):
    def fake_snapshot(competition: str = "EPL", force_refresh: bool = False):
        return {
            "competition": competition,
            "league": "English Premier League",
            "generated_at": "2026-04-23T00:00:00Z",
            "metrics": {"accuracy": 0.55},
            "upcoming_predictions": [],
            "upcoming_fixtures_count": 0,
            "training_rows": 100,
            "ingestion": {"season_results": []},
            "backtest": {"summary": {"roi": 0.02}},
            "teams": ["Arsenal", "Man City"],
            "timings": {"training_seconds": 1.2},
        }

    monkeypatch.setattr("app.main.build_pipeline_snapshot", fake_snapshot)
    client = TestClient(app)

    response = client.get("/api/predictions")

    assert response.status_code == 200
    body = response.json()
    assert body["league"] == "English Premier League"
    assert body["training_rows"] == 100
    assert "timings" in body


def test_backtest_endpoint_propagates_snapshot(monkeypatch):
    def fake_snapshot(competition: str = "EPL", force_refresh: bool = False):
        return {
            "competition": competition,
            "league": "English Premier League",
            "generated_at": "2026-04-23T00:00:00Z",
            "metrics": {"accuracy": 0.55},
            "upcoming_predictions": [],
            "upcoming_fixtures_count": 0,
            "training_rows": 100,
            "ingestion": {"season_results": []},
            "backtest": {"summary": {"roi": 0.02, "bets_placed": 10}},
            "teams": ["Arsenal", "Man City"],
            "timings": {"training_seconds": 1.2},
        }

    monkeypatch.setattr("app.main.build_pipeline_snapshot", fake_snapshot)
    client = TestClient(app)

    response = client.get("/api/backtest")

    assert response.status_code == 200
    body = response.json()
    assert body["backtest"]["summary"]["bets_placed"] == 10


def test_refresh_endpoint_forces_rebuild(monkeypatch):
    calls = []

    def fake_clear(competition=None):
        calls.append(("clear", competition))

    def fake_snapshot(competition: str = "EPL", force_refresh: bool = False):
        calls.append((competition, force_refresh))
        return {
            "competition": competition,
            "league": "English Premier League",
            "generated_at": "2026-04-23T00:00:00Z",
            "metrics": {"accuracy": 0.55},
            "upcoming_predictions": [],
            "upcoming_fixtures_count": 1,
            "training_rows": 100,
            "ingestion": {"season_results": []},
            "backtest": {"summary": {"roi": 0.02}},
            "teams": ["Arsenal", "Man City"],
            "timings": {"training_seconds": 1.2},
        }

    monkeypatch.setattr("app.main.clear_pipeline_snapshot_cache", fake_clear)
    monkeypatch.setattr("app.main.build_pipeline_snapshot", fake_snapshot)
    client = TestClient(app)

    response = client.post("/api/refresh")

    assert response.status_code == 200
    assert calls == [("clear", "EPL"), ("EPL", True)]


def test_competitions_endpoint(monkeypatch):
    monkeypatch.setattr(
        "app.main.list_competitions",
        lambda: [{"key": "EPL", "name": "English Premier League", "supported": True}],
    )
    client = TestClient(app)

    response = client.get("/api/competitions")

    assert response.status_code == 200
    assert response.json()["competitions"][0]["key"] == "EPL"


def test_matchup_endpoint(monkeypatch):
    monkeypatch.setattr(
        "app.main.predict_matchup",
        lambda competition, home_team, away_team: {
            "competition": competition,
            "summary": {"headline": f"{home_team} vs {away_team}"},
            "prediction": {"predicted_result": "H"},
        },
    )
    client = TestClient(app)

    response = client.get("/api/matchup?competition=EPL&home_team=Arsenal&away_team=Man%20City")

    assert response.status_code == 200
    assert response.json()["summary"]["headline"] == "Arsenal vs Man City"
