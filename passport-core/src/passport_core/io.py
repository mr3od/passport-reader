from __future__ import annotations

import csv
import mimetypes
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlparse
from uuid import uuid4

import cv2
import httpx
import numpy as np
from numpy.typing import NDArray

from passport_core.config import Settings
from passport_core.models import PassportData, PassportProcessingResult

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


class BinaryStore(Protocol):
    def save(self, data: bytes, *, folder: str, filename: str, content_type: str) -> str: ...


class ResultStore(Protocol):
    def save(self, result: PassportProcessingResult) -> None: ...

    def fetch_all(self) -> list[PassportProcessingResult]: ...


class LocalFileStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, *, folder: str, filename: str, content_type: str) -> str:
        suffix = Path(filename).suffix or _preferred_extension(content_type)
        dated_folder = self.root / folder / datetime.now(UTC).strftime("%Y%m%d")
        dated_folder.mkdir(parents=True, exist_ok=True)

        target = dated_folder / f"{uuid4().hex}{suffix}"
        target.write_bytes(data)
        return str(target.resolve())


class S3FileStore:
    def __init__(self, bucket: str, prefix: str = "passport-core") -> None:
        import boto3

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client("s3")

    def save(self, data: bytes, *, folder: str, filename: str, content_type: str) -> str:
        suffix = Path(filename).suffix or _preferred_extension(content_type)
        date_part = datetime.now(UTC).strftime("%Y%m%d")
        key = f"{self.prefix}/{folder}/{date_part}/{uuid4().hex}{suffix}"

        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return f"s3://{self.bucket}/{key}"


class JsonResultStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, result: PassportProcessingResult) -> None:
        path = self.directory / f"{uuid4().hex}.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    def fetch_all(self) -> list[PassportProcessingResult]:
        out: list[PassportProcessingResult] = []
        for path in sorted(self.directory.glob("*.json")):
            payload = path.read_text(encoding="utf-8")
            out.append(PassportProcessingResult.model_validate_json(payload))
        return out


class CsvResultStore:
    FIELDNAMES = ["created_at", "is_passport", "payload_json"]

    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, result: PassportProcessingResult) -> None:
        exists = self.csv_path.exists()
        with self.csv_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.FIELDNAMES)
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "created_at": result.created_at.isoformat(),
                    "is_passport": str(result.validation.is_passport),
                    "payload_json": result.model_dump_json(),
                }
            )

    def fetch_all(self) -> list[PassportProcessingResult]:
        if not self.csv_path.exists():
            return []

        out: list[PassportProcessingResult] = []
        with self.csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                payload = row.get("payload_json", "")
                if payload:
                    out.append(PassportProcessingResult.model_validate_json(payload))
        return out


class SqliteResultStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS passport_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_passport INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save(self, result: PassportProcessingResult) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO passport_results (source, created_at, is_passport, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    result.source,
                    result.created_at.isoformat(),
                    int(result.validation.is_passport),
                    result.model_dump_json(),
                ),
            )

    def fetch_all(self) -> list[PassportProcessingResult]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM passport_results ORDER BY id ASC"
            ).fetchall()
        return [PassportProcessingResult.model_validate_json(row["payload_json"]) for row in rows]


def build_binary_store(settings: Settings) -> BinaryStore:
    if settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise ValueError("PASSPORT_S3_BUCKET is required when storage_backend=s3.")
        return S3FileStore(bucket=settings.s3_bucket, prefix=settings.s3_prefix)

    return LocalFileStore(settings.local_storage_dir)


def build_result_store(settings: Settings) -> ResultStore:
    if settings.data_store_backend == "json":
        return JsonResultStore(settings.data_store_path / "results")
    if settings.data_store_backend == "csv":
        return CsvResultStore(settings.data_store_path / "results.csv")
    return SqliteResultStore(settings.data_store_path / "results.sqlite3")


class EnjazCsvExporter:
    def export(self, records: Sequence[PassportProcessingResult], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(PassportData.model_fields.keys())

        with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                if record.data is None:
                    continue
                writer.writerow({name: getattr(record.data, name) or "" for name in fieldnames})
