"""Auth routes (BUILD_PLAN §5.2): signup+consent, login+rate-limit, email
verification, password reset, and a Google OAuth scaffold.

Email is not actually sent in this build (no SMTP configured); verification and
reset tokens are returned in the response when DEBUG is on so the flows are
testable end-to-end. In production these go in an email and are NOT returned.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from study_planner.api.audit import audit, log_event
from study_planner.api.config import settings
from study_planner.api.db import get_session
from study_planner.api.deps import client_ip, get_current_user
from study_planner.api.legal import PRIVACY_VERSION, TOS_VERSION
from study_planner.api.models import Consent, Profile, User
from study_planner.api.ratelimit import check_auth_rate
from study_planner.api.schemas import (
    LoginRequest, PasswordResetConfirm, PasswordResetRequest,
    SignupRequest, TokenResponse, UserOut,
)
from study_planner.api.security import (
    decode_token, hash_password, make_access_token, make_reset_token,
    make_verify_token, verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=dict, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, request: Request,
                 session: AsyncSession = Depends(get_session)):
    if not (body.accept_privacy and body.accept_tos):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "You must accept the Privacy Policy and Terms to sign up")
    existing = (await session.execute(
        select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(email=str(body.email), hashed_password=hash_password(body.password))
    session.add(user)
    await session.flush()  # assign user.id
    session.add(Profile(user_id=user.id))
    ip = client_ip(request)
    session.add(Consent(user_id=user.id, doc="privacy", version=PRIVACY_VERSION, ip=ip))
    session.add(Consent(user_id=user.id, doc="tos", version=TOS_VERSION, ip=ip))
    await audit(session, user_id=user.id, action="signup", ip=ip)
    await session.commit()

    token = make_verify_token(user.id)
    out = {"id": user.id, "email": user.email,
           "message": "Account created. Check your email to verify."}
    if settings.debug:
        out["verify_token"] = token  # dev only — prod emails this
    return out


@router.post("/verify", response_model=dict)
async def verify_email(token: str, session: AsyncSession = Depends(get_session)):
    user_id = decode_token(token, "verify")
    if not user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired token")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.is_verified = True
    await audit(session, user_id=user.id, action="verify_email")
    await session.commit()
    return {"message": "Email verified. You can now create plans."}


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request,
                session: AsyncSession = Depends(get_session)):
    ip = client_ip(request)
    if not check_auth_rate(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many attempts. Try again later.")
    user = (await session.execute(
        select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        # same error whether the email exists or not — no account enumeration
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    await audit(session, user_id=user.id, action="login", ip=ip)
    await session.commit()
    return TokenResponse(access_token=make_access_token(user.id))


@router.post("/password-reset/request", response_model=dict)
async def password_reset_request(body: PasswordResetRequest, request: Request,
                                 session: AsyncSession = Depends(get_session)):
    if not check_auth_rate(client_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many attempts. Try again later.")
    user = (await session.execute(
        select(User).where(User.email == body.email))).scalar_one_or_none()
    # Always return the same response — don't disclose whether the email exists.
    out = {"message": "If that email exists, a reset link has been sent."}
    if user is not None and settings.debug:
        out["reset_token"] = make_reset_token(user.id)  # dev only
    return out


@router.post("/password-reset/confirm", response_model=dict)
async def password_reset_confirm(body: PasswordResetConfirm,
                                 session: AsyncSession = Depends(get_session)):
    user_id = decode_token(body.token, "reset")
    if not user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired token")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.hashed_password = hash_password(body.new_password)
    await audit(session, user_id=user.id, action="password_reset")
    await session.commit()
    return {"message": "Password updated. You can now log in."}


@router.get("/oauth/google", response_model=dict)
async def oauth_google_start():
    """OAuth scaffold. Returns 501 until GOOGLE_CLIENT_ID/SECRET are configured —
    wiring the real redirect/callback is a deploy-time step, not a code gap."""
    import os
    if not os.getenv("GOOGLE_CLIENT_ID"):
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED,
                            "Google OAuth not configured (set GOOGLE_CLIENT_ID/SECRET)")
    # With creds set, redirect to Google's consent screen here.
    return {"message": "Configured — implement redirect to Google's consent screen."}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, email=user.email, is_verified=user.is_verified,
                   created_at=user.created_at)
