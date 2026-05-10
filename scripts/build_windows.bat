REM Snekbooru Secondary Windows Build Script
@echo off
echo Building Snekbooru for Windows...

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH.
    exit /b 1
)

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Installing requirements...
call venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller

echo Running PyInstaller...
pyinstaller Snekbooru.spec --noconfirm

echo Build complete! The executable can be found in the dist directory.
pause
