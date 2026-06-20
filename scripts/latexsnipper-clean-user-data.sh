#!/bin/sh
set -eu

APP_NAME="LaTeXSnipper"

usage() {
    cat <<'EOF'
Usage: latexsnipper-clean-user-data.sh [--app-data] [--models] [--all] [--yes]

Removes LaTeXSnipper user-owned data for the current user only.
By default the script asks interactively. Package uninstall does not run this
script automatically because Linux/macOS uninstall commands may run as root or
from a different user account.

Options:
  --app-data  Remove settings, history, logs, dependency state, and temp files.
  --models    Remove MathCraft model weights from the default platform cache.
  --all       Remove both app data and model weights.
  --yes       Do not ask for confirmation.
EOF
}

remove_app_data=false
remove_models=false
assume_yes=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --app-data)
            remove_app_data=true
            ;;
        --models)
            remove_models=true
            ;;
        --all)
            remove_app_data=true
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

if [ "$remove_app_data" = "false" ] && [ "$remove_models" = "false" ]; then
    if ask_yes_no "Remove LaTeXSnipper settings, history, logs, dependency state, and temp files?"; then
        remove_app_data=true
    fi
    if ask_yes_no "Remove MathCraft model weights from the default cache?"; then
        remove_models=true
    fi
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
Custom MATHCRAFT_HOME directories are not removed automatically. Delete them
manually if you explicitly pointed MathCraft at another location.
EOF
