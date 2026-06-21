#!/bin/sh
set -eu

APP_NAME="LaTeXSnipper"
CONFIG_FILENAME="LaTeXSnipper_config.json"

usage() {
    cat <<'EOF'
Usage: latexsnipper-clean-user-data.sh [--app-data] [--deps] [--models] [--all] [--yes]

Removes LaTeXSnipper user-owned data for the current user only.
By default the script asks interactively. Package uninstall does not run this
script automatically because Linux/macOS uninstall commands may run as root or
from a different user account.

Options:
  --app-data  Remove settings, history, logs, dependency state, and temp files.
  --deps      Remove app-managed dependency environments and Pandoc/translation tools.
  --models    Remove MathCraft model weights from the default platform cache.
  --all       Remove app data, dependency environments, and model weights.
  --yes       Do not ask for confirmation.
EOF
}

remove_app_data=false
remove_deps=false
remove_models=false
assume_yes=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --app-data)
            remove_app_data=true
            ;;
        --deps)
            remove_deps=true
            ;;
        --models)
            remove_models=true
            ;;
        --all)
            remove_app_data=true
            remove_deps=true
            remove_models=true
            ;;
        --yes|-y)
            assume_yes=true
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

is_macos=false
if [ "$(uname -s)" = "Darwin" ]; then
    is_macos=true
fi

xdg_data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
tmp_root="${TMPDIR:-/tmp}"

if [ "$is_macos" = "true" ]; then
    app_state="$HOME/Library/Application Support/$APP_NAME"
    log_dir="$HOME/Library/Logs/$APP_NAME"
    model_dir="$HOME/Library/Application Support/$APP_NAME/MathCraft/models"
else
    app_state="$HOME/.latexsnipper"
    log_dir="$HOME/.latexsnipper/logs"
    model_dir="$xdg_data_home/$APP_NAME/MathCraft/models"
fi
temp_dir="$tmp_root/$APP_NAME"
config_file="$app_state/$CONFIG_FILENAME"

ask_yes_no() {
    prompt="$1"
    if [ "$assume_yes" = "true" ]; then
        return 0
    fi
    printf '%s [y/N] ' "$prompt"
    if ! IFS= read -r answer; then
        answer=""
    fi
    case "$answer" in
        y|Y|yes|YES|Yes)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

remove_path() {
    path="$1"
    label="$2"
    if [ -e "$path" ]; then
        rm -rf "$path"
        printf 'Removed %s: %s\n' "$label" "$path"
    else
        printf 'Skipped %s; not found: %s\n' "$label" "$path"
    fi
}

collect_dependency_roots() {
    printf '%s\n' "$app_state/deps"
    if command -v python3 >/dev/null 2>&1 && [ -f "$config_file" ]; then
        python3 - "$config_file" <<'PY'
import json
import sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
try:
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
except Exception:
    data = {}
if isinstance(data, dict):
    raw_values = [str(data.get("install_base_dir") or "").strip()]
    history = data.get("install_base_dir_cleanup_roots")
    if isinstance(history, str):
        raw_values.extend(item.strip() for item in history.split("|"))
    elif isinstance(history, list):
        raw_values.extend(str(item).strip() for item in history)
    for raw in raw_values:
        if raw:
            print(str(Path(raw).expanduser()))
PY
    fi
}

is_dangerous_root() {
    path="$1"
    [ -z "$path" ] && return 0
    [ "$path" = "/" ] && return 0
    [ "$path" = "$HOME" ] && return 0
    [ "$path" = "$app_state" ] && return 0
    return 1
}

is_python_environment_root() {
    root="$1"
    [ -f "$root/pyvenv.cfg" ] && return 0
    [ -f "$root/python.exe" ] && return 0
    [ -f "$root/pythonw.exe" ] && return 0
    [ -f "$root/Scripts/python.exe" ] && return 0
    [ -f "$root/bin/python" ] && return 0
    return 1
}

remove_dependency_root_children() {
    root="$1"
    if is_dangerous_root "$root"; then
        printf 'Skipped dependency root with unsafe scope: %s\n' "$root"
        return
    fi

    if is_python_environment_root "$root"; then
        remove_path "$root" "dependency environment root"
        return
    fi

    remove_path "$root/.deps_state.json" "dependency state"
    remove_path "$root/python311" "dependency Python"
    remove_path "$root/Python311" "dependency Python"
    remove_path "$root/python_full" "dependency Python"
    remove_path "$root/venv" "dependency venv"
    remove_path "$root/.venv" "dependency venv"
    remove_path "$root/pandoc" "Pandoc dependency"
    remove_path "$root/translation_env" "translation environment"
    rmdir "$root" 2>/dev/null || true
}

dependency_roots="$(collect_dependency_roots | awk 'NF && !seen[$0]++')"

if [ "$remove_app_data" = "false" ] && [ "$remove_deps" = "false" ] && [ "$remove_models" = "false" ]; then
    if ask_yes_no "Remove LaTeXSnipper settings, history, logs, dependency state, and temp files?"; then
        remove_app_data=true
    fi
    if ask_yes_no "Remove app-managed dependency environments, Pandoc, and translation tools?"; then
        remove_deps=true
    fi
    if ask_yes_no "Remove MathCraft model weights from the default cache?"; then
        remove_models=true
    fi
fi

if [ "$remove_deps" = "true" ]; then
    printf '%s\n' "$dependency_roots" | while IFS= read -r root; do
        [ -n "$root" ] && remove_dependency_root_children "$root"
    done
fi

if [ "$remove_app_data" = "true" ]; then
    remove_path "$app_state" "app state"
    if [ "$is_macos" = "true" ]; then
        remove_path "$log_dir" "logs"
    fi
    remove_path "$temp_dir" "temporary files"
fi

if [ "$remove_models" = "true" ]; then
    remove_path "$model_dir" "MathCraft model weights"
fi

cat <<EOF

Done.
Custom MATHCRAFT_HOME directories are not removed automatically. Dependency
tools created by LaTeXSnipper are grouped under the configured dependency root.
EOF
