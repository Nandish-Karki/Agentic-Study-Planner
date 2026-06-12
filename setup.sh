#!/usr/bin/env bash
# Agentic Study Planner - one-command setup (macOS / Linux)
# Usage:  ./setup.sh
set -e

# 1. Python 3.10-3.13
PY=""
for cand in python3.10 python3.11 python3.12 python3.13 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        v=$("$cand" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        case "$v" in 3.10|3.11|3.12|3.13) PY=$cand; break;; esac
    fi
done
if [ -z "$PY" ]; then
    echo "[FAIL] no Python 3.10-3.13 found."
    echo "       FIX: install python3.10 (e.g. 'brew install python@3.10' or your distro package)"
    exit 1
fi
echo "[ OK ] using $PY ($($PY --version))"

# 2. Virtual environment + dependencies
if [ ! -d .venv ]; then
    echo "[....] creating .venv ..."
    "$PY" -m venv .venv
fi
echo "[....] installing dependencies (takes a few minutes on first run) ..."
./.venv/bin/pip install -q -e .
echo "[ OK ] dependencies installed"

# 3. .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[ACTION REQUIRED] .env created from template."
    echo "    Open .env and paste your token (see README 'Workshop quickstart' for"
    echo "    how to create a free GitHub Models token). Then re-run ./setup.sh"
    exit 0
fi
echo "[ OK ] .env exists"

# 4. Preflight check against the bundled sample data
./.venv/bin/python -m study_planner.check sample_data
echo ""
echo "Setup complete. Try it:"
echo "    ./.venv/bin/python -m study_planner.main sample_data"
