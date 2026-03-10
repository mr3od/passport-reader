from __future__ import annotations

import argparse
import json
from pathlib import Path

from passport_core.config import Settings
from passport_core.log import setup_logging
from passport_core.pipeline import PassportCoreService

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Passport core CLI")
    parser.add_argument("--log-level", default=None, help="Logging level")
    parser.add_argument("--log-json", action="store_true", help="Enable JSON logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    process = subparsers.add_parser(
        "process",
        aliases=["simulate-agency"],
        help="Process one or many passport images and return unified results",
    )
    process.add_argument("sources", nargs="+", help="Image file paths")
    process.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    process.add_argument("--csv-output", type=Path, help="Optional CSV export path")
    process.add_argument("--out-json", type=Path, help="Optional JSON output path")

    process_dir = subparsers.add_parser(
        "process-dir",
        help="Process every supported image inside a directory as one agency batch",
    )
    process_dir.add_argument("input_dir", type=Path, help="Directory containing uploaded images")
    process_dir.add_argument(
        "--recursive",
        action="store_true",
        help="Walk subdirectories recursively",
    )
    process_dir.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    process_dir.add_argument("--csv-output", type=Path, help="Optional CSV export path")
    process_dir.add_argument("--out-json", type=Path, help="Optional JSON output path")

    crop = subparsers.add_parser(
        "crop-face",
        help="Validate a passport image and return the stored face crop metadata",
    )
    crop.add_argument("source", help="Image file path")
    crop.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    crop.add_argument("--out-json", type=Path, help="Optional JSON output path")

    return parser


def _dump_json(payload: object, out_json: Path | None, pretty: bool) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)
    if out_json is not None:
        out_json.write_text(text, encoding="utf-8")
    print(text)


def _collect_image_sources(input_dir: Path, recursive: bool) -> list[str]:
    if not input_dir.exists():
        raise FileNotFoundError(
            f"Input directory does not exist: {input_dir} (cwd: {Path.cwd()})"
        )
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    walker = input_dir.rglob("*") if recursive else input_dir.iterdir()
    sources = [
        str(path)
        for path in walker
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(sources)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    settings = Settings()
    setup_logging(
        args.log_level or settings.log_level,
        json_output=args.log_json or settings.log_json,
    )

    service = PassportCoreService(settings=settings)
    try:
        if args.command in {"process", "simulate-agency"}:
            results = service.process_sources(args.sources)

            if args.csv_output:
                service.export_results_csv(results, args.csv_output)

            payload = [result.model_dump(mode="json") for result in results]
            _dump_json(payload, args.out_json, args.pretty)
            return 0

        if args.command == "process-dir":
            sources = _collect_image_sources(args.input_dir, args.recursive)
            results = service.process_sources(sources)

            if args.csv_output:
                service.export_results_csv(results, args.csv_output)

            payload = [result.model_dump(mode="json") for result in results]
            _dump_json(payload, args.out_json, args.pretty)
            return 0

        if args.command == "crop-face":
            result = service.crop_face(args.source)
            payload = (
                None
                if result is None
                else result.model_dump(mode="json", exclude={"jpeg_bytes"})
            )
            _dump_json(payload, args.out_json, args.pretty)
            return 0

        parser.error(f"Unknown command: {args.command}")
    finally:
        service.close()

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
