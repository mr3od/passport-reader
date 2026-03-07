from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from passport_core.pipeline import PassportCoreService


def main() -> int:
    parser = argparse.ArgumentParser(description="Passport core processing CLI")
    parser.add_argument("sources", nargs="+", help="Image file paths or URLs")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    parser.add_argument("--csv-output", type=Path, help="Optional CSV export path")
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    service = PassportCoreService()
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
