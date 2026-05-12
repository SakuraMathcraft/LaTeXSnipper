#!/bin/bash
# Build a Debian/Ubuntu .deb package.
#
# Usage:
#   ./scripts/build_deb.sh [version]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/package_common.sh"

VERSION="$(resolve_project_version "$PROJECT_ROOT" "${1:-}")"
if [[ -z "${VERSION:-}" ]]; then
    die "unable to determine version; pass one explicitly: $0 <version>"
fi

echo "LaTeXSnipper Linux package build"
echo "Version: $VERSION"

PACKAGING_TEMPLATE="$PROJECT_ROOT/packaging/debian"
PACKAGE_ROOT="$PROJECT_ROOT/build/package/debian-latexsnipper"
DEB_OUTPUT_DIR="$PROJECT_ROOT/dist"
DEB_PATH="$DEB_OUTPUT_DIR/latexsnipper_${VERSION}_amd64.deb"
DIST_DIR="$PROJECT_ROOT/dist/LaTeXSnipper"
SPEC_FILE="$PROJECT_ROOT/LaTeXSnipper-linux.spec"

log_step "0/5" "Checking build tools"
command -v dpkg-deb >/dev/null 2>&1 || die "dpkg-deb is required; install dpkg-dev on the build host"
command -v python3 >/dev/null 2>&1 || die "python3 is required"
[[ -f "$SPEC_FILE" ]] || die "missing spec file: $SPEC_FILE"

log_step "1/5" "Preparing isolated Python runtime"
BUILD_PYTHON="$(prepare_python_runtime "$PROJECT_ROOT")"
install_python_requirements \
    "$BUILD_PYTHON" \
    "$PROJECT_ROOT/requirements-linux.txt" \
    "$PROJECT_ROOT/requirements-build.txt"

log_step "2/5" "Running PyInstaller"
rm -rf "$PROJECT_ROOT/build/pyinstaller_linux" "$DIST_DIR"
cd "$PROJECT_ROOT"
"$BUILD_PYTHON" -m PyInstaller \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build/pyinstaller_linux" \
    --noconfirm \
    "$SPEC_FILE"

[[ -d "$DIST_DIR" ]] || die "PyInstaller output was not created: $DIST_DIR"

log_step "3/5" "Preparing Debian package tree"
copy_debian_template "$PACKAGING_TEMPLATE" "$PACKAGE_ROOT"
DEB_LIB_DIR="$PACKAGE_ROOT/usr/lib/latexsnipper"
mkdir -p "$DEB_LIB_DIR"
cp -a "$DIST_DIR"/. "$DEB_LIB_DIR"/

MAIN_BIN="$DEB_LIB_DIR/LaTeXSnipper"
[[ -f "$MAIN_BIN" ]] || die "missing packaged executable: $MAIN_BIN"
chmod 755 "$MAIN_BIN"
write_debian_launcher "$PACKAGE_ROOT" "/usr/lib/latexsnipper/LaTeXSnipper"
write_debian_desktop_file "$PACKAGE_ROOT"

find "$DEB_LIB_DIR" -type f -executable -exec chmod 755 {} \; 2>/dev/null || true
find "$DEB_LIB_DIR" -type f -name "*.so*" -exec chmod 755 {} \; 2>/dev/null || true
if [[ -f "$DEB_LIB_DIR/_internal/PyQt6/Qt6/libexec/QtWebEngineProcess" ]]; then
    chmod 755 "$DEB_LIB_DIR/_internal/PyQt6/Qt6/libexec/QtWebEngineProcess"
fi
chmod 755 "$PACKAGE_ROOT/DEBIAN/postinst" "$PACKAGE_ROOT/DEBIAN/prerm"
[[ -f "$PACKAGE_ROOT/DEBIAN/postrm" ]] && chmod 755 "$PACKAGE_ROOT/DEBIAN/postrm"
find "$PACKAGE_ROOT/usr/share" -type f -exec chmod 644 {} \; 2>/dev/null || true

# Remove pyvenv.cfg from the bundled runtime for reproducible builds.
# At runtime, bundled_python_env() sets PYTHONHOME dynamically so
# pyvenv.cfg is not needed.  Removing it avoids leaking
# build-machine absolute paths into the .deb.
find "$DEB_LIB_DIR" -name "pyvenv.cfg" -delete 2>/dev/null || true

# Normalize file timestamps for reproducible builds.
# Debian policy section 4.9: packages should be reproducible.
# Use SOURCE_DATE_EPOCH if set, otherwise use a fixed epoch.
: "${SOURCE_DATE_EPOCH:=1609459200}"
export SOURCE_DATE_EPOCH
find "$PACKAGE_ROOT" -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} + 2>/dev/null || true

log_step "4/5" "Updating Debian metadata"
INSTALLED_SIZE="$(du -sk "$PACKAGE_ROOT/usr" | cut -f1)"
[[ -n "$INSTALLED_SIZE" && "$INSTALLED_SIZE" -gt 0 ]] || INSTALLED_SIZE=1
update_debian_control \
    "$PACKAGE_ROOT/DEBIAN/control" \
    "latexsnipper" \
    "$VERSION" \
    "$INSTALLED_SIZE" \
    "Desktop math workspace for capture, recognize, edit and compute"

log_step "5/5" "Building .deb"
mkdir -p "$DEB_OUTPUT_DIR"
dpkg-deb --root-owner-group --build "$PACKAGE_ROOT" "$DEB_PATH"
write_sha256_file "$DEB_OUTPUT_DIR/SHA256SUMS-linux.txt" "$DEB_PATH"

echo ""
echo "Package created: $DEB_PATH"
dpkg-deb --info "$DEB_PATH"
