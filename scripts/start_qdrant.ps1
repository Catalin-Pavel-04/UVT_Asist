$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

docker compose up -d qdrant

Write-Host "Qdrant requested through Docker Compose."
Write-Host "Health check: Invoke-RestMethod http://127.0.0.1:6333/collections"
