# coding: utf-8

from __future__ import annotations

import argparse
import csv
import html
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an HTML gallery for render consistency pairs.")
    parser.add_argument("--rows", required=True, help="render_unimer_samples row CSV.")
    parser.add_argument("--image-dir", required=True, help="Directory containing *_pred.png and *_target.png.")
    parser.add_argument("--output", required=True, help="Output HTML file.")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)

    rows = list(csv.DictReader(Path(args.rows).open(encoding="utf-8")))
    rows = [row for row in rows if row.get("both_render_ok") == "True"]
    rows.sort(key=lambda row: float(row.get("global_ssim") or 0.0), reverse=True)
    rows = rows[: args.limit]

    image_dir = Path(args.image_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    cards = []
    for row in rows:
        sample_id = row["sample_id"]
        pred = image_dir / f"{sample_id}_pred.png"
        target = image_dir / f"{sample_id}_target.png"
        pred_src = pred.relative_to(output.parent).as_posix()
        target_src = target.relative_to(output.parent).as_posix()
        cards.append(
            f"""
            <section class="card">
              <h2>{html.escape(sample_id)} <span>{html.escape(row['subset'])}</span></h2>
              <p>text sim={float(row['text_similarity']):.4f}, pixel={float(row['pixel_similarity']):.4f}, ssim={float(row['global_ssim']):.4f}</p>
              <div class="pair">
                <figure><figcaption>MathCraft</figcaption><img src="{html.escape(pred_src)}"></figure>
                <figure><figcaption>Target</figcaption><img src="{html.escape(target_src)}"></figure>
              </div>
            </section>
            """
        )

    output.write_text(
        f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>MathCraft Render Consistency Gallery</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; color: #111; }}
h1 {{ font-size: 22px; }}
.card {{ border-top: 1px solid #ddd; padding: 16px 0; }}
.card h2 {{ font-size: 15px; margin: 0 0 4px; }}
.card h2 span {{ color: #666; font-weight: normal; margin-left: 8px; }}
.card p {{ margin: 0 0 10px; color: #444; font-size: 13px; }}
.pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }}
figure {{ margin: 0; }}
figcaption {{ font-size: 12px; color: #666; margin-bottom: 6px; }}
img {{ max-width: 100%; border: 1px solid #ddd; background: white; }}
</style>
</head>
<body>
<h1>MathCraft Render Consistency Gallery</h1>
{''.join(cards)}
</body>
</html>
""",
        encoding="utf-8",
    )
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
