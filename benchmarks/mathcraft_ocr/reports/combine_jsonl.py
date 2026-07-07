# coding: utf-8

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Combine JSONL shards without re-encoding damage.")
    parser.add_argument("--list-file", required=True, help="UTF-8 text file containing shard paths.")
    parser.add_argument("--output", required=True, help="Combined JSONL output path.")
    args = parser.parse_args(argv)

    list_path = Path(args.list_file)
    output_path = Path(args.output)
    paths = [
        Path(line.strip())
        for line in list_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if not paths:
        raise ValueError(f"no shard paths in {list_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as out:
        for path in paths:
            if not path.exists():
                raise FileNotFoundError(path)
            with path.open("r", encoding="utf-8-sig") as src:
                for line in src:
                    text = line.rstrip("\r\n")
                    if not text:
                        continue
                    out.write(text + "\n")
                    row_count += 1
    print(f"combined {len(paths)} shards and {row_count} rows into {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
