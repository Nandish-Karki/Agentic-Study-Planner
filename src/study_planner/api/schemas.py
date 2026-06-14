"""Pydantic request/response models for the API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ─── auth ──────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    accept_privacy: bool
    accept_tos: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    is_verified: bool
    created_at: datetime


# ─── plans ─────────────────────────────────────────────────────────────────────

class ConstraintsIn(BaseModel):
    degree_type: str = "master"
    target_semesters: int = Field(default=4, ge=1, le=12)
    default_cp_per_semester: int | None = Field(default=None, ge=1, le=60)
    cp_overrides: dict[int, int] = Field(default_factory=dict)
    total_coursework_cp: int | None = Field(default=None, ge=1, le=400)


class JobOut(BaseModel):
    id: str
    status: str
    provider: str | None = None
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class ValidationOut(BaseModel):
    ok: bool
    errors: list[dict]
    warnings: list[dict]
    stats: dict


class PlanOut(BaseModel):
    job_id: str
    status: str
    study_plan_md: str | None = None
    skill_gaps_md: str | None = None
    validation: ValidationOut | None = None
    created_at: datetime | None = None
