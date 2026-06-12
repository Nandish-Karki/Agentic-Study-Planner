# Agentic Study Planner - one-command setup (Windows)
# Usage:  .\setup.ps1
$ErrorActionPreference = "Stop"

# 1. Python 3.10 (CrewAI deps have no Python 3.14 wheels on Windows)
try {
    $pyver = & py -3.10 --version
    Write-Host "[ OK ] $pyver"
} catch {
    Write-Host "[FAIL] Python 3.10 not found."
    Write-Host "       FIX: install it from https://www.python.org/downloads/release/python-31011/"
    Write-Host "            (any 3.10-3.13 works; then re-run .\setup.ps1)"
    exit 1
}

# 2. Virtual environment + dependencies
if (-not (Test-Path .venv)) {
    Write-Host "[....] creating .venv ..."
    py -3.10 -m venv .venv
}
Write-Host "[....] installing dependencies (takes a few minutes on first run) ..."
.\.venv\Scripts\pip install -q -e .
Write-Host "[ OK ] dependencies installed"

# 3. .env
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "[ACTION REQUIRED] .env created from template."
    Write-Host "    Open .env and paste your token (see README 'Workshop quickstart' for"
    Write-Host "    how to create a free GitHub Models token). Then re-run .\setup.ps1"
    exit 0
}
Write-Host "[ OK ] .env exists"

# 4. Preflight check against the bundled sample data
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python -m study_planner.check sample_data
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Setup complete. Try it:"
    Write-Host "    `$env:PYTHONUTF8 = `"1`""
    Write-Host "    .\.venv\Scripts\python -m study_planner.main sample_data"
}
