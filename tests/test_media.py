"""Security coverage tests for media.py — MIME validation + file handling."""
from __future__ import annotations

import pytest
from src.media import (is_allowed_image, is_allowed_document,
                        ALLOWED_IMAGE_MIMES, ALLOWED_DOC_MIMES,
                        MAX_PHOTO_SIZE, MAX_FILE_SIZE)


def test_allowed_image_types() -> None:
    for mime in ALLOWED_IMAGE_MIMES:
        assert is_allowed_image(mime) is True


def test_blocked_image_types() -> None:
    assert is_allowed_image("image/bmp") is False
    assert is_allowed_image("image/svg+xml") is False
    assert is_allowed_image("") is False
    assert is_allowed_image("text/html") is False


def test_allowed_document_types() -> None:
    assert is_allowed_document("text/plain", "readme.txt") is True
    assert is_allowed_document("application/pdf", "doc.pdf") is True
    assert is_allowed_document("application/json", "data.json") is True
    assert is_allowed_document("text/x-python", "script.py") is True


def test_blocked_document_types() -> None:
    assert is_allowed_document("application/x-executable", "malware.exe") is False
    assert is_allowed_document("application/octet-stream", "virus.bin") is False
    assert is_allowed_document("application/zip", "archive.zip") is False
    assert is_allowed_document("application/octet-stream", "bad.com") is False


def test_document_allowed_by_extension_fallback() -> None:
    # MIME not in allowlist but extension is
    assert is_allowed_document("application/octet-stream", "config.yaml") is True


def test_document_blocked_com_extension_no_mime() -> None:
    # .com blocked only when MIME not trusted
    assert is_allowed_document("application/octet-stream", "config.com") is False


def test_size_limits_defined() -> None:
    assert MAX_PHOTO_SIZE == 10 * 1024 * 1024
    assert MAX_FILE_SIZE == 20 * 1024 * 1024
