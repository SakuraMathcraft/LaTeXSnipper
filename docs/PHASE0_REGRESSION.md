# Phase0 Regression Baseline

This document freezes current behavior for v1.05 before the Tauri/Rust migration.

## Scope

- Screenshot recognition: model routing from UI mode to pix2text runtime mode.
- PDF recognition output: markdown/latex wrapping contract.
- Dependency wizard core contract: HEAVY_CPU/HEAVY_GPU conflict handling and GPU reinstall decision.
- Restart flow contract: restart command/env for "open dependency wizard after restart".

## Automated Cases

Run:

```powershell
python -m unittest discover -s tests -p "test_phase0_*.py" -v
```

Cases included:

- `tests/test_phase0_model_routing.py`
- `tests/test_phase0_pdf_output.py`
- `tests/test_phase0_deps_contract.py`
- `tests/test_phase0_restart_contract.py`

## Manual Smoke Checklist (GUI)

1. Screenshot recognition
   - Open app, select each pix2text mode (`formula/mixed/text/page/table`), perform one screenshot.
   - Confirm result dialog appears and no freeze.

2. PDF recognition
   - Open one small PDF (1-3 pages), run markdown export and latex export once each.
   - Confirm output window opens and content is non-empty.

3. Dependency wizard
   - Open wizard from settings, ensure `HEAVY_CPU` and `HEAVY_GPU` cannot both stay selected.
   - Switch between CPU/GPU layer once, verify no contradictory state is persisted.

4. Restart from settings
   - Open dependency wizard entry from settings and choose restart.
   - Confirm new process launches and old process exits without lock conflict.

