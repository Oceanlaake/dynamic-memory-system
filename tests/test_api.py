"""HTTP 接口测试：验证对外契约，而不是内部实现。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app

QUESTION = "How long did it take for Jon to open his studio?"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_samples(client):
    assert client.get("/api/samples").json() == [{"sample_id": "conv-30", "memory_count": 5}]


def test_list_memories(client):
    response = client.get("/api/samples/conv-30/memories")
    assert response.status_code == 200
    assert len(response.json()) == 5


def test_unknown_sample_returns_structured_error(client):
    response = client.get("/api/samples/conv-99/memories")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SAMPLE_NOT_FOUND"


def test_retrieve_returns_candidates(client):
    response = client.post(
        "/api/retrieve",
        json={"sample_id": "conv-30", "question": QUESTION, "top_k": 4},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["strategy"] == "bm25"
    assert body["degraded"] is False
    assert len(body["candidates"]) == 4
    assert {c["memory"]["memory_id"] for c in body["candidates"][:2]} == {
        "mem-conv30-002",
        "mem-conv30-004",
    }


def test_retrieve_defaults_top_k_to_five(client):
    response = client.post("/api/retrieve", json={"sample_id": "conv-30", "question": QUESTION})
    assert response.json()["top_k"] == 5


def test_empty_question_is_rejected(client):
    response = client.post("/api/retrieve", json={"sample_id": "conv-30", "question": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_unknown_field_is_rejected(client):
    response = client.post(
        "/api/retrieve",
        json={"sample_id": "conv-30", "question": QUESTION, "as_of": "2023-06-20"},
    )
    assert response.status_code == 422


def test_query_endpoint_reports_unimplemented_dynamic_state(client):
    response = client.post("/api/query", json={"sample_id": "conv-30", "question": QUESTION})
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "DYNAMIC_STATE_NOT_IMPLEMENTED"


def test_openapi_document_is_served(client):
    schema = client.get("/openapi.json").json()
    assert "/api/retrieve" in schema["paths"]
