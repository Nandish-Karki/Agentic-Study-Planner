"""Password hashing + signed tokens (BUILD_PLAN §5.2).

Hand-rolled, full control (the locked auth decision). bcrypt for passwords; JWTs
for the access token and for purpose-scoped email-verification / password-reset
links (stateless, short-TTL, signed with SECRET_KEY — no token table to leak).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from study_planner.api.config import settings

ALGORITHM = "HS256"
_BCRYPT_MAX = 72  # bcrypt ignores bytes past 72; truncate explicitly to be safe


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:_BCRYPT_MAX]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:_BCRYPT_MAX],
                              hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _make_token(sub: str, purpose: str, ttl_min: int, **extra) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "purpose": purpose,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_min),
        **extra,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def make_access_token(user_id: str) -> str:
    return _make_token(user_id, "access", settings.access_token_ttl_min)


def make_verify_token(user_id: str) -> str:
    return _make_token(user_id, "verify", 60 * 24)  # 24h


def make_reset_token(user_id: str) -> str:
    return _make_token(user_id, "reset", 60)  # 1h


def decode_token(token: str, expected_purpose: str) -> str | None:
    """Return the subject (user_id) if the token is valid for `expected_purpose`."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("purpose") != expected_purpose:
        return None
    return payload.get("sub")
