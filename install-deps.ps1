# Keyframe Pro Linux — Windows installer (PowerShell)
#
# Usage (open PowerShell in the project folder):
#     .\install-deps.ps1
#
# If you get "running scripts is disabled on this system", run once:
#     Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

$ErrorActionPreference = "Stop"

Write-Host "Keyframe Pro Linux — Windows setup" -ForegroundColor Cyan

# 1) Python check
$py = (Get-Command python -ErrorAction SilentlyContinue) `
    ?? (Get-Command py -ErrorAction SilentlyContinue)
if (-not $py) {
    Write-Host "Python is not installed. Install Python 3.10+ from python.org first." -ForegroundColor Red
    Write-Host "  https://www.python.org/downloads/windows/"
    exit 1
}
$pyVersion = & $py.Source --version 2>&1
Write-Host "Found $pyVersion at $($py.Source)"

# 2) mpv / libmpv DLL check
$dllNames = @("libmpv-2.dll", "mpv-2.dll", "libmpv-1.dll", "mpv-1.dll")
$foundDll = $null
foreach ($name in $dllNames) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $foundDll = $cmd.Source; break }
}
if (-not $foundDll) {
    Write-Host ""
    Write-Host "libmpv DLL not found on PATH." -ForegroundColor Yellow
    Write-Host "Install mpv:" -ForegroundColor Yellow
    Write-Host "  Option A — winget:    winget install mpv.net"
    Write-Host "  Option B — chocolatey: choco install mpv"
    Write-Host "  Option C — manual:    download mpv from https://mpv.io/installation/"
    Write-Host "                        and place libmpv-2.dll on PATH"
    Write-Host ""
    Write-Host "After installing, re-run this script."
    exit 1
}
Write-Host "Found libmpv: $foundDll"

# 3) ffmpeg check (optional but recommended)
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    Write-Host ""
    Write-Host "ffmpeg not found on PATH (needed for export + source thumbnails)." -ForegroundColor Yellow
    Write-Host "Install: winget install Gyan.FFmpeg   (or:   choco install ffmpeg)"
    Write-Host "App will still launch and play video — only export/thumbnails will be disabled."
    Write-Host ""
} else {
    Write-Host "Found ffmpeg: $($ffmpeg.Source)"
}

# 4) Create venv
Write-Host ""
Write-Host "Creating virtual environment in .venv ..."
& $py.Source -m venv .venv
$venvPython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Failed to create venv at $venvPython" -ForegroundColor Red
    exit 1
}

# 5) Install Python deps + project
Write-Host "Installing Python dependencies ..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt
& $venvPython -m pip install -e .

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "To run:"
Write-Host "    .\run.bat"
Write-Host "    .\run.bat C:\path\to\video.mp4"
Write-Host ""
Write-Host "Or manually:"
Write-Host "    .\.venv\Scripts\activate"
Write-Host "    python -m keyframe_pro"
