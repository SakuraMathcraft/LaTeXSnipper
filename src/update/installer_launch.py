import json
import os
import subprocess
import tempfile
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from update.dialog_helpers import _hidden_subprocess_kwargs


def _schedule_windows_installer(path: str) -> None:
    installer = str(Path(path).resolve())
    script = Path(tempfile.gettempdir()) / f"latexsnipper-install-{os.getpid()}.vbs"
    script.write_text(
        "\n".join([
            'Set shell = CreateObject("WScript.Shell")',
            'Set fso = CreateObject("Scripting.FileSystemObject")',
            f'installer = "{installer.replace(chr(34), chr(34) * 2)}"',
            f'waitPid = "{os.getpid()}"',
            "Do",
            '  Set execObj = shell.Exec("cmd /c tasklist /FI ""PID eq " & waitPid & """ /NH")',
            "  output = LCase(execObj.StdOut.ReadAll())",
            '  If InStr(output, "no tasks are running") > 0 Or InStr(output, LCase(waitPid)) = 0 Then Exit Do',
            "  WScript.Sleep 1000",
            "Loop",
            'shell.Run Chr(34) & installer & Chr(34), 1, False',
            'On Error Resume Next',
            'fso.DeleteFile WScript.ScriptFullName, True',
        ]),
        encoding="utf-8",
    )
    subprocess.Popen(
        ["wscript.exe", "//B", "//NoLogo", str(script)],
        close_fds=True,
        **_hidden_subprocess_kwargs(),
    )


def _prepare_app_for_update_exit() -> None:
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        try:
            prepare_restart = getattr(widget, "prepare_restart", None)
            if callable(prepare_restart):
                prepare_restart()
                break
        except Exception:
            continue



def _read_signature_status(path: str) -> str:
    ext = Path(path).suffix.lower()
    if os.name != "nt" or ext not in (".exe", ".msi"):
        return "未校验（非 Windows 安装器）"
    try:
        escaped_path = path.replace("'", "''")
        cmd = (
            "Get-AuthenticodeSignature -FilePath "
            f"'{escaped_path}' | "
            "Select-Object Status,SignerCertificate | ConvertTo-Json -Compress"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=20,
            encoding="utf-8",
            errors="replace",
            **_hidden_subprocess_kwargs(),
        )
        raw = (proc.stdout or "").strip()
        if not raw:
            return "未校验（无签名信息）"
        obj = json.loads(raw)
        status = str(obj.get("Status", "") or "Unknown")
        cert = obj.get("SignerCertificate") or {}
        subject = str(cert.get("Subject", "") or "").strip()
        if subject:
            return f"{status} / {subject}"
        return status
    except Exception as e:
        return f"未校验（{e}）"
