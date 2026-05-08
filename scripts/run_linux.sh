#!/bin/bash
set -e

find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install wheel
pip install -r requirements.txt

echo "Starting Snekbooru (Linux)..."
export PYTHONPATH=$PYTHONPATH:.
python3 -m snekbooru_linux.main


# source venv/bin/activate
# python3 -m snekbooru_linux.main
