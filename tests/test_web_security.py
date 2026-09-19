from fastapi import FastAPI
from fastapi.testclient import TestClient

from jobpilot.web.app import reject_cross_origin_writes


def _client() -> TestClient:
    # An isolated app with just the middleware under test, not the real
    # dashboard - a POST to the real app's routes would actually launch a
    # browser-based Bayt search or send email via a background task.
    app = FastAPI()
    app.middleware("http")(reject_cross_origin_writes)

    @app.post("/echo")
    def echo_post():
        return {"ok": True}

    @app.get("/echo")
    def echo_get():
        return {"ok": True}

    return TestClient(app)


def test_same_origin_post_is_allowed():
    client = _client()
    response = client.post("/echo", headers={"origin": str(client.base_url).rstrip("/")})
    assert response.status_code == 200


def test_post_with_no_origin_header_is_allowed():
    # A plain <form method="post"> submission from the dashboard's own
    # pages doesn't always carry an Origin header - only reject when we
    # can positively identify a different origin.
    client = _client()
    response = client.post("/echo")
    assert response.status_code == 200


def test_cross_origin_post_is_rejected():
    client = _client()
    response = client.post("/echo", headers={"origin": "https://evil.example.com"})
    assert response.status_code == 403


def test_get_requests_are_never_blocked():
    client = _client()
    response = client.get("/echo", headers={"origin": "https://evil.example.com"})
    assert response.status_code == 200
