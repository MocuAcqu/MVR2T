"""Phase 03: one-time session token + CORS for the Electron window."""
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import token_matches
from app.main import create_app

TOKEN = "test-token-0123456789abcdef"


def make_client(**overrides) -> TestClient:
    cfg = Settings(auth_token=TOKEN, allowed_origins=["null"], **overrides)
    return TestClient(create_app(cfg))


def auth(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_token_matches():
    assert token_matches(f"Bearer {TOKEN}", TOKEN)
    assert token_matches(f"bearer {TOKEN}", TOKEN)
    assert not token_matches(None, TOKEN)
    assert not token_matches("", TOKEN)
    assert not token_matches(TOKEN, TOKEN)  # missing scheme
    assert not token_matches(f"Basic {TOKEN}", TOKEN)
    assert not token_matches("Bearer wrong", TOKEN)
    assert not token_matches("Bearer ", "")  # empty expected token never matches


def test_request_without_token_is_rejected():
    res = make_client().get("/api/health")
    assert res.status_code == 401


def test_request_with_wrong_token_is_rejected():
    res = make_client().get("/api/health", headers=auth("nope"))
    assert res.status_code == 401


def test_request_with_token_is_accepted():
    res = make_client().get("/api/health", headers=auth())
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_docs_disabled_when_token_required():
    client = make_client()
    assert client.get("/api/docs", headers=auth()).status_code == 404
    assert client.get("/api/openapi.json", headers=auth()).status_code == 404


def test_preflight_from_electron_file_origin():
    # Packaged Electron loads file:// pages, whose Origin header is "null".
    res = make_client().options(
        "/api/health",
        headers={
            "Origin": "null",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "null"
    assert "authorization" in res.headers.get("access-control-allow-headers", "").lower()


def test_unauthorized_response_still_has_cors_headers():
    # Lets the renderer read the 401 instead of seeing an opaque network error.
    res = make_client().get("/api/health", headers={"Origin": "null"})
    assert res.status_code == 401
    assert res.headers.get("access-control-allow-origin") == "null"


def test_unknown_origin_gets_no_cors_even_with_token():
    res = make_client().get("/api/health", headers={**auth(), "Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in res.headers


def test_dev_mode_without_token_keeps_docs():
    client = TestClient(create_app(Settings(auth_token="")))
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/docs").status_code == 200
