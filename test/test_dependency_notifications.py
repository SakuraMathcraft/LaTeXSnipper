from __future__ import annotations


import bootstrap.deps_ui as deps_ui_module


def test_hosted_user_notice_uses_a_nonblocking_infobar(monkeypatch) -> None:
    calls: list[tuple[object, str, str, str, int]] = []
    monkeypatch.setattr(
        deps_ui_module,
        "show_info_bar",
        lambda parent, title, content, level, duration: calls.append(
            (parent, title, content, level, duration)
        ),
    )
    parent = object()

    assert deps_ui_module.show_user_notice("错误", "操作失败", parent) is True
    assert calls == [(parent, "错误", "操作失败", "error", 5000)]
