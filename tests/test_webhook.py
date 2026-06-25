"""Security coverage tests for webhook.py — HMAC validation + handler."""
from __future__ import annotations

import hashlib
import hmac
import json

from src.webhook import _verify_secret, WEBHOOK_PATH


def test_webhook_path_constant() -> None:
    assert WEBHOOK_PATH == "/webhook"


def test_verify_secret_valid() -> None:
    token = "my-secret-token-123"
    body = json.dumps({"update_id": 1}).encode()
    expected = hmac.new(
        hashlib.sha256(token.encode()).digest(),
        body, hashlib.sha256).hexdigest()
    assert _verify_secret(body, expected, token) is True


def test_verify_secret_wrong() -> None:
    token = "my-secret-token-123"
    body = json.dumps({"update_id": 1}).encode()
    assert _verify_secret(body, "wrong-hash", token) is False


def test_verify_secret_empty_header() -> None:
    assert _verify_secret(b"{}", "", "token") is False


def test_verify_secret_empty_token() -> None:
    assert _verify_secret(b"{}", "x", "") is False


def test_verify_secret_different_body() -> None:
    token = "my-secret-token-123"
    body1 = json.dumps({"update_id": 1}).encode()
    body2 = json.dumps({"update_id": 2}).encode()
    expected = hmac.new(
        hashlib.sha256(token.encode()).digest(),
        body1, hashlib.sha256).hexdigest()
    assert _verify_secret(body2, expected, token) is False
