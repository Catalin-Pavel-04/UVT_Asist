param(
    [switch]$SkipCompile,
    [switch]$Coverage,
    [switch]$EvaluateRag
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

if (-not $SkipCompile) {
    & $Python -m compileall backend
}

if ($Coverage) {
    & $Python -m pytest --cov=backend
}
else {
    & $Python -m pytest
}

if ($EvaluateRag) {
    if (Test-Path "backend\scripts\evaluate_rag.py") {
        & $Python backend\scripts\evaluate_rag.py
    }
    else {
        Write-Host "backend\scripts\evaluate_rag.py does not exist; skipping RAG evaluation."
    }
}
