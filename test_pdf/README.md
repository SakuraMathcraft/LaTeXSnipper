# MathCraft PDF Test Fixtures

This directory contains stable local PDF fixtures for OCR, block layout, document engine, and TeX export regression checks.

## Source PDFs

Keep these files as fixed test inputs:

| File | Primary coverage |
| --- | --- |
| `Brouwer Fixed Point Theorem.pdf` | English article, headings, prose, inline math, display math |
| `Absract Algebra.pdf` | English textbook, dense formulas, examples, long mathematical paragraphs |
| `Limits, Series, and Fractional Part Integrals.pdf` | English prose-heavy math book, preface and mixed inline formulas |
| `清疏大学生数学竞赛班第十一届讲义-已解锁.pdf` | Chinese math lecture notes, Chinese OCR, symbols, dense paragraphs |
| `动力系统期刊.pdf` | Chinese academic-style PDF, layout and prose regression |

## Output Policy

Generated outputs belong under `outputs/` and are ignored by git except for `outputs/README.md`.

Use versioned folders for comparable baselines:

```text
outputs/
  <feature>_regression_vN/
    summary.json
    <case_name>/
      document_engine.md
      structured.json
```

Delete one-off smoke outputs after inspection. Do not keep timestamp-only or ambiguous output folders.
