param(
    [string]$PythonVersion = "3.11",
    [ValidateSet("cpu", "gpu-cu118", "gpu-cu126")]
    [string]$Runtime = "cpu"
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\\..")
$venvPath = Join-Path $projectRoot "backend\\.ocr-venv"
$venvPython = Join-Path $venvPath "Scripts\\python.exe"

if (-not (Test-Path $venvPath)) {
    py -$PythonVersion -m venv $venvPath
}

if (-not (Test-Path $venvPython)) {
    throw "OCR venv Python not found at $venvPython"
}

& $venvPython -m ensurepip --upgrade
& $venvPython -m pip install --upgrade pip setuptools wheel

switch ($Runtime) {
    "cpu" {
        & $venvPython -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
    }
    "gpu-cu118" {
        & $venvPython -m pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/
    }
    "gpu-cu126" {
        & $venvPython -m pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
    }
}

& $venvPython -m pip install -r (Join-Path $projectRoot "backend\\requirements-ocr.txt")

Write-Host "OCR venv ready: $venvPython"
