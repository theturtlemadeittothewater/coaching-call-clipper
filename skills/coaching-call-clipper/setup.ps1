# Set up the coaching-call-clipper Python environment (Windows).
# Creates a fixed, user-level virtual environment at
# %USERPROFILE%\.coaching-call-clipper\.venv, installs faster-whisper, and adds the
# NVIDIA CUDA wheels when a GPU is detected. Safe to re-run.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvRoot  = Join-Path $env:USERPROFILE ".coaching-call-clipper"
$VenvDir   = Join-Path $VenvRoot ".venv"
$VenvPy    = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "coaching-call-clipper setup (Windows)" -ForegroundColor Cyan

# 1. Python present?
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) {
    Write-Host "Python was not found on PATH. Install Python 3.9+ from python.org, then re-run this script." -ForegroundColor Red
    exit 1
}

# 2. Create the venv if missing.
if (-not (Test-Path $VenvPy)) {
    Write-Host "Creating virtual environment at $VenvDir ..."
    New-Item -ItemType Directory -Force -Path $VenvRoot | Out-Null
    & $py.Source -m venv $VenvDir
} else {
    Write-Host "Virtual environment already exists at $VenvDir."
}

# 3. Install dependencies.
Write-Host "Installing dependencies (this can take a few minutes the first time)..."
& $VenvPy -m pip install --upgrade pip
& $VenvPy -m pip install -r (Join-Path $ScriptDir "requirements.txt")

# 4. GPU wheels if an NVIDIA GPU is present.
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    Write-Host "NVIDIA GPU detected; installing CUDA wheels for GPU transcription..."
    & $VenvPy -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
} else {
    Write-Host "No NVIDIA GPU detected; transcription will run on CPU (slower, but works)." -ForegroundColor Yellow
}

# 5. ffmpeg check.
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "ffmpeg found." -ForegroundColor Green
} else {
    Write-Host "ffmpeg was NOT found on PATH. Install it before transcribing or exporting:" -ForegroundColor Yellow
    Write-Host "    winget install Gyan.FFmpeg     (or)     choco install ffmpeg"
}

Write-Host ""
Write-Host "Done. Interpreter: $VenvPy" -ForegroundColor Green
