param(
    [switch]$IncludeQdrantStorage,
    [switch]$IncludeRootVenv,
    [switch]$StopBackendVenvProcesses
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Resolve-WorkspacePath {
    param([string]$RelativePath)

    $candidate = Join-Path $Root $RelativePath
    if (-not (Test-Path -LiteralPath $candidate)) {
        return $null
    }

    $resolved = (Resolve-Path -LiteralPath $candidate).Path
    if (-not ($resolved -eq $Root -or $resolved.StartsWith($Root + [IO.Path]::DirectorySeparatorChar))) {
        throw "Refuz stergerea in afara workspace-ului: $resolved"
    }

    return $resolved
}

function Get-DirectorySizeMb {
    param([string]$Path)

    $size = (Get-ChildItem -LiteralPath $Path -Force -Recurse -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum).Sum
    if ($null -eq $size) {
        $size = 0
    }
    return [math]::Round($size / 1MB, 2)
}

if ($StopBackendVenvProcesses) {
    $backendVenv = Resolve-WorkspacePath "backend/.venv"
    if ($backendVenv) {
        $processes = Get-CimInstance Win32_Process |
            Where-Object { $_.CommandLine -and $_.CommandLine.Contains($backendVenv) }
        foreach ($process in $processes) {
            Stop-Process -Id $process.ProcessId -Force
        }
        Write-Host "Procese backend/.venv oprite: $($processes.Count)"
    }
}

$targets = @(
    "backend/.ocr-venv",
    "backend/.venv",
    "backend/data/evaluation",
    "backend/data/qdrant_local",
    "backend/logs",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "htmlcov"
)

if ($IncludeRootVenv) {
    $targets += ".venv"
}

if ($IncludeQdrantStorage) {
    $targets += "qdrant_storage"
}

$deleted = @()
$failed = @()

foreach ($relativePath in $targets) {
    $resolved = Resolve-WorkspacePath $relativePath
    if (-not $resolved) {
        continue
    }

    $sizeMb = Get-DirectorySizeMb $resolved
    try {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction Stop
        $deleted += [PSCustomObject]@{ Path = $relativePath; MB = $sizeMb }
    } catch {
        $failed += [PSCustomObject]@{ Path = $relativePath; Error = $_.Exception.Message }
    }
}

$pycacheTargets = Get-ChildItem -Path (Join-Path $Root "backend") -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\.venv\\|\\.ocr-venv\\" }

$pycacheDeleted = 0
foreach ($directory in $pycacheTargets) {
    if (-not $directory.FullName.StartsWith($Root + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refuz stergerea in afara workspace-ului: $($directory.FullName)"
    }

    try {
        Remove-Item -LiteralPath $directory.FullName -Recurse -Force -ErrorAction Stop
        $pycacheDeleted += 1
    } catch {
        $failed += [PSCustomObject]@{ Path = $directory.FullName.Substring($Root.Length + 1); Error = $_.Exception.Message }
    }
}

Write-Host "Tintele sterse:"
$deleted | Format-Table -AutoSize
Write-Host "Directoare __pycache__ sterse: $pycacheDeleted"

if ($failed.Count -gt 0) {
    Write-Host "Tintele care nu au putut fi sterse:"
    $failed | Format-Table -AutoSize
    exit 1
}
