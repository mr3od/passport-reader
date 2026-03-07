from __future__ import annotations

import argparse
import json
from pathlib import Path

from passport_core.config import Settings
from passport_core.log import setup_logging
from passport_core.pipeline import PassportCoreService


def main() -> int:
    parser = argparse.ArgumentParser(description="Passport core processing CLI")
    parser.add_argument("sources", nargs="+", help="Image file paths or URLs")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    parser.add_argument("--csv-output", type=Path, help="Optional CSV export path")
    parser.add_argument("--log-level", default=None, help="Logging level")
    parser.add_argument("--log-json", action="store_true", help="Enable JSON logging")

    args = parser.parse_args()

    settings = Settings()
    setup_logging(
        args.log_level or settings.log_level,
        json_output=args.log_json or settings.log_json,
    )

    service = PassportCoreService(settings=settings)
    try:
        results = service.process_sources(args.sources)

        if args.csv_output:
            service.export_results_csv(results, args.csv_output)

        payload = [result.model_dump(mode="json") for result in results]
        print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
