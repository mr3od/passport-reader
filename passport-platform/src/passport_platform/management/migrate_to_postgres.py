"""Migrate data from SQLite to PostgreSQL.

Usage:
    uv run migrate-to-postgres [--dry-run] [--sqlite PATH] [--pg-url URL]

Reads DATABASE_URL from env if --pg-url is not provided.
Reads PASSPORT_PLATFORM_DB_PATH from env if --sqlite is not provided.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sqlite3
import sys
from typing import Any

_BOOL_COLUMNS = {"is_passport", "is_complete"}


def _cast(col: str, value: Any) -> Any:
    """Cast SQLite values to Postgres-compatible types."""
    if col in _BOOL_COLUMNS and isinstance(value, int):
        return bool(value)
    return value


# Table migration order (respects foreign keys).
TABLES = [
    "users",
    "uploads",
    "processing_results",
    "masar_submissions",
    "usage_ledger",
    "temp_tokens",
    "extension_sessions",
    "broadcasts",
]


def migrate(sqlite_path: str, pg_url: str, *, dry_run: bool = False) -> None:
    """Migrate all data from SQLite to PostgreSQL."""
    import psycopg
    from psycopg import sql

    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row

    dst: Any = psycopg.connect(pg_url, autocommit=False)

    try:
        for table in TABLES:
            rows = src.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
            if not rows:
                print(f"  {table}: 0 rows (skip)")
                continue

            columns = rows[0].keys()
            col_ids = [sql.Identifier(c) for c in columns]
            query = sql.SQL(
                "INSERT INTO {table} ({cols}) OVERRIDING SYSTEM VALUE VALUES ({phs})"
            ).format(
                table=sql.Identifier(table),
                cols=sql.SQL(", ").join(col_ids),
                phs=sql.SQL(", ").join([sql.Placeholder()] * len(columns)),
            )

            for row in rows:
                values = tuple(_cast(col, row[col]) for col in columns)
                dst.execute(query, values)

            print(f"  {table}: {len(rows)} rows migrated")

        # Reset sequences so new inserts get correct IDs.
        for table in TABLES:
            with contextlib.suppress(Exception):
                dst.execute(
                    sql.SQL(
                        "SELECT setval(pg_get_serial_sequence({tbl}, 'id'), "
                        "COALESCE((SELECT MAX(id) FROM {table}), 1))"
                    ).format(tbl=sql.Literal(table), table=sql.Identifier(table))
                )

        if dry_run:
            print("\n  [DRY RUN] Rolling back — no data written.")
            dst.rollback()
        else:
            dst.commit()
            print("\n  ✅ Migration committed successfully.")

        # Verify counts.
        print("\n  Verification:")
        for table in TABLES:
            src_count = src.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
            if dry_run:
                print(f"    {table}: {src_count} (source)")
            else:
                dst_row = dst.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                ).fetchone()
                dst_count = dst_row[0] if dst_row else 0
                match = "✅" if src_count == dst_count else "❌ MISMATCH"
                print(f"    {table}: {src_count} → {dst_count} {match}")

    except Exception:
        dst.rollback()
        raise
    finally:
        src.close()
        dst.close()


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Migrate SQLite → PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Validate without committing")
    parser.add_argument("--sqlite", default=None, help="SQLite file path")
    parser.add_argument("--pg-url", default=None, help="PostgreSQL connection URL")
    args = parser.parse_args()

    sqlite_path = args.sqlite or os.environ.get(
        "PASSPORT_PLATFORM_DB_PATH", "data/platform.sqlite3"
    )
    pg_url = args.pg_url or os.environ.get("PASSPORT_PLATFORM_DATABASE_URL")

    if not pg_url:
        print("Error: --pg-url or PASSPORT_PLATFORM_DATABASE_URL required", file=sys.stderr)
        return 1

    print(f"Source: {sqlite_path}")
    print(f"Target: {pg_url.split('@')[1] if '@' in pg_url else pg_url}")
    print(f"Mode:   {'DRY RUN' if args.dry_run else 'LIVE'}\n")

    migrate(sqlite_path, pg_url, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
