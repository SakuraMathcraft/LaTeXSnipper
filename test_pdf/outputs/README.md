# MathCraft PDF OCR Regression Outputs

This directory is for local generated regression outputs. Generated files are ignored by git.

Keep comparable runs in this shape:

```text
outputs/
  <topic>_regression_vN/
    summary.json
    <case_name>/
      document_engine.md
      structured.json
```

Comparable baselines:

| Directory | Purpose |
| --- | --- |
| `block_layout_regression_v3` | Current block/layout regression after role/column/paragraph annotations, OCR crop filtering, and structured document-engine consumption. |
| `block_layout_regression_v2` | Previous structured page result baseline used for v3 comparison. |

Rules:

- Every comparable run must include `summary.json`.
- Case folders should include the source PDF name/page in either the folder name or the summary entry.
- Temporary smoke outputs should be deleted after inspection or recreated on demand.
- Do not use timestamp-only folders as baselines; include the feature area and version number.
