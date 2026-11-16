#!/bin/sh
set -eu
app_data=false
models=false
confirm=true
for option in "$@"; do
    case "$option" in
        --app-data) app_data=true ;;
        --models) models=true ;;
        --all) app_data=true; models=true ;;
        --yes) confirm=false ;;
        --help) printf 'Usage: %s [--app-data] [--models] [--all] [--yes]\n' "$0"; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$option" >&2; exit 2 ;;
    esac
done
if [ "$app_data" = false ] && [ "$models" = false ]; then
    printf 'Choose --app-data, --models or --all. Shared models affect other MathCraft clients.\n' >&2
    exit 2
fi
if [ "$confirm" = true ]; then
    printf 'Remove the selected current-user data? [y/N] '
    read -r answer
    [ "$answer" = y ] || [ "$answer" = Y ] || exit 0
fi
if [ "$(uname -s)" = Darwin ]; then
    state="$HOME/Library/Application Support/LaTeXSnipper"
    cache="$HOME/Library/Caches/LaTeXSnipper"
    logs="$HOME/Library/Logs/LaTeXSnipper"
    model_root="$state/MathCraft/models"
else
    state="$HOME/.latexsnipper"
    cache="$state/cache"
    logs="$state/logs"
    model_root="${XDG_DATA_HOME:-$HOME/.local/share}/LaTeXSnipper/MathCraft/models"
fi
if [ "$app_data" = true ]; then
    # macOS keeps the shared model cache below its application support root.
    # An app-data-only cleanup preserves that cache explicitly.
    if [ -L "$state" ]; then
        rm -f -- "$state"
    elif [ -d "$state" ]; then
        for path in "$state"/* "$state"/.[!.]* "$state"/..?*; do
            [ -e "$path" ] || [ -L "$path" ] || continue
            [ "${path##*/}" != MathCraft ] || [ "$models" = true ] || continue
            rm -rf -- "$path"
        done
    fi
    rm -rf -- "$cache" "$logs" "${TMPDIR:-/tmp}/LaTeXSnipper"
fi
if [ "$models" = true ]; then
    rm -rf -- "$model_root"
fi
printf 'Selected data removed. Custom library cache directories are preserved.\n'
