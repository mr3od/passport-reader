from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from passport_platform import (
    AuthenticatedSession,
    InvalidExtensionSessionError,
    UserBlockedError,
)

from passport_api.config import ApiSettings
from passport_api.services import ApiServices, build_services


@lru_cache
def get_settings() -> ApiSettings:
    return ApiSettings()


@lru_cache
def get_services() -> ApiServices:
    return build_services(get_settings())


def get_api_services() -> ApiServices:
    return get_services()


def get_bearer_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing authorization header",
        )
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authorization header",
        )
    return value


def get_authenticated_session(
    token: Annotated[str, Depends(get_bearer_token)],
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> AuthenticatedSession:
    try:
        return services.auth.authenticate_session(token)
    except InvalidExtensionSessionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except UserBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
