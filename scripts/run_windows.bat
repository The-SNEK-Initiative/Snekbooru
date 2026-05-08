@echo off
echo Starting Snekbooru...

if exist "venv" (
    call venv\Scripts\activate
)

python snekbooru\main.py
pause
