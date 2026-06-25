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

function Invoke-PythonChecked {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

if (-not $SkipCompile) {
    $CompileExclude = '(^|[\\/])(\.venv|\.ocr-venv|__pycache__)([\\/]|$)'
    Invoke-PythonChecked -m compileall -q -x $CompileExclude backend
}

if ($Coverage) {
    Invoke-PythonChecked -m pytest --cov=backend
}
else {
    Invoke-PythonChecked -m pytest
}

if ($EvaluateRag) {
    if (Test-Path "backend\scripts\evaluate_rag.py") {
        Invoke-PythonChecked backend\scripts\evaluate_rag.py
    }
    else {
        Write-Host "backend\scripts\evaluate_rag.py does not exist; skipping RAG evaluation."
    }
}
