# LaTeXSnipper Tauri Client v0.1.0

Release Date: 2026-02-25

## Summary

This release provides the first installable Tauri client for LaTeXSnipper, backed by the local Python daemon RPC pipeline.

## Highlights

- Migrated UI shell to Tauri client with Acrylic/Mica visual modes.
- Added compact window mode with:
  - reduced footprint,
  - always-on-top behavior,
  - live recognition preview area under the title.
- Added global hotkey capture flow and image recognition task polling.
- Added PDF task flow with page limit, DPI control, and Markdown/LaTeX export.
- Added environment page for dependency-layer installation tasks:
  - `BASIC`, `CORE`, `HEAVY_CPU`, `HEAVY_GPU`,
  - progress polling and cancellation.
- Added task/result feedback pills and improved non-blocking task interactions.
- Added auto-copy behavior for image recognition LaTeX output on success.

## Notes

- `DPI` is active and passed into PDF rasterization.
- Document template selection is active at export/wrapping stage.
- Build currently validated on Windows host.

## Build Commands

Use native builds on each target OS (recommended).  
Working directory below assumes:

```powershell
cd E:\LaTexSnipper\apps\tauri-client\src-tauri
```

### 1) Build release executable only (no installer)

```powershell
cargo tauri build --no-bundle
```

Output:

- `target\release\latexsnipper-tauri-client.exe`

### 2) Windows installers

MSI:

```powershell
cargo tauri build --bundles msi
```

NSIS:

```powershell
cargo tauri build --bundles nsis
```

Both:

```powershell
cargo tauri build --bundles msi,nsis
```

Outputs:

- `target\release\bundle\msi\...`
- `target\release\bundle\nsis\...`

### 3) macOS (run on macOS host)

Apple Silicon:

```bash
cargo tauri build --target aarch64-apple-darwin
```

Intel:

```bash
cargo tauri build --target x86_64-apple-darwin
```

Universal:

```bash
cargo tauri build --target universal-apple-darwin
```

### 4) Linux (run on Linux host)

```bash
cargo tauri build
```

Optional bundle selection (depends on distro toolchain availability):

```bash
cargo tauri build --bundles appimage,deb,rpm
```

## Prerequisites Checklist

- Rust + Cargo
- `cargo-tauri` CLI
- Node.js (if frontend rebuild is needed before packaging)
- Platform-specific packaging toolchains:
  - Windows: WiX/NSIS (auto-downloaded by Tauri unless pre-cached)
  - macOS: Xcode command line tools
  - Linux: distro packaging dependencies for `deb/rpm/appimage`

## Known Constraints

- Some runtime features (global hotkey/capture behaviors) are currently optimized for Windows path first.
- Cross-platform feature parity should be verified per OS before public release.
