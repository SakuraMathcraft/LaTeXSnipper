from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest
from latexsnipper_office import install, lifecycle, sideload


class Recorder:
    """Stands in for launchctl, the keychain and the certificate tools."""

    def __init__(self, monkeypatch, *, loaded: bool = False) -> None:
        self.calls: list[tuple] = []
        self.loaded = loaded

        def launchctl(*arguments, check=True):
            self.calls.append(("launchctl", *arguments))
            if arguments[0] == "bootstrap":
                self.loaded = True
            if arguments[0] == "bootout":
                self.loaded = False
            code = 0 if arguments[0] != "print" or self.loaded else 113
            return type("Done", (), {"returncode": code})()

        monkeypatch.setattr(install, "_launchctl", launchctl)
        monkeypatch.setattr(
            install,
            "prepare_certificate",
            lambda state, interactive: self.calls.append(("trust", interactive)),
        )
        monkeypatch.setattr(
            install.certificate,
            "untrust",
            lambda identity: self.calls.append(("untrust",)),
        )


def test_install_registers_a_login_agent_that_runs_the_host(monkeypatch, tmp_path):
    recorder = Recorder(monkeypatch)
    install.install(state=tmp_path / "state", home=tmp_path)
    plist = install.agent_path(tmp_path)
    with plist.open("rb") as stream:
        agent = plistlib.load(stream)
    assert agent["Label"] == install.AGENT_LABEL
    assert agent["ProgramArguments"][-1] == "--serve"
    assert agent["RunAtLoad"] is True
    # Restarted after a crash, not after a deliberate clean exit.
    assert agent["KeepAlive"] == {"SuccessfulExit": False}
    assert agent["StandardErrorPath"].startswith(str(tmp_path / "state"))
    assert ("trust", True) in recorder.calls
    assert recorder.calls[-1][:2] == ("launchctl", "bootstrap")
    assert (tmp_path / "state").stat().st_mode & 0o777 == 0o700


def test_source_installs_point_launchd_at_the_package(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    command = install.host_command()
    assert command[1:] == ["-m", "latexsnipper_office", "--serve"]
    agent = install.agent_definition(command, tmp_path)
    assert Path(
        agent["EnvironmentVariables"]["PYTHONPATH"], "latexsnipper_office"
    ).is_dir()


def test_reinstall_replaces_the_running_agent(monkeypatch, tmp_path):
    recorder = Recorder(monkeypatch, loaded=True)
    install.install(state=tmp_path / "state", home=tmp_path)
    verbs = [call[1] for call in recorder.calls if call[0] == "launchctl"]
    assert verbs.index("bootout") < verbs.index("bootstrap")


def test_uninstall_removes_everything_the_add_in_created(monkeypatch, tmp_path):
    recorder = Recorder(monkeypatch, loaded=True)
    state = tmp_path / "state"
    state.mkdir()
    (state / "settings.json").write_text("{}", encoding="utf-8")
    install.agent_path(tmp_path).parent.mkdir(parents=True)
    install.agent_path(tmp_path).write_bytes(b"")
    sideload.install_manifest("<OfficeApp/>", home=tmp_path)
    desktop_data = tmp_path / "Library/Application Support/LaTeXSnipper/history.json"
    desktop_data.parent.mkdir(parents=True)
    desktop_data.write_text("[]", encoding="utf-8")

    install.uninstall(state=state, home=tmp_path)

    assert not install.agent_path(tmp_path).exists()
    assert sideload.installed_hosts(tmp_path) == []
    assert not state.exists()
    assert ("untrust",) in recorder.calls
    assert not recorder.loaded
    assert desktop_data.is_file(), "the desktop app's data must be left alone"


def test_login_start_never_prompts_for_trust(monkeypatch, tmp_path):
    monkeypatch.setattr(
        lifecycle.certificate, "ensure_certificate", lambda state: (object(), True)
    )
    monkeypatch.setattr(lifecycle.certificate, "is_trusted", lambda identity: False)
    prompted = []
    monkeypatch.setattr(
        lifecycle.certificate, "trust", lambda identity: prompted.append(identity)
    )
    with pytest.raises(lifecycle.CertificateNotTrusted):
        lifecycle.prepare_certificate(tmp_path, interactive=False)
    assert prompted == []
