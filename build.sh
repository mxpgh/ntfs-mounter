#!/bin/bash
# Build NTFS Mounter into a standalone .app bundle.
# Requires: pip install pyinstaller rumps pyobjc

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SPEC_FILE="$PROJECT_DIR/NTFS Mounter.spec"
APP="$PROJECT_DIR/dist/NTFS Mounter.app"

cd "$PROJECT_DIR"

echo "=== Cleaning previous builds ==="
rm -rf "$PROJECT_DIR/build" "$PROJECT_DIR/dist"

echo "=== Building with PyInstaller ==="
pyinstaller --clean --noconfirm "$SPEC_FILE"

echo ""
echo "=== Build complete ==="
echo "App: $APP"
echo "Size: $(du -sh "$APP" | cut -f1)"
echo ""
echo "To test:   open \"$APP\""
echo "To install: cp -r \"$APP\" /Applications/"
