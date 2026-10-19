#!/usr/bin/env python3
"""Run deterministic integration checks for the presentation Demo."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))
os.environ["DMS_MEMORY_DIR"] = str(REPO_ROOT / "data" / "memories")
os.environ["DMS_RETRIEVER"] = "bm25"
os.environ["DMS_STATE_RESOLVER"] = "rules"

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


Check = Callable[[int, Any], None]


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_duration(status: int, body: Any) -> None:
    expect(status == 200, f"expected HTTP 200, got {status}")
    expect(body["answer"] == "It took Jon six months to open his studio.", "wrong answer")
    expect(
        {item["relation"] for item in body["relations"]} >= {"SUPERSEDE", "UPDATE"},
        "dynamic relations are incomplete",
    )
    expect(len(body["effective_memories"]) == 2, "duration needs two time anchors")
    expect(len(body["evidence"]) == 2, "duration answer needs two evidence turns")
    expect(body["degraded"] is False, "happy path must not be degraded")


def check_preference(status: int, body: Any) -> None:
    expect(status == 200, f"expected HTTP 200, got {status}")
    expect(body["answer"] == "Jon's favorite dance style is contemporary dance.", "wrong answer")
    expect(body["evidence"] == [{"session_id": "session_1", "dia_id": "D1:8"}], "wrong evidence")


def check_lifecycle(status: int, body: Any) -> None:
    expect(status == 200, f"expected HTTP 200, got {status}")
    expect(
        body["answer"] == "Jon scheduled the official opening of his dance studio for 20 June 2023.",
        "wrong lifecycle answer",
    )
    expect(
        body["effective_memories"]
        == [{"memory_id": "mem-conv30-004", "role": "supporting_event"}],
        "wrong effective memory",
    )


def check_no_match(status: int, body: Any) -> None:
    expect(status == 200, f"expected HTTP 200, got {status}")
    expect(body["answer"] is None, "no-match scenario must not invent an answer")
    expect(body["candidate_memories"] == [], "no-match scenario should have no candidates")
    expect(body["degraded"] is True, "no-match scenario must be marked degraded")


def check_not_found(status: int, body: Any) -> None:
    expect(status == 404, f"expected HTTP 404, got {status}")
    expect(body["error"]["code"] == "SAMPLE_NOT_FOUND", "wrong error code")


def check_invalid(status: int, body: Any) -> None:
    expect(status == 422, f"expected HTTP 422, got {status}")
    expect(body["error"]["code"] == "INVALID_REQUEST", "wrong error code")


SCENARIOS: list[tuple[str, dict[str, Any], Check]] = [
    (
        "duration + dynamic state + evidence",
        {
            "sample_id": "conv-30",
            "question": "How long did it take for Jon to open his studio?",
            "top_k": 5,
        },
        check_duration,
    ),
    (
        "stable preference",
        {
            "sample_id": "conv-30",
            "question": "What is Jon's favorite style of dance?",
            "top_k": 5,
        },
        check_preference,
    ),
    (
        "studio lifecycle",
        {
            "sample_id": "conv-30",
            "question": "What is Jon working on opening?",
            "top_k": 5,
        },
        check_lifecycle,
    ),
    (
        "unrelated question does not hallucinate",
        {
            "sample_id": "conv-30",
            "question": "ZXQJ completely unrelated quantum submarine?",
            "top_k": 5,
        },
        check_no_match,
    ),
    (
        "unknown sample",
        {"sample_id": "conv-999", "question": "Anything?", "top_k": 5},
        check_not_found,
    ),
    (
        "invalid empty question",
        {"sample_id": "conv-30", "question": "", "top_k": 5},
        check_invalid,
    ),
]


def main() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        expect(health.status_code == 200 and health.json() == {"status": "ok"}, "health check failed")
        print("[PASS] health check")

        samples = client.get("/api/samples")
        expect(samples.status_code == 200, "sample list failed")
        expect(samples.json() == [{"sample_id": "conv-30", "memory_count": 5}], "wrong Demo data")
        print("[PASS] curated Demo data: conv-30 / 5 memories")

        for name, payload, check in SCENARIOS:
            response = client.post("/api/query", json=payload)
            body = response.json()
            check(response.status_code, body)
            print(f"[PASS] {name}")

    print(f"\nDemo verification passed: {len(SCENARIOS) + 2} checks")


if __name__ == "__main__":
    main()
