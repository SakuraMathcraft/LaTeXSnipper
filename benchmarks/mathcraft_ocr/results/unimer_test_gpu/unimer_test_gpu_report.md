# MathCraft OCR on UniMER-Test

Reported outputs are produced by the full MathCraft runtime, not raw decoder strings.

- Results: 23757
- Providers: {'CUDAExecutionProvider': 23757}
- Failures: 0
- Empty outputs: 0

| Subset | Count | Norm Exact | Compact Exact | Avg Sim | Median Sim | Sim >= .95 | P50 ms | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 23757 | 25.88% | 38.40% | 0.8885 | 0.9677 | 56.08% | 158.5 | 1482.9 |
| spe | 6762 | 23.82% | 53.76% | 0.9676 | 1.0000 | 81.75% | 237.6 | 754.2 |
| cpe | 5921 | 0.22% | 1.47% | 0.8566 | 0.9017 | 25.86% | 849.3 | 2404.0 |
| sce | 4742 | 27.63% | 36.88% | 0.8309 | 0.9286 | 46.10% | 70.1 | 254.6 |
| hwe | 6332 | 50.76% | 57.68% | 0.8770 | 1.0000 | 64.42% | 94.0 | 191.4 |

| Subset | BLEU-4 | Avg Char NED | Median Char NED | Avg Token NED | Median Token NED |
| --- | ---: | ---: | ---: | ---: | ---: |
| all | 0.7946 | 0.1520 | 0.0559 | 0.1342 | 0.0625 |
| spe | 0.9212 | 0.0520 | 0.0000 | 0.0480 | 0.0000 |
| cpe | 0.7564 | 0.2005 | 0.1629 | 0.1801 | 0.1410 |
| sce | 0.6962 | 0.2314 | 0.1250 | 0.2085 | 0.1342 |
| hwe | 0.8481 | 0.1542 | 0.0000 | 0.1278 | 0.0000 |
