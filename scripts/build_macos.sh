#!/bin/bash
# Build a macOS .app bundle and optional .dmg image.
#
# Usage:
#   ./scripts/build_macos.sh [version]
#
# Optional environment:
#   CODESIGN_IDENTITY      Developer ID Application identity.
#   NOTARIZE=1             Submit the app for notarization.
#   APPLE_ID               Apple ID used by notarytool.
#   APPLE_APP_PASSWORD     App-specific password used by notarytool.
#   APPLE_TEAM_ID          Apple developer team ID.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/package_common.sh"

[[ "$(uname)" == "Darwin" ]] || die "this script must run on macOS"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

ARCH="$(uname -m)"
case "$ARCH" in
    arm64|x86_64)
        ARCH_LABEL="$ARCH"
        ;;
    *)
        die "unsupported macOS architecture: $ARCH"
        ;;
esac

VERSION="$(resolve_project_version "$PROJECT_ROOT" "${1:-}")"
if [[ -z "${VERSION:-}" ]]; then
    die "unable to determine version; pass one explicitly: $0 <version>"
fi

echo "LaTeXSnipper macOS package build"
echo "Version: $VERSION"
echo "Architecture: $ARCH_LABEL"

DIST_DIR="$PROJECT_ROOT/dist"
APP_NAME="LaTeXSnipper"
APP_BUNDLE="${APP_NAME}.app"
DMG_PATH="$DIST_DIR/LaTeXSnipper_${VERSION}_${ARCH_LABEL}.dmg"
APP_ZIP_PATH="$DIST_DIR/LaTeXSnipper_${VERSION}_${ARCH_LABEL}.app.zip"
BUILD_WORK_DIR="$PROJECT_ROOT/build/pyinstaller_macos"
SPEC_FILE="$PROJECT_ROOT/LaTeXSnipper-macos.spec"
ICNS_PATH="$PROJECT_ROOT/src/assets/icon.icns"

log_step "0/6" "Checking build tools"
[[ -f "$SPEC_FILE" ]] || die "missing spec file: $SPEC_FILE"
if [[ ! -f "$ICNS_PATH" ]]; then
    echo "warning: icon.icns was not found; the app will use the default icon"
fi

log_step "1/6" "Preparing isolated Python runtime"
BUILD_PYTHON="$(prepare_python_runtime "$PROJECT_ROOT")"
install_python_requirements \
    "$BUILD_PYTHON" \
    "$PROJECT_ROOT/requirements-macos.txt" \
    "$PROJECT_ROOT/requirements-build.txt"

log_step "2/6" "Cleaning previous outputs"
rm -rf "$BUILD_WORK_DIR" "$DIST_DIR/$APP_NAME" "$DIST_DIR/$APP_BUNDLE" "$DMG_PATH" "$APP_ZIP_PATH"

log_step "3/6" "Running PyInstaller"
cd "$PROJECT_ROOT"
"$BUILD_PYTHON" -m PyInstaller \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_WORK_DIR" \
    --noconfirm \
    "$SPEC_FILE"

log_step "4/6" "Validating app bundle"
if [[ -d "$DIST_DIR/$APP_BUNDLE" ]]; then
    APP_PATH="$DIST_DIR/$APP_BUNDLE"
elif [[ -d "$DIST_DIR/$APP_NAME/$APP_BUNDLE" ]]; then
    APP_PATH="$DIST_DIR/$APP_NAME/$APP_BUNDLE"
else
    APP_PATH="$(find "$DIST_DIR" -maxdepth 3 -name "*.app" -type d 2>/dev/null | head -1)"
fi

[[ -n "${APP_PATH:-}" && -d "$APP_PATH" ]] || die "generated .app bundle was not found"
[[ -f "$APP_PATH/Contents/MacOS/$APP_NAME" ]] || die "missing app executable: $APP_PATH/Contents/MacOS/$APP_NAME"

log_step "5/6" "Signing app bundle"
SIGN_IDENTITY="${CODESIGN_IDENTITY:-}"
if [[ -n "$SIGN_IDENTITY" ]]; then
    find "$APP_PATH" -name "*.dylib" -type f -print0 | xargs -0 -I{} codesign --force --options runtime --sign "$SIGN_IDENTITY" "{}" || true
    find "$APP_PATH" -name "*.framework" -type d -print0 | xargs -0 -I{} codesign --force --options runtime --sign "$SIGN_IDENTITY" "{}" || true
    codesign --force --options runtime --deep --sign "$SIGN_IDENTITY" "$APP_PATH"
    codesign --verify --verbose "$APP_PATH"
else
    echo "No CODESIGN_IDENTITY set; building unsigned app."
fi

if [[ "${NOTARIZE:-0}" == "1" ]]; then
    [[ -n "${APPLE_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]] || die "notarization requires APPLE_ID, APPLE_APP_PASSWORD, and APPLE_TEAM_ID"
    NOTARIZE_ZIP="$DIST_DIR/${APP_NAME}_notarize.zip"
    ditto -c -k --keepParent "$APP_PATH" "$NOTARIZE_ZIP"
    xcrun notarytool submit "$NOTARIZE_ZIP" \
        --apple-id "$APPLE_ID" \
        --password "$APPLE_APP_PASSWORD" \
        --team-id "$APPLE_TEAM_ID" \
        --wait
    rm -f "$NOTARIZE_ZIP"
    xcrun stapler staple "$APP_PATH"
fi

log_step "6/6" "Packaging app artifacts"
ditto -c -k --keepParent "$APP_PATH" "$APP_ZIP_PATH"

if command -v create-dmg >/dev/null 2>&1; then
    CREATE_DMG_ARGS=(
        --volname "LaTeXSnipper ${VERSION}"
        --window-pos 200 120
        --window-size 600 400
        --icon-size 100
        --icon "$APP_NAME.app" 150 190
        --hide-extension "$APP_NAME.app"
        --app-drop-link 450 185
        "$DMG_PATH"
        "$(dirname "$APP_PATH")"
    )
    if [[ -f "$ICNS_PATH" ]]; then
        CREATE_DMG_ARGS=(--volicon "$ICNS_PATH" "${CREATE_DMG_ARGS[@]}")
    fi
    create-dmg "${CREATE_DMG_ARGS[@]}"
fi

ARTIFACTS=("$APP_ZIP_PATH")
[[ -f "$DMG_PATH" ]] && ARTIFACTS+=("$DMG_PATH")
write_sha256_file "$DIST_DIR/SHA256SUMS-macos.txt" "${ARTIFACTS[@]}"

echo ""
echo "macOS artifacts:"
printf '  %s\n' "${ARTIFACTS[@]}"
