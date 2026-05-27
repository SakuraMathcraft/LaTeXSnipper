#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/package_common.sh"

[[ "$(uname)" == "Darwin" ]] || die "this script must run on macOS"
command -v pkgbuild >/dev/null 2>&1 || die "pkgbuild is required"
command -v npm >/dev/null 2>&1 || die "npm is required"

VERSION="$(resolve_project_version "$PROJECT_ROOT" "${1:-}")"
ADDIN_ROOT="$PROJECT_ROOT/office_addin"
STAGE="$PROJECT_ROOT/build/office_addin/macos"
PAYLOAD="$STAGE/payload/Library/Application Support/LaTeXSnipper/OfficeAddinPayload"
SCRIPTS="$STAGE/scripts"
OUTPUT="$PROJECT_ROOT/dist/office-addin"
PKG="$OUTPUT/LaTeXSnipperOfficeAddin-${VERSION}.pkg"
PUBLIC_ORIGIN="https://localhost:8765"

log_step "1/4" "Building Office add-in site"
npm --prefix "$ADDIN_ROOT" run build

log_step "2/4" "Staging Office add-in payload"
rm -rf "$STAGE"
mkdir -p "$PAYLOAD/site" "$PAYLOAD/manifests" "$SCRIPTS" "$OUTPUT"
cp -R "$ADDIN_ROOT/dist/." "$PAYLOAD/site/"
cp "$ADDIN_ROOT/installer/macos/postinstall" "$SCRIPTS/postinstall"
chmod 755 "$SCRIPTS/postinstall"

python3 - "$ADDIN_ROOT" "$PAYLOAD/manifests" "$PUBLIC_ORIGIN" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
origin = sys.argv[3]
for name in ("manifest.word.xml", "manifest.powerpoint.xml"):
    content = (source / name).read_text(encoding="utf-8").replace("https://localhost:3000", origin)
    (target / name).write_text(content, encoding="utf-8")
PY

log_step "3/4" "Building macOS Office add-in package"
rm -f "$PKG"
pkgbuild \
    --root "$STAGE/payload" \
    --scripts "$SCRIPTS" \
    --identifier "com.mathcraft.latexsnipper.officeaddin" \
    --version "$VERSION" \
    "$PKG"

log_step "4/4" "Writing package checksum"
write_sha256_file "$OUTPUT/SHA256SUMS-office-addin-macos.txt" "$PKG"
echo "Office add-in macOS package: $PKG"
