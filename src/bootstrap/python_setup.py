"""Dependency Python creation and pip toolchain initialization."""

import logging
from localization.manager import translate as tr
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


from runtime.dependency_runtime import (
    find_system_python3 as _find_system_python3,
    supported_system_python_range_label as _supported_system_python_range_label,
    system_python_unavailable as _system_python_unavailable,
)
from bootstrap.deps_pip_runner import _terminate_process
from PyQt6.QtCore import QThread, pyqtSignal
from bootstrap.deps_context import PIP_INSTALL_SUPPRESS_ARGS, flags, pip_ready_event
from runtime.processes import hidden_subprocess_kwargs

logger = logging.getLogger(f"latexsnipper.{__name__}")


def ensure_pip(main_python: Path) -> bool:
    """Ensure pip is available for the target interpreter."""
    import subprocess

    if not main_python.exists():
        raise RuntimeError(f"[ERR] 主 Python 不存在: {main_python}")

    try:
        name = main_python.name.lower()
        is_python_exe = (
            os.name == "nt" and name.startswith("python") and name.endswith(".exe")
        ) or (os.name != "nt" and (name.startswith("python") or "python" in name))
        if not is_python_exe:
            logger.debug("当前可执行文件不是 Python，跳过 pip 初始化: %s", main_python)
            return False
    except Exception:
        pass

    try:
        pth_candidates = list(main_python.parent.glob("python*.pth")) + list(
            main_python.parent.glob("python*._pth")
        )
        for pth_file in pth_candidates:
            content = pth_file.read_text(encoding="utf-8")
            if "#import site" in content:
                pth_file.write_text(
                    content.replace("#import site", "import site"), encoding="utf-8"
                )
    except Exception:
        pass

    def _pip_version_tuple(raw: str) -> tuple[int, ...]:
        parts: list[int] = []
        current = ""
        for ch in raw:
            if ch.isdigit():
                current += ch
            elif current:
                parts.append(int(current))
                current = ""
                if len(parts) >= 3:
                    break
        if current and len(parts) < 3:
            parts.append(int(current))
        return tuple(parts)

    def _query_pip_version() -> tuple[int, ...] | None:
        code = "import pip; print(pip.__version__)"
        proc = subprocess.run(
            [str(main_python), "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
        if proc.returncode != 0:
            return None
        return _pip_version_tuple(proc.stdout.strip())

    def _has_packaging_toolchain() -> bool:
        proc = subprocess.run(
            [str(main_python), "-c", "import setuptools, wheel"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        return proc.returncode == 0

    def _upgrade_packaging_toolchain() -> bool:
        cmd = [
            str(main_python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "setuptools",
            "wheel",
            "--no-cache-dir",
            *PIP_INSTALL_SUPPRESS_ARGS,
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
        if res.returncode != 0:
            logger.warning("pip 工具链升级失败: %s", res.stdout[-1000:])
            return False
        return True

    pip_version = _query_pip_version()
    if pip_version is None:
        try:
            subprocess.check_call(
                [str(main_python), "-m", "ensurepip", "--upgrade"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            pip_version = _query_pip_version()
        except Exception:
            pip_version = None

    if pip_version is None:
        logger.error("pip 不可用，且当前 Python 无法通过 ensurepip 初始化 pip。")
        return False

    needs_upgrade = (
        pip_version is None or pip_version < (23, 0) or not _has_packaging_toolchain()
    )
    ok = True
    if needs_upgrade:
        ok = _upgrade_packaging_toolchain()
    if ok:
        pip_ready_event.set()
    return ok


def system_python_install_hint(reason: str) -> str:
    """Return platform-specific instructions for creating the dependency venv."""
    version_range = _supported_system_python_range_label()
    lines = [
        reason,
        "",
        tr("请安装带 venv/pip 支持的 Python（{version_range}）后重试。").format(
            version_range=version_range
        ),
    ]
    if os.name == "nt":
        lines.extend(
            [
                tr(
                    "  python.org：安装 Python 3.10-3.13，并勾选 Add python.exe to PATH"
                ),
                "  winget：    winget install Python.Python.3.11",
                tr("  安装后请重新打开 LaTeXSnipper，再点击下载/安装。"),
            ]
        )
    elif sys.platform == "darwin":
        lines.extend(
            [
                "  Homebrew：brew install python",
                tr("  python.org：安装最新版 macOS Python 3 安装包"),
                tr("  安装后请重新打开 LaTeXSnipper。"),
            ]
        )
    else:
        lines.extend(
            [
                "  Debian/Ubuntu：sudo apt install python3 python3-venv",
                "  Fedora：        sudo dnf install python3",
                "  Arch：          sudo pacman -S python",
            ]
        )
    return "\n".join(lines)


def system_python_unavailable_text() -> str:
    issue = _system_python_unavailable()
    values = {
        "version": issue.version,
        "path": issue.path,
        "version_range": issue.version_range,
    }
    if issue.code == "missing_venv":
        source = tr(
            "检测到系统 Python {version}（{path}），版本位于支持范围 "
            "{version_range} 内，但缺少 venv/ensurepip，无法创建依赖环境。"
        )
    elif issue.code == "unsupported_version":
        source = tr(
            "检测到系统 Python {version}（{path}），但版本不在支持范围 "
            "{version_range} 内，无法创建依赖环境。"
        )
    else:
        source = tr(
            "未检测到可运行的系统 Python；需要 Python {version_range} "
            "并提供 venv/ensurepip。"
        )
    return source.format(**values)


def install_failure_dialog_copy() -> tuple[str, str]:
    return (
        tr("依赖安装未完成"),
        tr("部分依赖安装失败，请查看日志后重试。"),
    )


def install_failure_log_line() -> str:
    return "\n[ERR] 依赖安装未完成，请查看日志后重试"


def create_dependency_venv(
    target_dir: Path,
    timeout: int = 300,
    log_fn=print,
    stop_event: threading.Event | None = None,
    proc_setter=None,
) -> tuple[bool, str]:
    """Create a Python venv at target_dir using a supported system Python."""

    system_python = _find_system_python3()
    if system_python is None:
        reason = system_python_unavailable_text()
        log_fn(f"[ERR] {reason}")
        return False, reason

    target_dir.mkdir(parents=True, exist_ok=True)
    log_fn(f"[INFO] 使用系统 Python 创建 venv: {system_python} -> {target_dir}")
    proc = None
    try:
        cmd = [str(system_python), "-m", "venv", "--copies", str(target_dir)]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **hidden_subprocess_kwargs(),
        )
        if proc_setter is not None:
            proc_setter(proc)
        deadline = time.monotonic() + timeout
        while True:
            if stop_event is not None and stop_event.is_set():
                _terminate_process(proc)
                log_fn("[INFO] 用户取消虚拟环境初始化。")
                return False, tr("Python 依赖环境初始化已取消")
            ret = proc.poll()
            if ret is not None:
                break
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(cmd, timeout)
            time.sleep(0.2)
        output = proc.stdout.read() if proc.stdout else ""
        if ret == 0:
            log_fn(f"[INFO] Python 依赖环境创建成功: {target_dir}")
            return True, ""
        detail = output[-500:].strip()
        reason = tr("系统 Python {python} 创建 venv 失败").format(python=system_python)
        log_fn(f"[WARN] {reason}: {detail}")
        return False, reason
    except subprocess.TimeoutExpired:
        log_fn(f"[WARN] venv 创建超时（{timeout} 秒）")
        try:
            if proc is not None:
                _terminate_process(proc)
        except Exception:
            pass
        return False, tr("venv 创建超时（{timeout} 秒）").format(timeout=timeout)
    except Exception as e:
        log_fn(f"[WARN] venv 创建异常: {e}")
        return False, tr("venv 创建异常: {error}").format(error=e)
    finally:
        if proc_setter is not None:
            proc_setter(None)


class PythonVenvInitWorker(QThread):
    log_updated = pyqtSignal(str)
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    done = pyqtSignal(bool, str)

    def __init__(self, target_dir: Path, pyexe: Path, stop_event: threading.Event):
        super().__init__()
        self.target_dir = Path(target_dir)
        self.pyexe = Path(pyexe)
        self.stop_event = stop_event
        self.proc = None

    def stop(self) -> None:
        self.stop_event.set()
        if self.proc is not None and self.proc.poll() is None:
            _terminate_process(self.proc)
            self.proc = None

    def run(self) -> None:
        try:
            self.status_updated.emit(tr("正在初始化 Python 依赖环境..."))
            self.progress_updated.emit(5)
            ok, error = create_dependency_venv(
                self.target_dir,
                log_fn=self.log_updated.emit,
                stop_event=self.stop_event,
                proc_setter=lambda proc: setattr(self, "proc", proc),
            )
            if not ok or self.stop_event.is_set():
                self.done.emit(False, error or tr("Python 依赖环境初始化已取消"))
                return
            self.progress_updated.emit(25)
            self.status_updated.emit(tr("正在初始化 pip 工具链..."))
            if not ensure_pip(self.pyexe):
                self.done.emit(False, tr("无法初始化 pip"))
                return
            self.progress_updated.emit(30)
            self.done.emit(True, "")
        except Exception as e:
            self.log_updated.emit(f"[ERR] 初始化 Python 依赖环境失败: {e}")
            self.done.emit(False, str(e))
