"""Tests for the extension fetcher module."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from passport_telegram.extension import (
    ExtensionFetchError,
    _clear_cache,
    fetch_extension_zip,
)

FAKE_TOKEN = "ghp_testtoken"
FAKE_REPO = "owner/repo"
FAKE_ZIP = b"PK\x03\x04fake zip content"

_RELEASE_METADATA = {
    "assets": [
        {
            "name": "extension.zip",
            "url": "https://api.github.com/repos/owner/repo/releases/assets/12345",
        }
    ]
}


@pytest.fixture(autouse=True)
def clear_extension_cache():
    _clear_cache()
    yield
    _clear_cache()


def _make_mock_response(status_code: int, json_data=None, content: bytes = b"") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.content = content
    return resp


def _make_mock_client(side_effects: list) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=side_effects)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def test_fetch_returns_zip_bytes():
    release_resp = _make_mock_response(200, _RELEASE_METADATA)
    download_resp = _make_mock_response(200, content=FAKE_ZIP)
    mock_client = _make_mock_client([release_resp, download_resp])

    with patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client):
        result = asyncio.run(fetch_extension_zip(token=FAKE_TOKEN, repo=FAKE_REPO))

    assert result == FAKE_ZIP


def test_fetch_caches_result():
    release_resp = _make_mock_response(200, _RELEASE_METADATA)
    download_resp = _make_mock_response(200, content=FAKE_ZIP)
    mock_client = _make_mock_client([release_resp, download_resp])

    with patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client):
        first = asyncio.run(fetch_extension_zip(token=FAKE_TOKEN, repo=FAKE_REPO))
        second = asyncio.run(fetch_extension_zip(token=FAKE_TOKEN, repo=FAKE_REPO))

    assert first == second == FAKE_ZIP
    # Second call hits cache; httpx only called twice (both from the first fetch)
    assert mock_client.get.call_count == 2


def test_cache_expires_after_ttl(monkeypatch):
    call_count = 0
    time_values = [0.0, 0.0, 301.0, 301.0]

    def fake_monotonic():
        nonlocal call_count
        val = time_values[min(call_count, len(time_values) - 1)]
        call_count += 1
        return val

    monkeypatch.setattr("passport_telegram.extension.time.monotonic", fake_monotonic)

    release_resp1 = _make_mock_response(200, _RELEASE_METADATA)
    download_resp1 = _make_mock_response(200, content=FAKE_ZIP)
    release_resp2 = _make_mock_response(200, _RELEASE_METADATA)
    download_resp2 = _make_mock_response(200, content=FAKE_ZIP)
    mock_client = _make_mock_client([release_resp1, download_resp1, release_resp2, download_resp2])

    with patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client):
        asyncio.run(fetch_extension_zip(token=FAKE_TOKEN, repo=FAKE_REPO))
        asyncio.run(fetch_extension_zip(token=FAKE_TOKEN, repo=FAKE_REPO))

    # Both fetches should have hit the network (4 get calls total: 2 per fetch)
    assert mock_client.get.call_count == 4


def test_fetch_raises_on_release_not_found():
    not_found_resp = _make_mock_response(404)
    mock_client = _make_mock_client([not_found_resp])
    patcher = patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client)

    with patcher, pytest.raises(ExtensionFetchError, match="GitHub release lookup failed"):
        asyncio.run(fetch_extension_zip(token=FAKE_TOKEN, repo=FAKE_REPO))


def test_fetch_raises_on_missing_asset():
    release_resp = _make_mock_response(200, {"assets": []})
    mock_client = _make_mock_client([release_resp])
    patcher = patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client)

    with patcher, pytest.raises(ExtensionFetchError, match="extension.zip not found"):
        asyncio.run(fetch_extension_zip(token=FAKE_TOKEN, repo=FAKE_REPO))


def test_fetch_raises_on_zip_too_large():
    oversized_content = b"x" * 5_000_001
    release_resp = _make_mock_response(200, _RELEASE_METADATA)
    download_resp = _make_mock_response(200, content=oversized_content)
    mock_client = _make_mock_client([release_resp, download_resp])
    patcher = patch("passport_telegram.extension.httpx.AsyncClient", return_value=mock_client)

    with patcher, pytest.raises(ExtensionFetchError, match="Extension ZIP too large"):
        asyncio.run(fetch_extension_zip(token=FAKE_TOKEN, repo=FAKE_REPO))
