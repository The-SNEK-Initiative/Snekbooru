#!/bin/bash
# Snekbooru Linux Build Script

set -e

echo "Building Snekbooru for Linux..."

if [ ! -d "snekbooru_linux" ]; then
    echo "Error: snekbooru_linux directory not found!"
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo "Creating build environment..."
rm -rf build_env
mkdir -p build_env/snekbooru

echo "Copying snekbooru_linux sources..."
cp -r snekbooru_linux/* build_env/snekbooru/

cp snekbooru_linux.spec build_env/

cd build_env

echo "Running PyInstaller..."
pyinstaller --clean --noconfirm snekbooru_linux.spec

cd ..
rm -rf dist
mkdir -p dist
mv build_env/dist/Snekbooru dist/Snekbooru

rm -rf build_env

deactivate

echo "Build complete! Output is in dist/Snekbooru/"
echo "You can run it with: ./dist/Snekbooru/Snekbooru"
