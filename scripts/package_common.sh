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

        # Copy the system stdlib into the isolated runtime so the bundled
        # Python is self-contained after PyInstaller packaging.  Without
        # this, venv --copies only copies the binary; the stdlib is still
        # resolved via pyvenv.cfg which points to the build machine and
        # does not exist on target machines.  This also satisfies Debian
        # reproducible-build requirements.
        local system_python
        system_python="$(python3 -c 'import sys; print(sys.prefix)')" || true
        if [[ -n "$system_python" && -d "$system_python/lib" ]]; then
            local dest_lib="$runtime_dir/lib"
            mkdir -p "$dest_lib"
            for d in "$system_python/lib"/python3.*; do
                if [[ -d "$d" ]]; then
                    local ver_dir="$(basename "$d")"
                    local dest_ver="$dest_lib/$ver_dir"
                    # venv --copies pre-creates lib/pythonX.Y/ with an empty
                    # site-packages/.  We must replace it with the full stdlib
                    # so the copied binary can find encodings and other
                    # built-in modules on machines where the original prefix
                    # does not exist.
                    rm -rf "$dest_ver"
                    echo "[RUNTIME] copying stdlib: $d -> $dest_ver"
                    cp -a "$d" "$dest_ver"
                    # Remove system site-packages so they don't conflict
                    # with the isolated pip-installed packages.
                    rm -rf "$dest_ver/site-packages" 2>/dev/null || true
                fi
            done
        fi

        # Keep pyvenv.cfg so the copied Python binary can locate the
        # locally-copied stdlib during the build.  Without it, the binary
        # falls back to its compiled-in prefix (the build-machine path)
        # and cannot find encodings/stdlib.
        #
        # The venv --copies created pyvenv.cfg with a "home" key pointing
        # to the build machine's Python bin directory.  Rewrite it to
        # point to the venv's own bin directory so stdlib is resolved
        # from the locally-copied lib/pythonX.Y tree.
        local pyvenv_cfg="$runtime_dir/pyvenv.cfg"
        if [[ -f "$pyvenv_cfg" ]]; then
            local venv_bin_dir="$runtime_dir/bin"
            python3 - "$pyvenv_cfg" "$venv_bin_dir" <<'PY'
import pathlib, sys
cfg = pathlib.Path(sys.argv[1])
new_home = sys.argv[2]
lines = cfg.read_text(encoding="utf-8").splitlines()
out = []
for line in lines:
    if line.startswith("home"):
        out.append(f"home = {new_home}")
    elif line.startswith("executable") or line.startswith("command"):
        continue
    else:
        out.append(line)
cfg.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
            echo "[RUNTIME] updated pyvenv.cfg home=$venv_bin_dir"
        fi
    fi

    # Verify the runtime can import core stdlib before using pip.
    if ! "$runtime_python" -c "import encodings, sys; print(sys.version)" >/dev/null 2>&1; then
        die "isolated Python runtime is broken (cannot import encodings); check venv creation"
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
