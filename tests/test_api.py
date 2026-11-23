import pytest
from fastapi.testclient import TestClient

from api.main import FEATURES, app


def _row() -> dict:
    row = {f: 0.0 for f in FEATURES}
    row.update({"amount": 1000.0, "type_TRANSFER": 1.0, "orig_drain_ratio": 0.5})
    return row


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_ready_503_before_load():
    assert TestClient(app).get("/ready").status_code == 503


def test_valid_row(client):
    r = client.post("/predict", json=_row())
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["score"] <= 1.0
    assert len(body["model_version"]) == 8


def test_null_drain_ratio(client):
    row = _row()
    row["orig_drain_ratio"] = None
    assert client.post("/predict", json=row).status_code == 200


def test_missing_field(client):
    row = _row()
    del row["amount"]
    assert client.post("/predict", json=row).status_code == 422


def test_extra_field(client):
    row = _row()
    row["extra"] = 1.0
    assert client.post("/predict", json=row).status_code == 422


def test_non_numeric_field(client):
    row = _row()
    row["amount"] = "abc"
    assert client.post("/predict", json=row).status_code == 422


def test_null_on_required_field(client):
    row = _row()
    row["amount"] = None
    assert client.post("/predict", json=row).status_code == 422


def test_ready_and_health(client):
    assert client.get("/ready").status_code == 200
    assert client.get("/health").status_code == 200


def test_metrics_histogram(client):
    client.post("/predict", json=_row())
    text = client.get("/metrics").text
    assert "api_request_latency_seconds_bucket" in text
    assert "api_requests_total" in text
    assert "api_in_flight_requests" in text
    assert "api_errors_total" in text
