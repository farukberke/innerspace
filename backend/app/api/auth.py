from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from app.api.deps import (
    CurrentUser,
    RateLimiterDep,
    SessionDep,
    SettingsDep,
    client_ip,
    limit_per_ip,
)
from app.core.ratelimit import parse_limit
from app.schemas.care import (
    InvitationAccept,
    LoginRequest,
    RefreshRequest,
    TokenPair,
    UserRead,
)
from app.services import auth as service
from app.services import invitations
from app.services.errors import InvalidCredentialsError, InvalidInvitationError

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(pair: tuple[str, str]) -> TokenPair:
    return TokenPair(access_token=pair[0], refresh_token=pair[1])


@router.post("/login")
async def login(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    limiter: RateLimiterDep,
    data: Annotated[LoginRequest, Body()],
) -> TokenPair:
    # Brute force is limited per source IP and, separately, per target account.
    await limiter.check("login_ip", client_ip(request), parse_limit(settings.rate_limit_login_ip))
    await limiter.check("login_email", data.email, parse_limit(settings.rate_limit_login_email))
    try:
        return _tokens(await service.authenticate(session, settings, data.email, data.password))
    except InvalidCredentialsError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from None


@router.post("/refresh", dependencies=[Depends(limit_per_ip("refresh"))])
async def refresh(
    session: SessionDep, settings: SettingsDep, data: Annotated[RefreshRequest, Body()]
) -> TokenPair:
    try:
        return _tokens(await service.refresh(session, settings, data.refresh_token))
    except InvalidCredentialsError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_per_ip("refresh"))],
)
async def logout(
    session: SessionDep, settings: SettingsDep, data: Annotated[RefreshRequest, Body()]
) -> None:
    """Revokes the refresh token's session. Always 204 (idempotent, reveals nothing)."""
    await service.logout(session, settings, data.refresh_token)


@router.get("/me")
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.post(
    "/accept-invitation",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_per_ip("accept_invitation"))],
)
async def accept_invitation(
    session: SessionDep, data: Annotated[InvitationAccept, Body()]
) -> UserRead:
    """Public: the invitation token is the credential. Creates the account (no open sign-up)."""
    try:
        user = await invitations.accept_invitation(
            session, data.token, password=data.password, display_name=data.display_name
        )
    except InvalidInvitationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired invitation") from None
    return UserRead.model_validate(user)
