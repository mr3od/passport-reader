from __future__ import annotations

import uvicorn

from passport_api.config import ApiSettings


def main() -> int:
    settings = ApiSettings()
    uvicorn.run(
        "passport_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
