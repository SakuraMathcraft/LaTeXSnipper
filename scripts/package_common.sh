#!/bin/bash

die() {
    echo "ERROR: $*" >&2
    exit 1
}

log_step() {
    echo ""
    echo "[$1] $2"
}

resolve_project_version() {
    local project_root="$1"
    local explicit_version="${2:-}"

    if [[ -n "$explicit_version" ]]; then
        echo "$explicit_version"
        return
    fi

    python3 - "$project_root" <<'PY'
import pathlib
import re
import sys
import tomllib

root = pathlib.Path(sys.argv[1])
version_info = root / "version_info.txt"
if version_info.exists():
    match = re.search(
        r"filevers\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)",
        version_info.read_text(encoding="utf-8", errors="ignore"),
    )
    if match:
        print(".".join(match.groups()))
        raise SystemExit

pyproject = root / "pyproject.toml"
if pyproject.exists():
    version = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {}).get("version", "")
    if version:
        print(version)
PY
}

prepare_python_runtime() {
    local project_root="$1"
    local platform arch runtime_dir
    platform="$(uname -s | tr '[:upper:]' '[:lower:]')"
    arch="$(uname -m | tr '[:upper:]' '[:lower:]')"
    runtime_dir="$project_root/tools/deps/python311-$platform-$arch"
    local runtime_python="$runtime_dir/bin/python3"

    mkdir -p "$(dirname "$runtime_dir")"

    local rebuild=false
    if [[ ! -x "$runtime_python" ]]; then
        rebuild=true
    elif [[ -L "$runtime_python" ]]; then
        rebuild=true
    elif ! "$runtime_python" -c "print('ok')" >/dev/null 2>&1; then
        rebuild=true
    fi

    if [[ "$rebuild" == "true" ]]; then
        rm -rf "$runtime_dir"
        python3 -m venv --copies "$runtime_dir" || die "failed to create isolated runtime at $runtime_dir"
    fi

    "$runtime_python" -m ensurepip --upgrade >/dev/null 2>&1 || true
    "$runtime_python" -m pip install --upgrade pip wheel setuptools >&2
    echo "$runtime_python"
}

install_python_requirements() {
    local runtime_python="$1"
    shift

    for req in "$@"; do
        if [[ -f "$req" ]]; then
            "$runtime_python" -m pip install -r "$req"
        fi
    done

    if ! "$runtime_python" -c "import PyInstaller" >/dev/null 2>&1; then
        "$runtime_python" -m pip install "pyinstaller>=6"
    fi
}

find_mathcraft_models_root() {
    local project_root="$1"
    local candidates=(
        "${MATHCRAFT_MODELS_ROOT:-}"
        "$project_root/MathCraft/models"
        "${APPDATA:-}/MathCraft/models"
        "${HOME:-}/.MathCraft/models"
        "${HOME:-}/.mathcraft/models"
    )

    for candidate in "${candidates[@]}"; do
        if [[ -n "$candidate" && -d "$candidate" ]] && find "$candidate" -type f -print -quit | grep -q .; then
            echo "$candidate"
            return
        fi
    done

    return 1
}

copy_debian_template() {
    local template_dir="$1"
    local package_root="$2"

    rm -rf "$package_root"
    mkdir -p "$package_root"
    cp -a "$template_dir"/. "$package_root"/
    mkdir -p "$package_root/DEBIAN"
}

write_debian_launcher() {
    local package_root="$1"
    local executable_path="$2"

    mkdir -p "$package_root/usr/bin"
    cat > "$package_root/usr/bin/latexsnipper" <<EOF
#!/bin/sh
exec "$executable_path" "\$@"
EOF
    chmod 755 "$package_root/usr/bin/latexsnipper"
}

write_debian_desktop_file() {
    local package_root="$1"

    mkdir -p "$package_root/usr/share/applications"
    python3 - "$package_root/usr/share/applications/latexsnipper.desktop" <<'PY'
from pathlib import Path
import sys

desktop_file = Path(sys.argv[1])
desktop_file.write_text(
    "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Name=LaTeXSnipper",
            "Comment=\u622a\u56fe\u3001\u8bc6\u522b\u3001\u7f16\u8f91\u548c\u8ba1\u7b97\u6570\u5b66\u5185\u5bb9",
            "Exec=latexsnipper",
            "Icon=latexsnipper",
            "Terminal=false",
            "Categories=Utility;Education;Science;",
            "StartupNotify=true",
        ]
    )
    + "\n",
    encoding="utf-8",
)
PY
}

