# 文件：`src/compat_messagebox.py`（或直接放到 `src/main.py` 最前面）
from PyQt6.QtWidgets import QMessageBox as _QM

def _install_messagebox_shim():
    try:
        from qfluentwidgets import MessageBox as _QFMessageBox
    except Exception:
        _QFMessageBox = None

    # 标准按钮映射，保证 MessageBox.StandardButton 可用
    class _Std:
        Yes = _QM.StandardButton.Yes
        No = _QM.StandardButton.No
        Ok = _QM.StandardButton.Ok
        Cancel = _QM.StandardButton.Cancel

    # 回退实现（统一静态接口）
    def _info(parent, title, content):
        return _QM.information(parent, title, content)

    def _warn(parent, title, content):
        return _QM.warning(parent, title, content)

    def _crit(parent, title, content):
        return _QM.critical(parent, title, content)

    def _ask(parent, title, content, buttons=None):
        if buttons is None:
            buttons = _QM.StandardButton.Yes | _QM.StandardButton.No
        return _QM.question(parent, title, content, buttons)

    if _QFMessageBox is None:
        # qfluentwidgets 不可用时，提供完全回退类
        class _Compat:
            StandardButton = _Std
            information = staticmethod(_info)
            warning = staticmethod(_warn)
            critical = staticmethod(_crit)
            question = staticmethod(_ask)
        return _Compat

    # 有 qfluentwidgets 时，按需打补丁补全静态方法与枚举
    M = _QFMessageBox
    if not hasattr(M, "StandardButton"):
        M.StandardButton = _Std
    for name, fn in {
        "information": _info,
        "warning": _warn,
        "critical": _crit,
        "question": _ask
    }.items():
        if not hasattr(M, name):
            setattr(M, name, staticmethod(fn))
    return M

# 对外导出：后续直接用 MessageBox.warning / information / question
MessageBox = _install_messagebox_shim()
