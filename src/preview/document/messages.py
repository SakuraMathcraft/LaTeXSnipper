"""Localized presentation text for structured document-rendering messages."""

from __future__ import annotations

from localization.manager import mark_for_translation, translate as tr
from rendering.latex import RenderMessage


_RENDER_MESSAGE_SOURCES = {
    "compile.unsupported_mode": mark_for_translation(
        "请先在设置中选择 LaTeX + pdflatex 或 LaTeX + xelatex。"
    ),
    "compile.engine_missing": mark_for_translation(
        "未找到可用的 {engine}，请先在设置中完成 LaTeX 路径配置。"
    ),
    "compile.empty_document": mark_for_translation(
        "当前没有可编译的 TeX 文档内容。"
    ),
    "compile.generated_with_errors": mark_for_translation(
        "编译存在错误，已尽量生成 PDF。请查看下方编译日志。"
    ),
    "compile.generated_with_warnings": mark_for_translation(
        "编译完成，但存在警告；请查看下方编译日志。"
    ),
    "compile.failed": mark_for_translation(
        "TeX 文档编译失败，请检查源码和 LaTeX 环境。"
    ),
    "compile.failed_detail": mark_for_translation("TeX 文档编译失败：{detail}"),
    "compile.timeout": mark_for_translation(
        "TeX 文档编译超时，请检查内容或 LaTeX 环境。"
    ),
    "compile.exception": mark_for_translation("TeX 文档编译失败：{error}"),
    "synctex.unsupported_mode": mark_for_translation(
        "当前渲染引擎不支持 SyncTeX。"
    ),
    "synctex.command_missing": mark_for_translation(
        "未找到可用的 synctex 命令。"
    ),
    "synctex.pdf_missing": mark_for_translation("PDF 预览文件不存在。"),
    "synctex.source_missing": mark_for_translation("源码文件不存在。"),
    "synctex.query_failed": mark_for_translation("SyncTeX 查询失败：{error}"),
    "synctex.source_parse_failed": mark_for_translation(
        "未能从 SyncTeX 输出中解析源码位置。"
    ),
    "synctex.source_parse_detail": mark_for_translation(
        "未能从 SyncTeX 输出中解析源码位置：{detail}"
    ),
    "synctex.pdf_parse_failed": mark_for_translation(
        "未能从 SyncTeX 输出中解析 PDF 坐标。"
    ),
    "synctex.pdf_parse_detail": mark_for_translation(
        "未能从 SyncTeX 输出中解析 PDF 坐标：{detail}"
    ),
    "synctex.output_parse_failed": mark_for_translation("SyncTeX 输出解析失败。"),
}
_UNKNOWN_RENDER_MESSAGE = mark_for_translation("操作未完成，请查看日志。")


def render_message_text(message: RenderMessage | None) -> str:
    """Translate a rendering message at the UI boundary."""
    if message is None:
        return ""
    source = _RENDER_MESSAGE_SOURCES.get(message.code, _UNKNOWN_RENDER_MESSAGE)
    try:
        return tr(source).format(**message.format_parameters())
    except (KeyError, ValueError):
        return tr(_UNKNOWN_RENDER_MESSAGE)


__all__ = ["render_message_text"]
