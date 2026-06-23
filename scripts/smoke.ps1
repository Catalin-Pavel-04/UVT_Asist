param(
    [switch]$DemoCheck
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

& $Python backend\scripts\smoke_retrieval.py

if ($DemoCheck) {
    & $Python backend\scripts\demo_check.py
}
