"""Production HTTP API for the study planner (BUILD_PLAN.md §3-§5).

Self-hosted FastAPI + SQLAlchemy(async) + hand-rolled JWT auth. Multi-tenant:
every owned row carries user_id and every read scopes by it (404 on mismatch).
"""
