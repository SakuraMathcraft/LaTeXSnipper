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
    local runtime_dir="$project_root/src/deps/python311"
    local runtime_python="$runtime_dir/bin/python3"

    mkdir -p "$(dirname "$runtime_dir")"

    local rebuild=false
    if [[ ! -x "$runtime_python" ]]; then
        rebuild=true
    elif [[ -L "$runtime_python" ]]; then
        # Symlinks point to the system Python and are not self-contained
        rebuild=true
    elif head -c 2 "$runtime_python" 2>/dev/null | grep -q '^#!'; then
        # A previous build may have left a shell wrapper script behind
        rebuild=true
    elif ! "$runtime_python" -c "print('ok')" >/dev/null 2>&1; then
        rebuild=true
    fi

    if [[ "$rebuild" == "true" ]]; then
        rm -rf "$runtime_dir"
        python3 -m venv --copies "$runtime_dir" || die "failed to create isolated runtime at $runtime_dir"

        # Standard library discovery is handled by pyvenv.cfg so the
        # copied binary resolves stdlib from the system Python even
        # though sys.prefix is hardcoded to the build-machine prefix.
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
    cat > "$package_root/usr/share/applications/latexsnipper.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=LaTeXSnipper
Comment=Capture, recognize, edit, and compute mathematical content
Exec=latexsnipper
Terminal=false
Categories=Utility;Education;Science;
StartupNotify=true
EOF
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
