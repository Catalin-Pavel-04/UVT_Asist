param(
    [switch]$FullStack
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

function Invoke-CheckedCommand {
    param(
        [string]$Label,
        [string]$Executable,
        [string[]]$Arguments
    )

    Write-Host ""
    Write-Host "==> $Label"
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Error "$Label failed with exit code $LASTEXITCODE."
        exit $LASTEXITCODE
    }
}

Write-Host "UVT_Asist final demo check"
Write-Host "Repository root: $RepoRoot"
Write-Host "Python: $Python"

$RequiredFiles = @(
    "backend\.env",
    "backend\app.py",
    "backend\build_index.py",
    "backend\data\page_index.json",
    "extension\manifest.json",
    "extension\popup.html",
    "docs\architecture.md",
    "docs\evaluation\methodology.md"
)

Write-Host ""
Write-Host "==> Checking important files"
foreach ($Path in $RequiredFiles) {
    if (Test-Path $Path) {
        Write-Host "[OK] $Path"
    }
    else {
        Write-Warning "[MISSING] $Path"
    }
}

Invoke-CheckedCommand `
    -Label "Compiling backend Python files" `
    -Executable $Python `
    -Arguments @("-m", "compileall", "backend")

Invoke-CheckedCommand `
    -Label "Running pytest" `
    -Executable $Python `
    -Arguments @("-m", "pytest")

if ($FullStack) {
    Invoke-CheckedCommand `
        -Label "Running retrieval smoke test" `
        -Executable $Python `
        -Arguments @("backend\scripts\smoke_retrieval.py")

    Invoke-CheckedCommand `
        -Label "Running demo readiness check" `
        -Executable $Python `
        -Arguments @("backend\scripts\demo_check.py")
}
else {
    Write-Host ""
    Write-Host "Skipping full-stack checks. Run .\scripts\final_check.ps1 -FullStack after starting Ollama and Qdrant."
}

Write-Host ""
Write-Host "Final check completed."
