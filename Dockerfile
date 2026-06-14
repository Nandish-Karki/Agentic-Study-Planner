# API + worker image (BUILD_PLAN deploy). One image runs both the web service
# (uvicorn) and the RQ worker — the command differs per service in compose/render.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUTF8=1

WORKDIR /app

# System deps occasionally needed by crewai/litellm wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[api]"

# Default: web service. Override the command for the worker.
EXPOSE 8000
CMD ["uvicorn", "study_planner.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
