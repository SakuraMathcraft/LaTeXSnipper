"""Declarative content for the main-window introduction."""

from dataclasses import dataclass

from localization.manager import translate as tr


@dataclass(frozen=True)
class TourStep:
    title: str
    description: str
    icon: str
    targets: tuple[str, ...] = ()


def tour_steps() -> tuple[TourStep, ...]:
    return (
        TourStep(tr("欢迎使用 LaTeXSnipper"), tr("您的快速上手向导。"), "HOME"),
        TourStep(
            tr("从这里开始"),
            tr("识别、预览，再导出您的公式。"),
            "SEARCH",
            ("capture_button", "preview_view", "preview_fallback_label", "export_btn"),
        ),
        TourStep(
            tr("让操作更顺手"),
            tr("设置您习惯的截图快捷键。"),
            "EDIT",
            ("change_key_button",),
        ),
        TourStep(
            tr("关于模型准备"),
            tr("本地模型会在后台准备，首次使用可能需要下载。您可以在日志中查看详情。"),
            "SYNC",
            ("status_label",),
        ),
        TourStep(
            tr("一起让它变得更好"),
            tr("如果 LaTeXSnipper 对您有帮助，欢迎支持项目。"),
            "HEART",
        ),
        TourStep(tr("开始使用吧"), tr("欢迎，让公式处理更简单。"), "ACCEPT"),
    )
