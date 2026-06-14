"""Public legal routes (BUILD_PLAN §5.1). Unauthenticated by design — these are
the documented public exceptions to auth-by-default."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from study_planner.api import legal

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/privacy", response_class=PlainTextResponse)
async def privacy():
    return legal.PRIVACY_POLICY


@router.get("/tos", response_class=PlainTextResponse)
async def tos():
    return legal.TERMS_OF_SERVICE


@router.get("/cookie", response_class=PlainTextResponse)
async def cookie():
    return legal.COOKIE_NOTICE
