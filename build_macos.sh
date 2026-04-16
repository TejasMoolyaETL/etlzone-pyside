#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="Etlzone"
SPEC_FILE="MY_ETLZONE_App_macos.spec"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
DMG_NAME="${APP_NAME}-macOS.dmg"
DMG_STAGING_DIR="dist/${APP_NAME}-dmg"
APP_BUNDLE_PATH="dist/${APP_NAME}.app"

echo
echo "=== Etlzone - Build macOS app ==="
echo "Working directory: $(pwd)"
echo

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: This build script must be run on macOS."
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: Python interpreter not found: $PYTHON_BIN"
  echo "Set PYTHON_BIN to the Python that has PyInstaller and app dependencies installed."
  exit 1
fi

if ! "$PYTHON_BIN" -c "import PyInstaller" >/dev/null 2>&1; then
  echo "ERROR: PyInstaller is not installed in $PYTHON_BIN"
  echo
  echo "Install it with:"
  echo "  $PYTHON_BIN -m pip install pyinstaller"
  exit 1
fi

if ! "$PYTHON_BIN" -c "import PySide6, dateutil, tzdata" >/dev/null 2>&1; then
  echo "ERROR: App dependencies are missing in $PYTHON_BIN"
  echo
  echo "Install them with:"
  echo "  $PYTHON_BIN -m pip install -r requirements.txt"
  exit 1
fi

if [[ ! -f "$SPEC_FILE" ]]; then
  echo "ERROR: Spec file not found: $SPEC_FILE"
  exit 1
fi

echo "Using Python: $("$PYTHON_BIN" -c 'import sys; print(sys.executable)')"
echo
echo "Building .app bundle with PyInstaller..."
"$PYTHON_BIN" -m PyInstaller --clean "$SPEC_FILE"

if [[ ! -d "$APP_BUNDLE_PATH" ]]; then
  echo
  echo "ERROR: PyInstaller did not produce $APP_BUNDLE_PATH"
  exit 1
fi

echo
echo "Preparing DMG staging folder..."
rm -rf "$DMG_STAGING_DIR"
mkdir -p "$DMG_STAGING_DIR"
cp -R "$APP_BUNDLE_PATH" "$DMG_STAGING_DIR/"
ln -s /Applications "$DMG_STAGING_DIR/Applications"

echo
echo "Creating DMG..."
rm -f "dist/$DMG_NAME"
hdiutil create \
  -volname "Etlzone" \
  -srcfolder "$DMG_STAGING_DIR" \
  -ov \
  -format UDZO \
  "dist/$DMG_NAME"

rm -rf "$DMG_STAGING_DIR"

echo
echo "OK - macOS build created here:"
echo "  $(pwd)/$APP_BUNDLE_PATH"
echo "  $(pwd)/dist/$DMG_NAME"
echo
echo "If macOS blocks the app on another machine, you will need to codesign and notarize it."
