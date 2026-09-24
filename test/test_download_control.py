import subprocess
import sys
import threading
import time

from bootstrap.download_control import DownloadControl, wait_for_download


def test_pause_stops_running_process_and_resume_continues(tmp_path):
    heartbeat = tmp_path / "heartbeat"
    code = (
        "import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); "
        + "\nwhile True:\n p.write_text(str(time.monotonic()))\n time.sleep(0.02)"
    )
    proc = subprocess.Popen([sys.executable, "-c", code, str(heartbeat)])
    gate = threading.Event()
    gate.set()
    control = DownloadControl(gate)
    control.set_process(proc)
    try:
        deadline = time.monotonic() + 5
        while not heartbeat.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert heartbeat.exists()
        control.set_paused(True)
        before = heartbeat.read_bytes()
        time.sleep(0.15)
        assert heartbeat.read_bytes() == before
        control.set_paused(False)
        deadline = time.monotonic() + 5
        while heartbeat.read_bytes() == before and time.monotonic() < deadline:
            time.sleep(0.02)
        assert heartbeat.read_bytes() != before
    finally:
        control.set_paused(False)
        proc.terminate()
        proc.wait(timeout=5)
        control.set_process(None)


def test_cooperative_pause_can_resume_or_cancel():
    gate, stop, done = threading.Event(), threading.Event(), threading.Event()
    result = []

    def run():
        result.append(wait_for_download(gate, stop))
        done.set()

    thread = threading.Thread(target=run)
    thread.start()
    assert not done.wait(0.05)
    gate.set()
    assert done.wait(1)
    thread.join()
    assert result == [True]
    gate.clear()
    stop.set()
    assert wait_for_download(gate, stop) is False


def test_exit_confirmation_keeps_task_until_confirmed(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from bootstrap.progress_dialog import InstallProgressDialog

    app = QApplication.instance() or QApplication([])
    dialog = InstallProgressDialog()
    dialog.confirm_cancel = True
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
    )
    assert dialog.confirm_exit() is False
    assert dialog.confirm_cancel
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    assert dialog.confirm_exit() is True
    assert dialog.confirm_exit() is True
    dialog.close()
    app.processEvents()