install_debian_icons() {
    local package_root="$1"
    local icon_source="$2"
    local python_cmd="$3"

    [[ -f "$icon_source" ]] || die "application icon not found: $icon_source"

    "$python_cmd" - "$icon_source" "$package_root/usr/share/icons/hicolor" <<'PY'
from pathlib import Path
import sys

from PIL import Image, ImageOps

source = Path(sys.argv[1])
target_root = Path(sys.argv[2])
image = Image.open(source)
ico = getattr(image, "ico", None)
if ico is not None and hasattr(ico, "sizes"):
    sizes = sorted(ico.sizes(), key=lambda item: item[0] * item[1])
    if sizes:
        image = ico.getimage(sizes[-1])
image = image.convert("RGBA")

for size in (16, 24, 32, 48, 64, 128, 256):
    target_dir = target_root / f"{size}x{size}" / "apps"
    target_dir.mkdir(parents=True, exist_ok=True)
    resized = ImageOps.contain(image, (size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    canvas.save(target_dir / "latexsnipper.png")
PY
}

prepare_macos_icns() {
    local project_root="$1"
    local python_cmd="$2"
    local existing_icns="$project_root/src/assets/icon.icns"
    local icon_source="$project_root/src/assets/icon.ico"
    local generated_dir="$project_root/build/generated"
    local iconset_dir="$generated_dir/latexsnipper.iconset"
    local generated_icns="$generated_dir/latexsnipper.icns"

    if [[ -f "$existing_icns" ]]; then
        echo "$existing_icns"
        return
    fi

    if [[ ! -f "$icon_source" ]]; then
        echo "warning: application icon was not found: $icon_source" >&2
        echo ""
        return
    fi

    if ! command -v iconutil >/dev/null 2>&1; then
        echo "warning: iconutil was not found; macOS app will use the default icon" >&2
        echo ""
        return
    fi

    rm -rf "$iconset_dir"
    mkdir -p "$iconset_dir"

    "$python_cmd" - "$icon_source" "$iconset_dir" <<'PY'
from pathlib import Path
import sys

from PIL import Image, ImageOps

source = Path(sys.argv[1])
iconset = Path(sys.argv[2])
image = Image.open(source)
ico = getattr(image, "ico", None)
if ico is not None and hasattr(ico, "sizes"):
    sizes = sorted(ico.sizes(), key=lambda item: item[0] * item[1])
    if sizes:
        image = ico.getimage(sizes[-1])
image = image.convert("RGBA")

outputs = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}
for name, size in outputs.items():
    resized = ImageOps.contain(image, (size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    canvas.save(iconset / name)
PY

    mkdir -p "$generated_dir"
    iconutil -c icns "$iconset_dir" -o "$generated_icns"
    echo "$generated_icns"
}

update_debian_control() {
    local control_file="$1"
    local package_name="$2"
    local version="$3"
    local installed_size="$4"
    local description="$5"

    python3 - "$control_file" "$package_name" "$version" "$installed_size" "$description" <<'PY'
import pathlib
import sys

control_path = pathlib.Path(sys.argv[1])
package_name, version, installed_size, description = sys.argv[2:6]
lines = control_path.read_text(encoding="utf-8").splitlines()
out = []
for line in lines:
    if line.startswith("Package:"):
        out.append(f"Package: {package_name}")
    elif line.startswith("Version:"):
        out.append(f"Version: {version}")
    elif line.startswith("Installed-Size:"):
        out.append(f"Installed-Size: {installed_size}")
    elif line.startswith("Description:"):
        out.append(f"Description: {description}")
    else:
        out.append(line)
control_path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

write_sha256_file() {
    local output_file="$1"
    shift

    : > "$output_file"
    local artifact hash
    for artifact in "$@"; do
        if command -v sha256sum >/dev/null 2>&1; then
            hash="$(sha256sum "$artifact" | awk '{print $1}')"
        else
            hash="$(shasum -a 256 "$artifact" | awk '{print $1}')"
        fi
        printf '%s  %s\n' "$hash" "$(basename "$artifact")" >> "$output_file"
    done
}
