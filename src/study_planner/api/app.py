"""FastAPI application factory (BUILD_PLAN §3.3).

Auth is required on every route by default; the documented public exceptions are
/healthz and the /legal/* pages. The frontend (B6) will call this API.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev/SQLite convenience: create tables on boot. Prod Postgres uses migrations.
    from study_planner.api.config import settings
    if settings.is_sqlite:
        from study_planner.api.db import init_db
        await init_db()
    yield


def create_app() -> FastAPI:
    from study_planner.api.routes import account, auth, legal, plans

    app = FastAPI(title="Study Planner API", version="1.0", lifespan=lifespan)

    # CORS — lock to the frontend origin in prod via ALLOWED_ORIGINS.
    import os
    origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(plans.router)
    app.include_router(account.router)
    app.include_router(legal.router)

    @app.get("/healthz", tags=["health"])
    async def healthz():
        return {"status": "ok"}

    return app


app = create_app()
