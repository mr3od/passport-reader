from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from passport_core.io import ImageLoader, decode_image, encode_jpeg


class _MockResponse:
    def __init__(self, chunks: list[bytes], content_type: str = "image/jpeg") -> None:
        self._chunks = chunks
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        return

    def iter_bytes(self):
        yield from self._chunks


class _MockStream:
    def __init__(self, response: _MockResponse) -> None:
        self._response = response

    def __enter__(self) -> _MockResponse:
        return self._response

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


class _MockHttpClient:
    def __init__(self, response: _MockResponse) -> None:
        self._response = response

    def stream(self, method: str, url: str):
        return _MockStream(self._response)


def test_encode_decode_roundtrip(sample_bgr_image: np.ndarray):
    encoded = encode_jpeg(sample_bgr_image)
    decoded = decode_image(encoded)
    assert decoded.shape == sample_bgr_image.shape


def test_load_file_success(tmp_path: Path, sample_bgr_image: np.ndarray):
    p = tmp_path / "passport.jpg"
    cv2.imwrite(str(p), sample_bgr_image)

    loader = ImageLoader(timeout_seconds=5, max_download_bytes=1024)
    loaded = loader.load(p)

    assert loaded.filename == "passport.jpg"
    assert loaded.bgr.shape == sample_bgr_image.shape


def test_load_file_not_found():
    loader = ImageLoader(timeout_seconds=5, max_download_bytes=1024)
    with pytest.raises(FileNotFoundError):
        loader.load("/missing/file.jpg")


def test_load_url_blocked_localhost(sample_jpeg_bytes: bytes):
    client = _MockHttpClient(_MockResponse([sample_jpeg_bytes]))
    loader = ImageLoader(timeout_seconds=5, max_download_bytes=1024 * 1024, http_client=client)

    with pytest.raises(ValueError, match="not allowed"):
        loader.load("http://localhost/image.jpg")


def test_load_url_enforces_max_bytes(sample_jpeg_bytes: bytes):
    client = _MockHttpClient(_MockResponse([sample_jpeg_bytes]))
    loader = ImageLoader(timeout_seconds=5, max_download_bytes=100, http_client=client)

    with pytest.raises(ValueError, match="exceeds"):
        loader.load("https://example.com/image.jpg")
