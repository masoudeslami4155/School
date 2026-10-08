# ------------------------------------------------------------------
# Script: tools/setup-hooks.ps1
# Purpose: One-command setup for Git hooks on a fresh clone (Windows).
# Usage:   powershell -File tools/setup-hooks.ps1
# Note:    This is a thin wrapper; the real installer is the portable
#          python script tools/install_hooks.py (also run automatically
#          at application start).
# ------------------------------------------------------------------

$ErrorActionPreference = "Stop"

$RepoRoot = git rev-parse --show-toplevel 2>$null
if (-not $?) {
    Write-Host "[X] Not inside a Git repository." -ForegroundColor Red
    exit 1
}

Set-Location $RepoRoot

$Python = $null
foreach ($candidate in @("python", "py")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $Python = $candidate
        break
    }
}
if (-not $Python) {
    Write-Host "[X] Python not found. Install Python 3.10+ first." -ForegroundColor Red
    exit 1
}

& $Python "tools/install_hooks.py" @args
exit $LASTEXITCODE
