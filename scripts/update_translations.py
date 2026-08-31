"""Update the Qt Linguist catalog from LaTeXSnipper ``tr()`` calls."""

from __future__ import annotations

import argparse
import ast
import string
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = ROOT / "src"
CATALOG_PATH = SOURCE_ROOT / "assets" / "i18n" / "latexsnipper_en_US.ts"


def _is_translation_call(node: ast.Call) -> bool:
    function = node.func
    return isinstance(function, ast.Name) and function.id in {
        "mark_for_translation",
        "tr",
        "translate",
    }


def collect_messages() -> dict[str, list[tuple[str, int]]]:
    messages: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_translation_call(node):
                continue
            if not node.args:
                continue
            source = node.args[0]
            if not isinstance(source, ast.Constant) or not isinstance(
                source.value, str
            ):
                continue
            location = (relative, int(getattr(node, "lineno", 0)))
            if location not in messages[source.value]:
                messages[source.value].append(location)
    return dict(sorted(messages.items()))


def read_existing_translations() -> dict[str, tuple[str, str | None]]:
    if not CATALOG_PATH.exists():
        return {}
    root = ET.parse(CATALOG_PATH).getroot()
    translations: dict[str, tuple[str, str | None]] = {}
    for message in root.findall("./context/message"):
        source = message.findtext("source")
        translation = message.find("translation")
        if source is None or translation is None:
            continue
        translations[source] = (translation.text or "", translation.get("type"))
    return translations


def build_catalog(messages: dict[str, list[tuple[str, int]]]) -> bytes:
    existing = read_existing_translations()
    root = ET.Element(
        "TS",
        {
            "version": "2.1",
            "language": "en_US",
            "sourcelanguage": "zh_CN",
        },
    )
    context = ET.SubElement(root, "context")
    ET.SubElement(context, "name").text = "LaTeXSnipper"
    for source, locations in messages.items():
        message = ET.SubElement(context, "message")
        for filename, line in locations:
            ET.SubElement(
                message,
                "location",
                {"filename": f"../../../{filename}", "line": str(line)},
            )
        ET.SubElement(message, "source").text = source
        translation_text, translation_type = existing.get(source, ("", "unfinished"))
        attributes = {"type": translation_type} if translation_type else {}
        translation = ET.SubElement(message, "translation", attributes)
        translation.text = translation_text
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return body.replace(b"'utf-8'", b'"utf-8"') + b"\n"


def validate_catalog() -> list[str]:
    errors: list[str] = []
    formatter = string.Formatter()
    root = ET.parse(CATALOG_PATH).getroot()
    for message in root.findall("./context/message"):
        source = message.findtext("source") or ""
        translation = message.find("translation")
        translated = translation.text if translation is not None else ""
        if (
            translation is None
            or translation.get("type") == "unfinished"
            or not translated
        ):
            errors.append(f"unfinished translation: {source!r}")
            continue
        source_fields = {name for _, name, _, _ in formatter.parse(source) if name}
        translated_fields = {
            name for _, name, _, _ in formatter.parse(translated) if name
        }
        if source_fields != translated_fields:
            errors.append(
                f"placeholder mismatch for {source!r}: "
                f"source={sorted(source_fields)!r} translation={sorted(translated_fields)!r}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the checked-in catalog is not current",
    )
    args = parser.parse_args()
    rendered = build_catalog(collect_messages())
    current = CATALOG_PATH.read_bytes() if CATALOG_PATH.exists() else b""
    if args.check:
        if current != rendered:
            print(f"translation catalog is stale: {CATALOG_PATH}", file=sys.stderr)
            return 1
        errors = validate_catalog()
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        return 0
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_bytes(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
