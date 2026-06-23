$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

$Python = "python"
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    & $Python -m venv .venv
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r backend\requirements.txt

if (Test-Path "requirements-dev.txt") {
    & $VenvPython -m pip install -r requirements-dev.txt
}

if ((Test-Path "backend\.env.example") -and -not (Test-Path "backend\.env")) {
    Copy-Item "backend\.env.example" "backend\.env"
    Write-Host "Created backend\.env from backend\.env.example"
}
elseif (Test-Path "backend\.env") {
    Write-Host "backend\.env already exists; leaving it unchanged."
}

Write-Host "Setup complete. Use .\.venv\Scripts\activate to activate the environment manually."
