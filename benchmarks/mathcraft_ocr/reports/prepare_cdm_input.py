# coding: utf-8

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert MathCraft formula results to the official CDM batch JSON format."
    )
    parser.add_argument("--results", required=True, help="MathCraft formula result JSONL.")
    parser.add_argument("--manifest", required=True, help="Formula manifest JSONL.")
    parser.add_argument("--output", required=True, help="Output CDM JSON file.")
    parser.add_argument("--subset", default="all", help="Optional manifest tag filter. Use 'all' for every row.")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum rows after subset filtering.")
    args = parser.parse_args(argv)

    manifest = read_manifest(Path(args.manifest))
    rows = read_jsonl(Path(args.results))
    converted: list[dict[str, str]] = []

    for row in rows:
        sample_id = str(row.get("sample_id", ""))
        target_row = manifest.get(sample_id)
        if not target_row:
            continue
        if not row_matches_subset(target_row, args.subset):
            continue
        converted.append(
            {
                "img_id": sample_id,
                "gt": str(target_row.get("target_latex", "")),
                "pred": str(row.get("text", "")),
            }
        )
        if args.limit > 0 and len(converted) >= args.limit:
            break

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(converted, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {len(converted)} CDM rows to {output}")
    return 0


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def read_manifest(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("id")): row for row in read_jsonl(path)}


def row_matches_subset(row: dict[str, Any], subset: str) -> bool:
    subset = subset.strip().lower()
    if subset == "all":
        return True
    tags = row.get("tags", [])
    if isinstance(tags, list):
        return subset in {str(tag).lower() for tag in tags}
    return False


if __name__ == "__main__":
    raise SystemExit(main())
