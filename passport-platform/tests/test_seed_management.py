from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from passport_platform.management.seed import _seed_user


def _write_case(root: Path, case_name: str) -> Path:
    case_dir = root / case_name
    case_dir.mkdir()
    (case_dir / "expected.json").write_text(
        json.dumps({"PassportNumber": "A1234567", "_meta": {"is_passport": True}}),
        encoding="utf-8",
    )
    (case_dir / "input.jpeg").write_bytes(b"jpeg-bytes")
    return case_dir


def test_seed_user_restores_archived_benchmark_uploads(tmp_path: Path) -> None:
    _write_case(tmp_path, "case_001")
    archive_calls: list[dict[str, object]] = []
    runtime = SimpleNamespace(
        records=SimpleNamespace(
            list_user_records=lambda _user_id, limit=1000: [
                SimpleNamespace(
                    upload_id=77,
                    source_ref="benchmark://case_001",
                    archived_at=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
                ),
            ],
            set_archive_state=lambda **kwargs: archive_calls.append(kwargs),
        ),
        uploads=SimpleNamespace(
            register_upload=lambda command: SimpleNamespace(id=command.user_id),
            record_processing_result=lambda _user_id, _command: None,
        ),
        artifacts=SimpleNamespace(save=lambda *_args, **_kwargs: "/tmp/seeded.jpeg"),
    )
    user = SimpleNamespace(id=42)

    created, skipped, restored = _seed_user(runtime, user, tmp_path)

    assert (created, skipped, restored) == (0, 0, 1)
    assert archive_calls == [{
        "upload_id": 77,
        "user_id": 42,
        "archived": False,
    }]


def test_seed_user_skips_active_benchmark_uploads(tmp_path: Path) -> None:
    _write_case(tmp_path, "case_001")
    archive_calls: list[dict[str, object]] = []
    runtime = SimpleNamespace(
        records=SimpleNamespace(
            list_user_records=lambda _user_id, limit=1000: [
                SimpleNamespace(
                    upload_id=77,
                    source_ref="benchmark://case_001",
                    archived_at=None,
                ),
            ],
            set_archive_state=lambda **kwargs: archive_calls.append(kwargs),
        ),
        uploads=SimpleNamespace(
            register_upload=lambda command: SimpleNamespace(id=command.user_id),
            record_processing_result=lambda _user_id, _command: None,
        ),
        artifacts=SimpleNamespace(save=lambda *_args, **_kwargs: "/tmp/seeded.jpeg"),
    )
    user = SimpleNamespace(id=42)

    created, skipped, restored = _seed_user(runtime, user, tmp_path)

    assert (created, skipped, restored) == (0, 1, 0)
    assert archive_calls == []
