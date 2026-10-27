"""Exercise installed GUI handoff, replacement and automatic restart in release CI."""

from __future__ import annotations

import os
import py_compile
import re
import shutil
import subprocess
import time
import zipfile
from dataclasses import replace
from pathlib import Path

import psutil

from runtime.app_paths import CONFIG_FILENAME
from runtime.component_inventory import file_sha256, inventory_component
from runtime.content_types import FORMULA_CONTENT_TYPE
from runtime.distribution_manifest import DistributionManifest, ManifestError, read_json
from runtime.installation_layout import (
    deployment_write_root,
    installation_manifest,
    macos_bundle,
)
from runtime.installed_resources import InstalledResources
from runtime.processes import hidden_subprocess_kwargs
from update.deployment_transaction import atomic_json, verify_distribution
from update.deployment_validation import validate_installed_worker
from update.platform_deployment import deployment_transaction


def prepare_fixture(root: Path, target: DistributionManifest, work: Path) -> None:
    staged = work / "update-predecessor"
    application = staged / "application"
    shutil.copytree(root / "application", application)
    archive = application / "application.pyz"
    # The driver exists only in this predecessor; the target is the unmodified release.
    with zipfile.ZipFile(archive) as original:
        entries = {info.filename: original.read(info) for info in original.infolist()}
    entries["acceptance_application.pyc"] = entries.pop("main.pyc")
    wrapper = work / "main.py"
    wrapper.write_text(
        "import acceptance_application as application\n"
        "from acceptance_driver import start\n"
        "application.bootstrap_application()\n"
        f"start({str(work / 'driver.json')!r}, {target.release_tag!r})\n"
        "raise SystemExit(application.main())\n",
        encoding="utf-8",
    )
    for name, source in (
        ("main.pyc", wrapper),
        (
            "acceptance_driver.pyc",
            Path(__file__).with_name("installed_update_driver.py"),
        ),
    ):
        compiled = work / name
        py_compile.compile(str(source), cfile=str(compiled), dfile=name, doraise=True)
        entries[name] = compiled.read_bytes()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, contents in entries.items():
            output.writestr(name, contents)
    predecessor = replace(
        target,
        application=replace(target.application, files=inventory_component(application)),
    )
    atomic_json(staged / "distribution.json", predecessor.to_dict())
    deployment_transaction(root).apply(staged, validate=validate_installed_worker)


