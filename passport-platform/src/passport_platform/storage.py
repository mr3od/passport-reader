from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Protocol
from uuid import uuid4


class ArtifactStore(Protocol):
    def save(self, data: bytes, *, folder: str, filename: str, content_type: str) -> str: ...


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, *, folder: str, filename: str, content_type: str) -> str:
        target_dir = self.root / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix or _preferred_extension(content_type)
        target = target_dir / f"{uuid4().hex}{suffix}"
        target.write_bytes(data)
        return str(target.resolve())


def _preferred_extension(content_type: str) -> str:
    explicit = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/tiff": ".tiff",
    }
    return explicit.get(content_type, mimetypes.guess_extension(content_type) or ".bin")
