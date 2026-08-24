# Automation API v1

LaTeXSnipper v3.0.0 exposes its resident MathCraft runtime and the external OCR model already configured in the desktop application through a versioned job API. Clients cannot provide or read upstream URLs, model names, credentials, paths, or prompts.

## Enable and discover

The service is disabled by default. Enable **自动化接口** in Settings. Local mode listens on `127.0.0.1:28765` by default and writes a private, per-session discovery file:

- Windows and Linux: `~/.latexsnipper/automation-api.json`
- macOS: `~/Library/Application Support/LaTeXSnipper/automation-api.json`

The file contains `base_url`, `api_version`, `pid`, and a Bearer `token`. The local token changes every time the service starts and the file is removed when it stops. Clients must not log or redistribute it.

## Routes

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/health` | No | Minimal service health |
| `GET` | `/api/v1/config` | Bearer | Capabilities, permissions, and limits |
| `POST` | `/api/v1/recognition/jobs` | Bearer | Create an upload job or a passive next-result subscription |
| `GET` | `/api/v1/recognition/jobs/{id}` | Bearer | Read an owned job |
| `DELETE` | `/api/v1/recognition/jobs/{id}` | Bearer | Cancel an owned job |

Job states are `awaiting_result`, `queued`, `running`, `completed`, `failed`, and `canceled`. Results remain in input order. A batch can complete with both successful and failed items.

## Upload one or more images

Send `multipart/form-data` with optional `backend`, `mode`, optional `timeout`, and one to sixteen repeated `images` parts. Backends are `mathcraft` (default) and `external`. Modes are `formula`, `text`, and `mixed`. The user-facing input list contains eight extensions—PNG, JPG, JPEG, BMP, GIF, TIF, TIFF, and WEBP—representing six actual encodings: PNG, JPEG, BMP, GIF, TIFF, and WebP. Actual encoded content is inspected rather than trusting the extension or MIME type.

```bash
curl -sS "$BASE_URL/api/v1/recognition/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Prefer: wait=30" \
  -H "Idempotency-Key: client-generated-retry-key" \
  -F backend=mathcraft \
  -F mode=formula \
  -F timeout=120 \
  -F "images=@formula.png"
```

If the job finishes during `Prefer: wait`, the server returns `200`; otherwise it returns `202` with a `Location` header and the current snapshot. HTTP wait timeout never cancels the background job.

## Wait for the next desktop result

```json
{
  "input": {"type": "next_result"},
  "timeout": 120
}
```

`next_result` is a passive, one-shot local subscription used by the official Office client. It never opens the capture overlay, starts recognition, changes windows, or suppresses the normal desktop result. The next recognition explicitly started by the user continues through the ordinary desktop flow, while a copy of its result completes the waiting job. Only one waiter is allowed at a time. Remote keys always receive `forbidden` because observing desktop recognition results would cross the remote privacy boundary.

## Remote security

Remote access is disabled by default. LaTeXSnipper permits remote mode only with:

1. a concrete address belonging to a Tailscale, WireGuard, or equivalent VPN tunnel interface; or
2. HTTPS with a user-selected certificate and private key (TLS 1.2 minimum).

Remote mode always requires an independent remote Bearer key. It is never returned by an endpoint. Remote keys initially have only `recognition.mathcraft`; `recognition.external` must be enabled separately. External access can consume a local Ollama/MinerU service or paid online API quota, but still cannot inspect or override its configuration. Remote clients can only submit existing images and cannot subscribe to desktop results or open desktop UI. Browser CORS is absent unless the request Origin exactly matches the configured whitelist. Do not expose a tunnel-mode HTTP listener directly to the public internet.

Tunnel mode rejects ordinary LAN and public-interface addresses. For SSH port forwarding or a reverse proxy, keep LaTeXSnipper in local mode; let SSH carry the loopback connection or terminate HTTPS at the proxy. Mobile clients such as iOS Shortcuts and Android Tasker should call the HTTPS or encrypted-tunnel address with the remote key.

### Desktop settings quick reference

For local Office and automation clients, keep `仅本机`, port `28765`, and `127.0.0.1`. Local clients should discover the rotating session token from `automation-api.json`; do not hard-code it.

For a Tailscale or WireGuard device:

1. Join the LaTeXSnipper computer and remote device to the same encrypted network.
2. Select `远程设备` and `安全隧道（推荐）`.
3. Set the listener to the LaTeXSnipper computer's tunnel-interface IP, not the client IP, LAN IP, router IP, or `0.0.0.0`.
4. Keep port `28765` unless it conflicts, generate a remote key, acknowledge the warning, and save.
5. Leave the Origin list empty for Shortcuts, Tasker, curl, Python, and native clients. Add exact `scheme://host[:port]` values only for browser JavaScript.
6. Enable remote external-model access only when its resource or billing impact is acceptable.

The remote base URL is `http://<tunnel-address>:28765`; tunnel encryption protects the HTTP hop. HTTPS mode instead requires a certificate/private-key pair whose SAN matches the address used by clients and whose issuer is trusted by those clients.

Saving changed network or permission settings while the API is running performs an asynchronous stop/start so the listener and authentication state are replaced. The local session token consequently rotates. Saving an unchanged effective configuration does not restart the service. Avoid changing settings during active jobs; if start or stop consistently takes several seconds, check port conflicts, firewall/security software, certificate files, and the runtime log.

## Limits and errors

Initial limits are 16 MiB per encoded image, 64 MiB per request, 16 images per batch, 40 MP per image, 80 MP decoded per request, 32 queued jobs, and 256 MiB shared normalized-image memory across queued and running jobs. Upload decoding is serialized, so concurrent large requests cannot multiply the decoded-image peak. Remote submissions default to 20 per minute per key and source IP.

Errors use this shape and never include image content, credentials, local paths, or tracebacks:

```json
{"error":{"code":"queue_full","message":"识别队列已满。","request_id":"..."}}
```

See [`examples/automation`](../examples/automation/) for Python, curl, AutoKey, AutoHotkey, and Hammerspoon clients.