def validate_running_update(
    root: Path, target: DistributionManifest, work: Path, diagnostics: Path
) -> dict:
    prepare_fixture(root, target, work)
    home = work / "home"
    home.mkdir()
    state = (
        home / "Library/Application Support/LaTeXSnipper"
        if target.platform == "macos"
        else home / ".latexsnipper"
    )
    logs = (
        home / "Library/Logs/LaTeXSnipper"
        if target.platform == "macos"
        else state / "logs"
    )
    state.mkdir(parents=True)
    atomic_json(
        state / CONFIG_FILENAME,
        {
            "onboarding_auto_show": False,
            "mathcraft_warmup_notice_done": True,
            "theme_mode": "dark",
        },
    )
    history = {
        "history": ["x^2+1"],
        "formula_names": {"x^2+1": "验收公式"},
        "formula_types": {"x^2+1": FORMULA_CONTENT_TYPE},
    }
    atomic_json(state / "history.json", history)
    environment = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --no-sandbox",
    }
    executable = "LaTeXSnipper.exe" if target.platform == "windows" else "LaTeXSnipper"
    retained = InstalledResources(root, target).resource("inference", "runtime.json")
    runtime_hash = file_sha256(retained)
    launcher = subprocess.Popen(
        [str(root / executable)],
        cwd=deployment_write_root(root, target.platform),
        env=environment,
        **hidden_subprocess_kwargs(),
    )
    started = time.monotonic()
    report: dict = {}
    old_exited = None
    try:
        while time.monotonic() - started < 600:
            launcher.poll()  # Reap the launcher even when it exits before the GUI.
            driver = work / "driver.json"
            if driver.is_file():
                report = read_json(driver)
            if report.get("error"):
                raise ManifestError(report["error"])
            if report.get("request"):
                outcome = Path(report["request"]).with_name("deployment-result.json")
                try:
                    result = read_json(outcome)
                except FileNotFoundError:
                    result = {}
                if result.get("state") in {"failed", "rolled-back"}:
                    raise ManifestError(f"Installed update failed: {result}")
            handoff = report.get("states", {}).get("handoff-ready")
            if handoff is not None:
                old_alive = psutil.pid_exists(report["pid"])
                if not old_alive and old_exited is None:
                    old_exited = time.monotonic()
                if old_alive and time.monotonic() - handoff > 30:
                    raise ManifestError("Update handoff did not exit the original GUI")
            log = logs / "app.log"
            text = log.read_text(encoding="utf-8") if log.is_file() else ""
            # A committed outcome is logged only by the automatically restarted GUI.
            if "独立部署结果 state=committed" in text:
                pids = re.findall(r"LaTeXSnipper 启动 pid=(\d+)", text)
                if len(pids) < 2 or int(pids[-1]) == report.get("pid"):
                    raise ManifestError("Update did not restart a distinct GUI process")
                restarted = psutil.Process(int(pids[-1]))
                if not restarted.is_running() or old_exited is None or handoff is None:
                    raise ManifestError("The expected GUI process transition failed")
                if not report.get("update_window_visible"):
                    raise ManifestError(
                        "Update handoff was not exercised from a visible window"
                    )
                installed = DistributionManifest.load(
                    installation_manifest(root, target.platform)
                )
                if installed != target.installed_identity():
                    raise ManifestError(
                        "Installed update identity differs from the release"
                    )
                verify_distribution(root, target)
                validate_installed_worker(root, target)
                if file_sha256(retained) != runtime_hash:
                    raise ManifestError("Business update changed the inference runtime")
                for path, contents in report["user_files"].items():
                    if read_json(Path(path)) != contents:
                        raise ManifestError(
                            f"Business update changed user data: {path}"
                        )
                if read_json(state / "history.json") != history:
                    raise ManifestError(
                        "Business update did not preserve recognition history"
                    )
                return {
                    "original_pid": report["pid"],
                    "restarted_pid": restarted.pid,
                    "exit_seconds": round(old_exited - handoff, 2),
                    "total_seconds": round(time.monotonic() - started, 2),
                    "states": report["states"],
                    "committed": True,
                    "user_data_preserved": True,
                    "base_preserved": True,
                }
            time.sleep(0.2)
        raise TimeoutError(
            "Installed GUI update and restart did not finish within 600 seconds"
        )
    finally:
        diagnostics.mkdir(parents=True, exist_ok=True)
        atomic_json(diagnostics / "driver.json", report)
        atomic_json(
            diagnostics / "user-data-after.json",
            {str(path): read_json(path) for path in state.glob("*.json")},
        )
        if report.get("request"):
            task = Path(report["request"]).parent
            for name in ("request.json", "deployment-result.json"):
                try:
                    shutil.copy2(task / name, diagnostics / name)
                except FileNotFoundError:
                    pass  # The restarted GUI may already have reclaimed this task.
        if logs.is_dir():
            shutil.copytree(logs, diagnostics / "logs", dirs_exist_ok=True)
        # Stop only processes belonging to this isolated installation or its task cache.
        owned = []
        owner = macos_bundle(root) if target.platform == "macos" else root
        for process in psutil.process_iter(["exe"]):
            try:
                path = (
                    Path(process.info["exe"]).resolve() if process.info["exe"] else None
                )
                if path is not None and (
                    path.is_relative_to(owner) or path.is_relative_to(home)
                ):
                    owned.append(process)
                    process.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        _, alive = psutil.wait_procs(owned, timeout=10)
        for process in alive:
            process.kill()
        psutil.wait_procs(alive, timeout=10)
        launcher.wait(timeout=10)
