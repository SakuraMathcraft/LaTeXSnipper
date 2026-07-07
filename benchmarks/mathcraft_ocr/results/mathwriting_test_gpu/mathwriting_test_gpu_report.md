# MathCraft OCR on MathWriting Test

Protocol: fixed MathWriting test split, offline raster images, normalized LaTeX labels as ground truth.

- Results: 7644
- Providers: {'CUDAExecutionProvider': 7644}
- Failures: 0
- Empty outputs: 0

| Split | Count | Norm Exact | Compact Exact | Avg Sim | Median Sim | Sim >= .95 | P50 ms | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 7644 | 0.00% | 11.75% | 0.7194 | 0.7586 | 17.61% | 116.7 | 225.1 |
| test | 7644 | 0.00% | 11.75% | 0.7194 | 0.7586 | 17.61% | 116.7 | 225.1 |

| Split | BLEU-4 | Avg Char NED | Median Char NED | Avg Token NED | Median Token NED |
| --- | ---: | ---: | ---: | ---: | ---: |
| all | 0.5467 | 0.3547 | 0.3333 | 0.3239 | 0.2917 |
| test | 0.5467 | 0.3547 | 0.3333 | 0.3239 | 0.2917 |
