from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import cv2
import httpx
import numpy as np
from numpy.typing import NDArray

ImageArray = NDArray[np.uint8]


@dataclass(slots=True)
class LoadedImage:
    source: str
    data: bytes
    mime_type: str
    filename: str
    bgr: ImageArray


def decode_image(data: bytes) -> ImageArray:
    raw = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image bytes.")
    return cast(ImageArray, image)


def encode_jpeg(image: ImageArray, quality: int = 95) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise ValueError("Could not encode image to JPEG.")
    return encoded.tobytes()


def load_image_bytes(
    data: bytes,
    *,
    filename: str = "upload.jpg",
    mime_type: str = "image/jpeg",
    source: str | None = None,
) -> LoadedImage:
    return LoadedImage(
        source=source or filename,
        data=data,
        mime_type=mime_type,
        filename=filename,
        bgr=decode_image(data),
    )


def _preferred_extension(content_type: str) -> str:
    explicit = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/tiff": ".tiff",
    }
    return explicit.get(content_type, mimetypes.guess_extension(content_type) or ".bin")


def _is_disallowed_host(hostname: str | None) -> bool:
    if not hostname:
        return True
    blocked = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
    return hostname in blocked


class ImageLoader:
    def __init__(
        self,
        timeout_seconds: float,
        max_download_bytes: int,
        http_client: Any | None = None,
    ) -> None:
        self._max_download_bytes = max_download_bytes
        self._client = http_client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "passport-core/0.1"},
        )
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def load(self, source: str | Path) -> LoadedImage:
        source_str = str(source)
        parsed = urlparse(source_str)

        if parsed.scheme in {"http", "https"}:
            return self._load_url(source_str)

        return self._load_file(Path(source_str))

    def _load_url(self, url: str) -> LoadedImage:
        parsed = urlparse(url)
        if _is_disallowed_host(parsed.hostname):
            raise ValueError("URL host is not allowed.")

        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            mime_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > self._max_download_bytes:
                    raise ValueError(f"Image at {url} exceeds max allowed size.")
                chunks.append(chunk)

        data = b"".join(chunks)
        filename = Path(urlparse(url).path).name or f"downloaded{_preferred_extension(mime_type)}"

        return LoadedImage(
            source=url,
            data=data,
            mime_type=mime_type,
            filename=filename,
            bgr=decode_image(data),
        )

    def _load_file(self, path: Path) -> LoadedImage:
        if not path.exists():
            raise FileNotFoundError(f"Image path does not exist: {path}")

        data = path.read_bytes()
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"

        return LoadedImage(
            source=str(path),
            data=data,
            mime_type=mime_type,
            filename=path.name,
            bgr=decode_image(data),
        )
