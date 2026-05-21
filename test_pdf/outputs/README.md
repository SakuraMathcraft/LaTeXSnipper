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

Comparable baseline:

| Directory | Purpose |
| --- | --- |
| `block_layout_regression_v4` | Current block/layout regression baseline for role, column, paragraph, OCR crop filtering, and structured document-engine output. |

Rules:

- Every comparable run must include `summary.json`.
- Case folders should include the source PDF name/page in either the folder name or the summary entry.
- Temporary smoke outputs should be deleted after inspection or recreated on demand.
- Do not use timestamp-only folders as baselines; include the feature area and version number.
- Retain older generated output folders only when actively comparing a regression. They are ignored by git and should not be documented as current baselines.
