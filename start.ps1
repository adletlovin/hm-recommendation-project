$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt

if (-not (Test-Path "data\processed\app_data.json.gz")) {
    & ".\.venv\Scripts\python.exe" preprocess.py
}

Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:8000"
} | Out-Null
& ".\.venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000
