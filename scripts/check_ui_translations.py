"""Reject untranslated string literals passed directly to common UI APIs."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
UI_DIRECTORIES = (
    "bootstrap",
    "capture",
    "editor",
    "exporting",
    "handwriting",
    "platform_services",
    "preview/document",
    "recognition",
    "ui",
    "update",
)
DOMAIN_BOUNDARY_DIRECTORIES = ("rendering", "runtime")
TRANSLATION_FUNCTIONS = {"tr", "translate", "mark_for_translation"}
USER_TEXT_CALLS = {
    "Action",
    "BodyLabel",
    "CaptionLabel",
    "CenterMenu",
    "CheckBox",
    "Label",
    "PrimaryPushButton",
    "PushButton",
    "QAction",
    "QCheckBox",
    "QGroupBox",
    "QLabel",
    "QProgressDialog",
    "QPushButton",
    "QRadioButton",
    "QToolButton",
    "RoundMenu",
    "SubtitleLabel",
    "TitleLabel",
    "setInformativeText",
    "setLabelText",
    "setTitle",
    "setPlaceholderText",
    "setStatusTip",
    "setText",
    "setToolTip",
    "setWindowTitle",
    "showMessage",
}
MULTI_TEXT_ARGUMENTS = {
    "QProgressDialog": (0, 1),
    "_add_section": (1, 2),
    "_exec_close_only_message_box": (1, 2),
    "_field": (0, 2),
    "_notify_parent": (0, 1),
    "_path_field": (0, 2, 3),
    "_pick_item": (1, 2),
    "_show_capture_notice": (0, 1),
    "_select_existing_directory_with_icon": (1,),
    "_select_open_file_with_icon": (1, 3),
    "_select_save_file_with_icon": (1, 3),
    "_set_compute_mode_text": (0,),
    "_set_info_text": (0,),
    "_set_status": (0,),
    "_show_info": (0, 1),
    "_show_error": (0, 1),
    "_show_warning": (0, 1),
    "_warn": (0, 1),
    "_warning_dialog": (0, 1),
    "_emit_status": (0,),
    "addAction": (0,),
    "add_btn": (0, 1),
    "addItem": (0,),
    "addMenu": (0,),
    "addTab": (1,),
    "getOpenFileName": (1, 3),
    "getSaveFileName": (1, 3),
    "question_close_only": (1, 2),
    "question": (1, 2),
    "set_action_status": (0,),
    "show_action_status": (0,),
    "show_info_bar": (1, 2),
    "show_user_notice": (1, 2),
    "show_notification": (1, 2),
}
KEYWORD_TEXT_ARGUMENTS = {
    "_show_capture_notice": {"title", "message"},
    "_show_export_menu_for_source": {"empty_hint"},
    "_show_formula_rename_dialog": {"title", "prompt"},
    "show_formula_export_menu": {"empty_hint"},
    "show_formula_rename_dialog": {"title", "prompt"},
}
INFO_BAR_CALLS = {"error", "info", "success", "warning"}


def _call_name(call: ast.Call) -> str:
    function = call.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return ""


def _call_owner_name(call: ast.Call) -> str:
    function = call.func
    if not isinstance(function, ast.Attribute) or function.attr != "emit":
        return ""
    owner = function.value
    return owner.attr if isinstance(owner, ast.Attribute) else ""


def _is_translated(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) in TRANSLATION_FUNCTIONS


def _is_user_text_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        value = node.value if isinstance(node.value, str) else ""
    elif isinstance(node, ast.JoinedStr):
        value = "".join(
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
    else:
        return False
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def _contains_user_text_literal(node: ast.AST) -> bool:
    return any(_is_user_text_literal(child) for child in ast.walk(node))


def _source_files() -> list[Path]:
    files: set[Path] = set()
    for relative in UI_DIRECTORIES:
        files.update((SOURCE_ROOT / relative).rglob("*.py"))
    return sorted(files)


def main() -> int:
    failures: list[str] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if (
                name in TRANSLATION_FUNCTIONS
                and node.args
                and isinstance(node.args[0], ast.JoinedStr)
            ):
                relative = path.relative_to(PROJECT_ROOT)
                failures.append(
                    f"{relative}:{node.args[0].lineno} (dynamic translation key)"
                )
                continue
            indexes = MULTI_TEXT_ARGUMENTS.get(
                name, (0,) if name in USER_TEXT_CALLS else ()
            )
            if name == "emit" and _call_owner_name(node) in {"failed", "status_updated"}:
                indexes = (0,)
            arguments = [
                node.args[index] for index in indexes if index < len(node.args)
            ]
            if name in INFO_BAR_CALLS:
                arguments.extend(
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg in {"title", "content"}
                )
            keyword_names = KEYWORD_TEXT_ARGUMENTS.get(name, set())
            arguments.extend(
                keyword.value
                for keyword in node.keywords
                if keyword.arg in keyword_names
            )
            for argument in arguments:
                if _is_user_text_literal(argument) and not _is_translated(argument):
                    relative = path.relative_to(PROJECT_ROOT)
                    failures.append(f"{relative}:{argument.lineno}")
    for directory in DOMAIN_BOUNDARY_DIRECTORIES:
        for path in sorted((SOURCE_ROOT / directory).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Return)
                    and node.value is not None
                    and _contains_user_text_literal(node.value)
                ):
                    relative = path.relative_to(PROJECT_ROOT)
                    failures.append(
                        f"{relative}:{node.lineno} (localized domain return)"
                    )
    if failures:
        print("Untranslated UI string literals:")
        print("\n".join(f"  {item}" for item in failures))
        return 1
    print("UI translation call-site check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
