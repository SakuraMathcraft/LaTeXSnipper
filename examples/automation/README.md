# Automation workflow examples

These examples are complete client workflows rather than single-request snippets. They accept encoded clipboard images as well as copied file paths, submit authenticated jobs, handle `200`/`202`, poll to a terminal state, preserve batch order, surface API error codes, and copy successful text back to the desktop clipboard where appropriate.

Enable **自动化接口** in LaTeXSnipper before using a local workflow. Local clients discover the rotating session URL and token from `automation-api.json`; do not copy that token into a script.

## Python client

`local_client.py` uses only the Python standard library.

```bash
python local_client.py formula.png --mode formula
python local_client.py page-1.png page-2.webp --mode mixed --output json
python local_client.py --stdin --filename capture.png < capture.png
```

Linux clipboard image or copied path:

```bash
python local_client.py --clipboard --mode formula --copy
```

Install `wl-clipboard` on Wayland or `xclip` on X11. Clipboard image bytes are uploaded directly; no filename is required.

Remote use:

```bash
export BASE_URL=http://100.x.y.z:28765
export LATEXSNIPPER_REMOTE_KEY='generated-remote-key'
python local_client.py image.png --mode mixed
```

The address must be protected by the configured HTTPS listener or an encrypted tunnel. The client also accepts `--base-url` and `--token` explicitly.

Useful options:

- `--backend mathcraft|external`
- `--mode formula|text|mixed`
- `--timeout 120`
- `--output text|json`
- `--copy`
- `--allow-partial` for batches where successful items should be returned even if another item fails

## AutoHotkey v2 on Windows

Keep `autohotkey_v2.ahk` and `clipboard_image.ps1` in the same directory, then run the AHK script. `Ctrl+Alt+L` recognizes either:

- image data placed on the clipboard by a screenshot tool; or
- an existing image-file path copied as text.

The PowerShell helper uses the Windows clipboard API in STA mode, writes a temporary PNG, and the AHK script always removes that file after success or failure. The workflow has no third-party Python requirement.

Change the backend, mode, timeout, or hotkey near the top of `RecognizeClipboard` if desired.

## AutoKey on Linux

Copy `autokey.py` into an AutoKey script and set `CLIENT` to the absolute path of `local_client.py`. Assign the desired AutoKey hotkey. The workflow accepts clipboard image data on Wayland/X11 and copied file paths, waits for completion, reports failures, and copies recognized text to the clipboard.

`PYTHON`, `BACKEND`, and `MODE` are explicit configuration constants at the top of the script.

## Hammerspoon on macOS

Copy `hammerspoon.lua` into `~/.hammerspoon/init.lua` or require it from there. Set the absolute `python` and `client` paths, then reload Hammerspoon. `Ctrl+Alt+L` reads a copied file URL, text path, or actual clipboard image. Image data is written to a temporary PNG and deleted in the asynchronous completion callback.

## Remote curl client

`remote_curl.sh` requires Bash, curl, and jq. It supports one to sixteen image paths, polling, partial-batch policy, structured errors, and text or JSON output.

```bash
BASE_URL=http://100.x.y.z:28765 \
LATEXSNIPPER_REMOTE_KEY='generated-remote-key' \
MODE=mixed \
bash remote_curl.sh page-1.png page-2.png
```

Optional environment variables are `BACKEND`, `MODE`, `TIMEOUT`, `PREFER_WAIT`, `POLL_INTERVAL`, `OUTPUT=json`, and `ALLOW_PARTIAL=1`.

## Input and failure behavior

The server recognizes PNG, JPEG, BMP, GIF, TIFF, and WebP encoded content; `.jpg`/`.jpeg` and `.tif`/`.tiff` account for the eight accepted extensions. Clients send the actual bytes and the server validates the encoding rather than trusting the extension or MIME type.

The examples distinguish connection/discovery failures, invalid credentials, unsupported input, queue saturation, recognition timeout, terminal job failure, and per-image batch failure. Tokens, uploaded data, and local paths are never logged by the clients.
