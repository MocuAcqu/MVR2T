"""Phase 01 驗收：後端 health check 可用，且回應結構正確。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["service"]


def test_cors_allows_vite_dev_origin():
    res = client.get("/api/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert res.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"


def test_cors_rejects_unknown_origin():
    res = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in res.headers
