"""End-to-end tests for the /predict API.

Field lookups go through `resolve_field` so the suite survives a small
API rename like `priority` -> `level` without code changes — it just
logs a warning and keeps running.
"""
from __future__ import annotations

import logging

import pytest
import requests

from tests.self_healing import FieldNotFound, resolve_field

VALID_PRIORITIES = {"High", "Medium", "Low"}


@pytest.fixture(scope="session")
def health(base_url):
    r = requests.get(f"{base_url}/health", timeout=5)
    r.raise_for_status()
    return r.json()


def test_health_ok(health):
    assert health.get("status") == "ok"


@pytest.mark.parametrize(
    "task, expected",
    [
        ("Fix production bug in payments service", "High"),
        ("Prepare quarterly business review deck",   "Medium"),
        ("Read newsletter from cloud provider",      "Low"),
    ],
)
def test_predict_returns_priority(base_url, task, expected, caplog):
    caplog.set_level(logging.WARNING, logger="self_healing")

    r = requests.post(
        f"{base_url}/predict",
        json={"task": task},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Field name might be `priority` today, `level`/`urgency`/... tomorrow.
    key, priority = resolve_field(body, "priority")
    assert priority in VALID_PRIORITIES, f"unexpected value for {key!r}: {priority!r}"
    assert priority == expected, (
        f"task {task!r} classified as {priority!r}, expected {expected!r}"
    )


def test_predict_returns_confidence(base_url, caplog):
    caplog.set_level(logging.WARNING, logger="self_healing")

    r = requests.post(
        f"{base_url}/predict",
        json={"task": "Patch critical security vulnerability"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    key, conf = resolve_field(body, "confidence")
    assert isinstance(conf, (int, float)), f"{key!r} should be numeric, got {type(conf).__name__}"
    assert 0.0 <= float(conf) <= 1.0, f"{key!r} out of range: {conf}"


def test_predict_rejects_empty_body(base_url):
    r = requests.post(f"{base_url}/predict", json={}, timeout=5)
    assert r.status_code == 400


def test_resolver_raises_when_nothing_matches():
    """Sanity check on the resolver itself — when an API breaks beyond
    the known aliases, the test should fail with a clear message,
    not silently miss the regression."""
    with pytest.raises(FieldNotFound) as exc:
        resolve_field({"completely_different": "x"}, "priority")
    msg = str(exc.value)
    assert "priority" in msg
    assert "completely_different" in msg
