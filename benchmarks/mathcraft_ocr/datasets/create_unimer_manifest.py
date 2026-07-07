# coding: utf-8

from __future__ import annotations

import argparse
import json
from pathlib import Path


SUBSETS = {
    "spe": "simple_printed_expression",
    "cpe": "complex_printed_expression",
    "sce": "screen_captured_expression",
    "hwe": "handwritten_expression",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create MathCraft manifest from UniMER-Test.")
    parser.add_argument(
        "--root",
        required=True,
        help="Path to extracted UniMER-Test directory containing spe/cpe/sce/hwe folders.",
    )
    parser.add_argument("--output", required=True, help="Output JSONL manifest path.")
    args = parser.parse_args(argv)

    root = _normalize_root(Path(args.root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with output.open("w", encoding="utf-8") as fh:
        for subset, subset_name in SUBSETS.items():
            labels = _read_labels(root / f"{subset}.txt")
            image_dir = root / subset
            image_paths = sorted(image_dir.glob("*.png"), key=lambda item: item.name)
            if len(labels) == len(image_paths):
                image_label_pairs = list(zip(image_paths, labels))
            elif all(_is_int_stem(path) and int(path.stem) < len(labels) for path in image_paths):
                image_label_pairs = [(path, labels[int(path.stem)]) for path in image_paths]
            else:
                raise ValueError(
                    f"{subset}: label count {len(labels)} does not match image count {len(image_paths)}"
                )
            for image_path, target_latex in image_label_pairs:
                item = {
                    "id": f"unimer_test_{subset}_{image_path.stem}",
                    "task": "formula",
                    "profile": "formula",
                    "image": str(image_path),
                    "target_latex": target_latex,
                    "source": "UniMER-Test",
                    "license": "apache-2.0",
                    "difficulty": _difficulty_for_subset(subset),
                    "tags": ["unimer-test", subset, subset_name],
                }
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
                count += 1

    print(f"wrote {count} UniMER-Test manifest rows to {output}")
    return 0


def _normalize_root(root: Path) -> Path:
    if (root / "spe").exists():
        return root
    nested = root / "UniMER-Test"
    if (nested / "spe").exists():
        return nested
    raise FileNotFoundError(f"could not find UniMER-Test subsets under {root}")


def _read_labels(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _is_int_stem(path: Path) -> bool:
    try:
        int(path.stem)
    except ValueError:
        return False
    return True


def _difficulty_for_subset(subset: str) -> str:
    if subset == "spe":
        return "easy"
    if subset in {"cpe", "sce"}:
        return "complex"
    return "moderate"


if __name__ == "__main__":
    raise SystemExit(main())
