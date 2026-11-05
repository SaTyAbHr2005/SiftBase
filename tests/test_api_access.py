"""API key and per-client rate limits in front of /index and /query."""
import pytest
from fastapi.testclient import TestClient

import kb.access as access
from kb.api import app

# An invalid collection name stops inside the route with 422, so reaching it costs no model call.
BODY = {"collection_name": "bad name", "query": "q"}


@pytest.fixture
def client(monkeypatch):
    for var in ("KB_API_KEYS", "KB_QUERY_PER_HOUR", "KB_INDEX_PER_DAY", "KB_QUERIES_PER_DAY", "RENDER", "KB_AUTH"):
        monkeypatch.delenv(var, raising=False)
    access._hits.clear()
    return TestClient(app)


def test_without_configured_keys_requests_go_through(client):
    assert client.post("/query", json=BODY).status_code == 422


def test_configured_keys_are_required_in_either_header(client, monkeypatch):
    monkeypatch.setenv("KB_API_KEYS", "k-one, k-two")
    for headers in ({}, {"X-API-Key": "wrong"}, {"Authorization": "Bearer wrong"}):
        r = client.post("/query", json=BODY, headers=headers)
        assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
    assert client.post("/query", json=BODY, headers={"X-API-Key": "k-two"}).status_code == 422
    assert client.post("/query", json=BODY, headers={"Authorization": "Bearer k-one"}).status_code == 422
    assert client.post("/index", data={"collection_name": "c1"}).status_code == 401


def test_each_key_has_its_own_hourly_query_limit(client, monkeypatch):
    monkeypatch.setenv("KB_API_KEYS", "a,b")
    monkeypatch.setenv("KB_QUERY_PER_HOUR", "2")
    for _ in range(2):
        assert client.post("/query", json=BODY, headers={"X-API-Key": "a"}).status_code == 422
    r = client.post("/query", json=BODY, headers={"X-API-Key": "a"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
    assert 0 < int(r.headers["Retry-After"]) <= 3600
    assert client.post("/query", json=BODY, headers={"X-API-Key": "b"}).status_code == 422
    assert client.post("/query", json=BODY, headers={"X-API-Key": "wrong"}).status_code == 401  # auth comes first


def test_all_keys_together_share_a_daily_query_cap(client, monkeypatch):
    monkeypatch.setenv("KB_API_KEYS", "a,b")
    monkeypatch.setenv("KB_QUERIES_PER_DAY", "3")
    for key in ("a", "b", "a"):
        assert client.post("/query", json=BODY, headers={"X-API-Key": key}).status_code == 422
    r = client.post("/query", json=BODY, headers={"X-API-Key": "b"})
    assert r.status_code == 429 and r.json()["error"]["details"]["window_s"] == 86400


def test_callers_turned_away_by_the_shared_cap_leave_nothing_in_memory(client, monkeypatch):
    monkeypatch.setenv("KB_QUERIES_PER_DAY", "1")
    assert access.check("POST", "/query", {}, "1.1.1.1") is None
    size = len(access._hits)
    for i in range(5):
        assert access.check("POST", "/query", {}, f"2.2.2.{i}")[0].code == "RATE_LIMITED"
    assert len(access._hits) == size


def test_a_hosted_deploy_without_keys_refuses_instead_of_running_open(client, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    r = client.post("/query", json=BODY)
    assert r.status_code == 503 and r.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"
    monkeypatch.setenv("KB_AUTH", "off")  # open on purpose
    assert client.post("/query", json=BODY).status_code == 422


def test_a_path_prefix_a_trailing_slash_or_another_verb_cannot_get_around_the_key(monkeypatch, client):
    monkeypatch.setenv("KB_API_KEYS", "k")
    monkeypatch.setenv("KB_QUERY_PER_HOUR", "1")
    assert TestClient(app, root_path="/api").post("/api/query", json=BODY).status_code == 401
    assert client.post("/query/", json=BODY, headers={"X-API-Key": "k"}, follow_redirects=False).status_code == 404
    assert client.get("/query").status_code == 401
    assert client.get("/query", headers={"X-API-Key": "k"}).status_code == 405  # a wrong verb uses no slot
    assert client.post("/query", json=BODY, headers={"X-API-Key": "k"}).status_code == 422


def test_index_has_a_daily_limit_and_zero_turns_a_limit_off(client, monkeypatch):
    monkeypatch.setenv("KB_INDEX_PER_DAY", "1")
    monkeypatch.setenv("KB_QUERY_PER_HOUR", "0")
    monkeypatch.setenv("KB_QUERIES_PER_DAY", "0")
    assert client.post("/index", data={"collection_name": "c1"}).status_code == 422
    assert client.post("/index", data={"collection_name": "c1"}).status_code == 429
    assert all(client.post("/query", json=BODY).status_code == 422 for _ in range(30))
