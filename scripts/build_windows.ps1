# Snekbooru Windows Build Script
Write-Host "Building Snekbooru for Windows..." -ForegroundColor Cyan

if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is not installed or not in PATH."
    exit 1
}

if (!(Test-Path "venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
}

Write-Host "Installing requirements..."
& .\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

Write-Host "Running PyInstaller..."
pyinstaller Snekbooru.spec --noconfirm

Write-Host "Build complete! The executable is in the 'dist' directory." -ForegroundColor Green
