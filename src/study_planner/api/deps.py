"""FastAPI dependencies: DB session, current user, client IP."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from study_planner.api.db import get_session
from study_planner.api.models import User
from study_planner.api.security import decode_token

_bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str:
    # Behind a proxy, prefer the first X-Forwarded-For hop; else the peer.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = decode_token(creds.credentials, "access")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


async def get_verified_user(user: User = Depends(get_current_user)) -> User:
    """Routes that require a confirmed email (e.g. generating a plan)."""
    if not user.is_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Please verify your email before creating a plan")
    return user
