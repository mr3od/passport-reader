from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from passport_platform import InvalidTempTokenError, UserBlockedError
from passport_platform.enums import ExternalProvider, PlanName
from passport_platform.schemas.commands import EnsureUserCommand

from passport_api.deps import get_api_services, get_authenticated_session, get_settings
from passport_api.schemas import ExchangeTokenRequest, ExchangeTokenResponse, MeResponse
from passport_api.services import ApiServices

router = APIRouter(tags=["auth"])


@router.post("/auth/exchange", response_model=ExchangeTokenResponse)
def exchange_token(
    payload: ExchangeTokenRequest,
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> ExchangeTokenResponse:
    try:
        issued = services.auth.exchange_temp_token(payload.token)
    except InvalidTempTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except UserBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return ExchangeTokenResponse(
        session_token=issued.session_token,
        expires_at=issued.expires_at,
    )


@router.post("/auth/dev-token", response_model=ExchangeTokenResponse)
def dev_token(
    services: Annotated[ApiServices, Depends(get_api_services)],
    settings: Annotated[object, Depends(get_settings)],
    x_dev_secret: Annotated[str | None, Header()] = None,
) -> ExchangeTokenResponse:
    if not settings.dev_token_secret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if x_dev_secret != settings.dev_token_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid dev secret")
    user = services.users.get_or_create_user(
        EnsureUserCommand(
            external_provider=ExternalProvider.API,
            external_user_id="local-dev",
            display_name="Local Dev",
            default_plan=PlanName.PRO,
        )
    )
    issued = services.auth.issue_dev_session(user.id)
    return ExchangeTokenResponse(session_token=issued.session_token, expires_at=issued.expires_at)


@router.get("/me", response_model=MeResponse)
def me(
    authenticated: Annotated[object, Depends(get_authenticated_session)],
) -> MeResponse:
    user = authenticated.user
    return MeResponse(
        user_id=user.id,
        external_provider=user.external_provider.value,
        external_user_id=user.external_user_id,
        display_name=user.display_name,
        plan=user.plan.value,
        status=user.status.value,
    )
