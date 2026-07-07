# coding: utf-8

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = {"image", "latex", "sample_id", "split_tag", "data_type"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a fixed MathWriting test manifest and export offline raster images."
    )
    parser.add_argument("--parquet", required=True, help="MathWriting test parquet file.")
    parser.add_argument("--output", required=True, help="Output JSONL manifest path.")
    parser.add_argument("--image-dir", required=True, help="Directory for exported offline raster images.")
    parser.add_argument("--split", default="test", choices=["test"], help="Fixed MathWriting split.")
    parser.add_argument("--limit", type=int, default=0, help="Optional debug row limit.")
    parser.add_argument("--force", action="store_true", help="Rewrite existing exported images.")
    args = parser.parse_args(argv)

    parquet_path = Path(args.parquet)
    output_path = Path(args.output)
    image_dir = Path(args.image_dir)

    dataframe = pd.read_parquet(parquet_path)
    validate_dataframe(dataframe, args.split)
    dataframe = dataframe[(dataframe["split_tag"] == args.split) & (dataframe["data_type"] == "human")]
    if args.limit > 0:
        dataframe = dataframe.head(args.limit)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for row in dataframe.itertuples(index=False):
            image_path = export_image(row.image, image_dir=image_dir, force=args.force)
            item = {
                "id": f"mathwriting_test_{row.sample_id}",
                "task": "formula",
                "profile": "formula",
                "image": str(image_path),
                "target_latex": str(row.latex),
                "source": "MathWriting",
                "license": "CC-BY-NC-SA-4.0",
                "split": "test",
                "difficulty": "handwritten",
                "tags": ["mathwriting", "test", "human", "handwritten_expression"],
            }
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            count += 1

    print(f"wrote {count} MathWriting test manifest rows to {output_path}")
    print(f"exported offline raster images under {image_dir}")
    return 0


def validate_dataframe(dataframe: pd.DataFrame, split: str) -> None:
    missing = sorted(REQUIRED_COLUMNS - set(dataframe.columns))
    if missing:
        raise ValueError(f"MathWriting parquet is missing columns: {missing}")
    split_values = set(str(value) for value in dataframe["split_tag"].dropna().unique())
    data_types = set(str(value) for value in dataframe["data_type"].dropna().unique())
    if split_values != {split}:
        raise ValueError(f"Expected only split_tag={split!r}, got {sorted(split_values)}")
    if data_types != {"human"}:
        raise ValueError(f"Expected only data_type='human', got {sorted(data_types)}")


def export_image(image_value: Any, *, image_dir: Path, force: bool) -> Path:
    if not isinstance(image_value, dict):
        raise TypeError(f"Expected image dict, got {type(image_value).__name__}")
    raw_bytes = image_value.get("bytes")
    if not isinstance(raw_bytes, bytes):
        raise TypeError("Expected image['bytes'] to contain raster bytes")
    raw_name = str(image_value.get("path") or "").strip()
    if not raw_name:
        raise ValueError("Expected image['path'] to contain a file name")
    image_path = image_dir / Path(raw_name).name
    if force or not image_path.exists():
        image_path.write_bytes(raw_bytes)
    return image_path.resolve()


if __name__ == "__main__":
    raise SystemExit(main())
