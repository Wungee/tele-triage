"""API tests. Need a trained model in artifacts/ (synthetic is fine):
    python scripts/make_synthetic.py --out ../data/synthetic && python scripts/train.py --data ../data/synthetic
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

FIX = Path(__file__).parent / "fixtures"
pytestmark = pytest.mark.skipif(not (config.ARTIFACT_DIR / "model.joblib").exists(), reason="no trained model")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    h = client.get("/api/health").json()
    assert h["model_loaded"] and h["demo_alarms"] > 0


def test_alarm_detail_hides_answer(client):
    first = client.get("/api/alarms").json()["alarms"][0]["id"]
    r = client.get(f"/api/alarms/{first}").json()
    assert r["verdict"] in {"likely_artifact", "needs_review", "likely_real"}
    assert "expert_label" not in r and "is_true_alarm" not in str(r)
    assert r["waveform"]["channels"]


def test_review_reveals_expert_label(client):
    first = client.get("/api/alarms").json()["alarms"][0]["id"]
    r = client.post(f"/api/alarms/{first}/review", json={"decision": "real"}).json()
    assert r["expert_label"] in {"real", "artifact"}
    assert client.get("/api/stats").json()["reviews"] >= 1


def test_rejects_bad_ids_and_input(client):
    assert client.get("/api/alarms/..%2F..%2Fetc").status_code == 404
    first = client.get("/api/alarms").json()["alarms"][0]["id"]
    assert client.post(f"/api/alarms/{first}/review", json={"decision": "ignore"}).status_code == 422


def test_score_upload_real_record(client):
    files = {"header": ("a103l.hea", (FIX / "a103l.hea").read_bytes()),
             "signal": ("a103l.mat", (FIX / "a103l.mat").read_bytes())}
    r = client.post("/api/score", files=files)
    assert r.status_code == 200
    assert r.json()["expert_label"] == "artifact"
