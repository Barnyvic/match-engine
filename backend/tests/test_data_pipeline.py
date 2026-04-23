import pytest

from app.pipeline.data_pipeline import fetch_csv


class DummyResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


def test_fetch_csv_rejects_html(monkeypatch):
    monkeypatch.setattr(
        "app.pipeline.data_pipeline.requests.get",
        lambda *args, **kwargs: DummyResponse("<html><body>not csv</body></html>"),
    )

    with pytest.raises(ValueError, match="received HTML"):
        fetch_csv("https://example.com/fake.csv")
