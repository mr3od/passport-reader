from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from passport_platform import ChannelName, ExternalProvider, build_platform_runtime
from passport_platform.schemas.commands import (
    RecordProcessingResultCommand,
    RegisterUploadCommand,
)

DEFAULT_CASES_DIR = Path("/app/benchmark-cases")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seed benchmark passport records for admin users defined in "
            "PASSPORT_ADMIN_BOT_ADMIN_USER_IDS. "
            "Does not create new users — only seeds existing Telegram users. "
            "Safe to run repeatedly; already-imported cases are skipped."
        ),
    )
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=DEFAULT_CASES_DIR,
        help="Path to the labeled benchmark cases directory (default: %(default)s).",
    )
    return parser.parse_args()


def _admin_user_ids() -> list[str]:
    raw = os.environ.get("PASSPORT_ADMIN_BOT_ADMIN_USER_IDS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _case_dirs(cases_dir: Path) -> list[Path]:
    return sorted(path for path in cases_dir.iterdir() if path.is_dir())


def _load_expected(case_dir: Path) -> dict[str, object]:
    return json.loads((case_dir / "expected.json").read_text())


def _source_ref(case_dir: Path) -> str:
    return f"benchmark://{case_dir.name}"


def _reset_masar_submissions(runtime, user) -> int:
    """Delete all masar submission rows for the user's benchmark uploads. Returns deleted count."""
    with runtime.db.transaction() as conn:
        result = conn.execute(
            """
            DELETE FROM masar_submissions
            WHERE upload_id IN (
                SELECT id FROM uploads
                WHERE user_id = ? AND source_ref LIKE 'benchmark://%'
            )
            """,
            (user.id,),
        )
        return result.rowcount


def _seed_user(runtime, user, cases_dir: Path) -> tuple[int, int]:
    """Import benchmark cases for a single user. Returns (created, skipped)."""
    existing = {
        record.source_ref
        for record in runtime.records.list_user_records(user.id, limit=1000)
    }

    created = 0
    skipped = 0
    for case_dir in _case_dirs(cases_dir):
        source_ref = _source_ref(case_dir)
        if source_ref in existing:
            skipped += 1
            continue

        image_path = case_dir / "input.jpeg"
        if not image_path.exists():
            skipped += 1
            continue

        expected = _load_expected(case_dir)
        image_bytes = image_path.read_bytes()
        passport_image_uri = runtime.artifacts.save(
            image_bytes,
            folder="uploads",
            filename=f"{case_dir.name}{image_path.suffix or '.jpg'}",
            content_type="image/jpeg",
        )

        upload = runtime.uploads.register_upload(
            RegisterUploadCommand(
                user_id=user.id,
                channel=ChannelName.API,
                filename=image_path.name,
                mime_type="image/jpeg",
                source_ref=source_ref,
            )
        )
        runtime.uploads.record_processing_result(
            user.id,
            RecordProcessingResultCommand(
                upload_id=upload.id,
                is_passport=bool(expected.get("_meta", {}).get("is_passport", True)),  # ty:ignore[unresolved-attribute]
                is_complete=bool(expected.get("PassportNumber")),
                review_status="auto",
                passport_number=expected.get("PassportNumber")
                if isinstance(expected.get("PassportNumber"), str)
                else None,  # ty:ignore[invalid-argument-type]
                passport_image_uri=passport_image_uri,
                confidence_overall=1.0,
                extraction_result_json=json.dumps(
                    {"data": expected, "warnings": []},
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
                error_code=None,
                completed_at=datetime.now(UTC),
            ),
        )
        created += 1

    return created, skipped


def main() -> int:
    args = _parse_args()

    admin_ids = _admin_user_ids()
    if not admin_ids:
        print(
            "[seed] PASSPORT_ADMIN_BOT_ADMIN_USER_IDS is not set or empty — nothing to seed",
            file=sys.stderr,
        )
        return 1

    if not args.cases_dir.exists():
        print(
            f"[seed] cases-dir {args.cases_dir} not found — nothing to seed",
            file=sys.stderr,
        )
        return 1

    runtime = build_platform_runtime()

    for telegram_user_id in admin_ids:
        user = runtime.users.get_by_external_identity(
            ExternalProvider.TELEGRAM,
            telegram_user_id,
        )
        if user is None:
            print(
                f"[seed] telegram_user_id={telegram_user_id} not found in DB — "
                "start the Telegram bot first",
                file=sys.stderr,
            )
            continue

        created, skipped = _seed_user(runtime, user, args.cases_dir)
        reset = _reset_masar_submissions(runtime, user)
        print(
            f"telegram_user_id={telegram_user_id} "
            f"user_id={user.id} "
            f"records_created={created} "
            f"records_skipped={skipped} "
            f"masar_submissions_reset={reset}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
