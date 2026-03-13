from __future__ import annotations

from fastapi import FastAPI

from passport_api.routes import auth_router, records_router


def create_app() -> FastAPI:
    app = FastAPI(title="passport-api", version="0.1.0")
    app.include_router(auth_router)
    app.include_router(records_router)
    return app
