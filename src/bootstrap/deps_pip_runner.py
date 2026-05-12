"""Reusable pip command runner helpers for dependency bootstrap."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import traceback
from contextlib import nullcontext
from pathlib import Path
from typing import Callable

_safe_run: Callable | None = None
_subprocess_lock = None
_suppress_args: list[str] = ["--no-warn-script-location"]


def configure_pip_runner(*, safe_run: Callable, subprocess_lock, suppress_args: list[str]) -> None:
    global _safe_run, _subprocess_lock, _suppress_args
    _safe_run = safe_run
    _subprocess_lock = subprocess_lock
    _suppress_args = list(suppress_args or [])


def _lock_context(lock=None):
    effective_lock = lock if lock is not None else _subprocess_lock
    return effective_lock if effective_lock is not None else nullcontext()


def _effective_safe_run(safe_run: Callable | None = None) -> Callable | None:
    return safe_run if safe_run is not None else _safe_run


def _pip_env(pyexe) -> dict:
    env = os.environ.copy()
    main_site = Path(pyexe).parent / "Lib" / "site-packages"
    if main_site.exists():
        env["PYTHONPATH"] = f"{main_site};{env.get('PYTHONPATH', '')}"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _hidden_startupinfo():
    if os.name != "nt":
        return None
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return startupinfo
    except Exception:
        return None


def _spawn_process(args, *, env: dict, flags=0, safe_run: Callable | None = None, subprocess_lock=None):
    runner = _effective_safe_run(safe_run)
    startupinfo = _hidden_startupinfo()
    with _lock_context(subprocess_lock):
        if runner is not None:
            kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "bufsize": 1,
                "encoding": "utf-8",
                "env": env,
                "creationflags": flags,
            }
            if startupinfo is not None:
                kwargs["startupinfo"] = startupinfo
            return runner(args, **kwargs)
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
            "encoding": "utf-8",
            "env": env,
            "creationflags": flags,
        }
        if startupinfo is not None:
            kwargs["startupinfo"] = startupinfo
        return subprocess.Popen(args, **kwargs)


def _set_proc(proc_setter, proc) -> None:
    if proc_setter is None:
        return
    try:
        proc_setter(proc)
    except Exception:
        pass


def _terminate_process(proc) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run_logged_pip_command(
    pyexe,
    pip_args,
    stop_event,
    log_q,
    flags=0,
    use_mirror=False,
    proc_setter=None,
    timeout=1200,
    safe_run: Callable | None = None,
    subprocess_lock=None,
):
    proc = None
    output_lines = []
    args = [str(pyexe), "-m", "pip", *pip_args]
    args += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple" if use_mirror else "https://pypi.org/simple"]

    log_q.put(f"[CMD] {' '.join(args)}")
    try:
        proc = _spawn_process(
            args,
            env=_pip_env(pyexe),
            flags=flags,
            safe_run=safe_run,
            subprocess_lock=subprocess_lock,
        )
        _set_proc(proc_setter, proc)

        for line in proc.stdout:
            if stop_event.is_set():
                log_q.put("[CANCEL] Cancel requested, terminating pip process...")
                _terminate_process(proc)
                return False, "\n".join(output_lines)
            text = line.rstrip()
            log_q.put(text)
            output_lines.append(text)
        proc.communicate(timeout=timeout)
        return proc.returncode == 0, "\n".join(output_lines)
    except subprocess.TimeoutExpired:
        log_q.put("[WARN] pip recovery command timed out")
        if proc is not None:
            _terminate_process(proc)
        return False, "\n".join(output_lines)
    except Exception as exc:
        log_q.put(f"[WARN] pip recovery command failed: {exc}")
        return False, "\n".join(output_lines)
    finally:
        _set_proc(proc_setter, None)


def maybe_recover_antlr_wheel_failure(
    pyexe,
    pkg,
    output: str,
    stop_event,
    log_q,
    use_mirror=False,
    flags=0,
    proc_setter=None,
    suppress_args: list[str] | None = None,
    safe_run: Callable | None = None,
    subprocess_lock=None,
) -> bool:
    lower = str(output or "").lower()
    pkg_lower = re.split(r"[<>=!~ ]", str(pkg or ""), 1)[0].strip().lower()
    if pkg_lower not in {"rapidocr", "omegaconf", "antlr4-python3-runtime"}:
        return False
    if "antlr4-python3-runtime" not in lower:
        return False
    if "bdist_wheel" not in lower and "metadata-generation-failed" not in lower:
        return False

    suppress = list(_suppress_args if suppress_args is None else suppress_args)
    log_q.put("[INFO] antlr4-python3-runtime build failed; repairing pip/setuptools/wheel...")

    ok_tools, _ = run_logged_pip_command(
        pyexe,
        ["install", "--upgrade", "pip", "setuptools", "wheel", "--no-cache-dir", *suppress],
        stop_event,
        log_q,
        flags=flags,
        use_mirror=use_mirror,
        proc_setter=proc_setter,
        timeout=900,
        safe_run=safe_run,
        subprocess_lock=subprocess_lock,
    )
    if not ok_tools:
        log_q.put("[WARN] pip/setuptools/wheel repair failed; antlr recovery cannot continue.")
        return False

    ok_antlr, _ = run_logged_pip_command(
        pyexe,
        ["install", "antlr4-python3-runtime==4.9.3", "--no-build-isolation", *suppress],
        stop_event,
        log_q,
        flags=flags,
        use_mirror=use_mirror,
        proc_setter=proc_setter,
        timeout=900,
        safe_run=safe_run,
        subprocess_lock=subprocess_lock,
    )
    if not ok_antlr:
        log_q.put("[WARN] Preinstalling antlr4-python3-runtime==4.9.3 failed.")
        return False

    log_q.put("[OK] antlr4-python3-runtime recovery completed; retrying current package.")
    return True


class PipInstallRunner:
    """Stateful pip install runner with injectable policy and process hooks."""

    def __init__(
        self,
        *,
        pyexe,
        pkg,
        stop_event,
        log_q,
        use_mirror=False,
        flags=0,
        pause_event=None,
        force_reinstall=False,
        no_cache=False,
        proc_setter=None,
        pip_ready_event=None,
        suppress_args: list[str] | None = None,
        safe_run: Callable | None = None,
        subprocess_lock=None,
        onnxruntime_gpu_policy: Callable | None = None,
        cleanup_orphan_onnxruntime_namespace: Callable | None = None,
        diagnose_install_failure: Callable | None = None,
    ):
        self.pyexe = pyexe
        self.pkg = pkg
        self.stop_event = stop_event
        self.log_q = log_q
        self.use_mirror = use_mirror
        self.flags = flags
        self.pause_event = pause_event
        self.force_reinstall = force_reinstall
        self.no_cache = no_cache
        self.proc_setter = proc_setter
        self.pip_ready_event = pip_ready_event
        self.suppress_args = list(suppress_args or _suppress_args)
        self.safe_run = _effective_safe_run(safe_run)
        self.subprocess_lock = subprocess_lock if subprocess_lock is not None else _subprocess_lock
        self.onnxruntime_gpu_policy = onnxruntime_gpu_policy
        self.cleanup_orphan_onnxruntime_namespace = cleanup_orphan_onnxruntime_namespace
        self.diagnose_install_failure = diagnose_install_failure

    @staticmethod
    def _root_name(spec: str) -> str:
        return re.split(r"[<>=!~ ]", spec, 1)[0].strip().lower()

    def _set_proc(self, proc) -> None:
        _set_proc(self.proc_setter, proc)

    def _wait_if_paused(self) -> bool:
        if self.pause_event is None or self.pause_event.is_set():
            return True
        self.log_q.put("[INFO] Paused; waiting to resume...")
        while not self.pause_event.is_set():
            if self.stop_event.is_set():
                self.log_q.put("[CANCEL] Cancel requested.")
                return False
            time.sleep(0.1)
        return True

    def _diagnose_failure(self, output: str, returncode: int) -> str:
        if callable(self.diagnose_install_failure):
            return self.diagnose_install_failure(output, returncode)
        return f"Unknown error (code={returncode}); see pip log above."

    def _build_manual_command(self, pyexe, pkg, name, ort_gpu_policy) -> str:
        manual_cmd = f'"{pyexe}" -m pip install "{pkg}" --upgrade --user'
        if name in {"onnxruntime", "onnxruntime-gpu"}:
            manual_cmd += " --no-deps"
        if ort_gpu_policy is not None and ort_gpu_policy.pre:
            manual_cmd += " --pre"
        if ort_gpu_policy is not None and ort_gpu_policy.index_url:
            manual_cmd += f" -i {ort_gpu_policy.index_url}"
        return manual_cmd

    def _build_install_args(self, pyexe, pkg, name, retry, ort_gpu_policy) -> list[str]:
        args = [str(pyexe), "-m", "pip", "install", pkg, "--upgrade", *self.suppress_args]
        if retry == 0 and ort_gpu_policy is not None:
            self.log_q.put(
                "[INFO] onnxruntime-gpu policy: "
                f"CUDA {ort_gpu_policy.cuda.version_text} -> {ort_gpu_policy.requirement} "
                f"({ort_gpu_policy.source_label})"
            )
            if ort_gpu_policy.warning:
                self.log_q.put(f"[WARN] {ort_gpu_policy.warning}")
        if ort_gpu_policy is not None and ort_gpu_policy.pre:
            args.append("--pre")

        if self.force_reinstall:
            args.append("--force-reinstall")
            if self.no_cache:
                args.append("--no-cache-dir")
        elif name in {"protobuf"}:
            args.append("--force-reinstall")

        if name in {"onnxruntime", "onnxruntime-gpu"}:
            args.append("--no-deps")

        if ort_gpu_policy is not None and ort_gpu_policy.index_url:
            args += ["-i", ort_gpu_policy.index_url]
            if retry == 0:
                self.log_q.put(f"[Source] {ort_gpu_policy.source_label}")
        elif self.use_mirror:
            args += ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
            if retry == 0:
                self.log_q.put("[Source] Using Tsinghua PyPI mirror")
        else:
            args += ["-i", "https://pypi.org/simple"]
            if retry == 0:
                self.log_q.put("[Source] Using official PyPI")
        return args

    def _recover_antlr_if_needed(self, pyexe, pkg, output: str) -> bool:
        return maybe_recover_antlr_wheel_failure(
            pyexe,
            pkg,
            output,
            self.stop_event,
            self.log_q,
            use_mirror=self.use_mirror,
            flags=self.flags,
            proc_setter=self.proc_setter,
            suppress_args=self.suppress_args,
            safe_run=self.safe_run,
            subprocess_lock=self.subprocess_lock,
        )

    def install(self) -> bool:
        max_retries = 2
        retry = 0
        antlr_recovery_applied = False
        pyexe = self.pyexe
        pkg = self.pkg

        if not Path(pyexe).exists():
            pyexe = Path(sys.executable)
            self.log_q.put(f"[WARN] Python path does not exist; switched to {pyexe}")

        if self.pip_ready_event is not None and not self.pip_ready_event.wait(timeout=60):
            self.log_q.put(f"[ERR] pip is not ready; skipping {pkg}")
            return False

        name = self._root_name(pkg)
        ort_gpu_policy = None
        if name == "onnxruntime-gpu" and callable(self.onnxruntime_gpu_policy):
            ort_gpu_policy = self.onnxruntime_gpu_policy(pyexe)
            pkg = ort_gpu_policy.requirement
            name = self._root_name(pkg)
        if name in {"onnxruntime", "onnxruntime-gpu"} and callable(self.cleanup_orphan_onnxruntime_namespace):
            self.cleanup_orphan_onnxruntime_namespace(pyexe, log_fn=self.log_q.put)

        env = _pip_env(pyexe)
        while retry <= max_retries:
            if self.stop_event.is_set():
                self.log_q.put("[INFO] Stop signal received; aborting install.")
                return False
            if not self._wait_if_paused():
                return False

            proc = None
            try:
                args = self._build_install_args(pyexe, pkg, name, retry, ort_gpu_policy)
                self.log_q.put(f"[CMD] {' '.join(args)}")
                proc = _spawn_process(
                    args,
                    env=env,
                    flags=self.flags,
                    safe_run=self.safe_run,
                    subprocess_lock=self.subprocess_lock,
                )
                self._set_proc(proc)

                output_lines = []
                for line in proc.stdout:
                    if self.stop_event.is_set():
                        self.log_q.put("[CANCEL] Cancel requested, terminating pip process...")
                        _terminate_process(proc)
                        return False
                    if self.pause_event is not None:
                        while not self.pause_event.is_set():
                            if self.stop_event.is_set():
                                _terminate_process(proc)
                                return False
                            time.sleep(0.1)
                    text = line.rstrip()
                    self.log_q.put(text)
                    output_lines.append(text)
                proc.communicate(timeout=1200)

                if proc.returncode == 0:
                    self.log_q.put(f"[OK] {pkg} installed successfully")
                    return True

                if self.stop_event.is_set():
                    self.log_q.put("[CANCEL] Cancel requested.")
                    return False

                full_output = "\n".join(output_lines[-50:])
                failure_reason = self._diagnose_failure(full_output, proc.returncode)
                self.log_q.put(f"[WARN] {pkg} install failed (returncode={proc.returncode})")
                self.log_q.put(f"[DIAG] Possible reason: {failure_reason}")

                if not antlr_recovery_applied:
                    antlr_recovery_applied = self._recover_antlr_if_needed(pyexe, pkg, full_output)
                    if antlr_recovery_applied:
                        self.log_q.put("[INFO] antlr/wheel recovery applied; retrying current package...")
                        time.sleep(1)
                        continue

                retry += 1
                if retry <= max_retries:
                    self.log_q.put(f"[INFO] Retry {retry}...")
                else:
                    self.log_manual_install_hint(pyexe, pkg, name, ort_gpu_policy, failure_reason)
                    return False

                if self.pause_event is not None:
                    while not self.pause_event.is_set():
                        if self.stop_event.is_set():
                            return False
                        time.sleep(0.1)
                time.sleep(3)
            except subprocess.TimeoutExpired:
                self.log_q.put(f"[ERR] {pkg} install timed out; retrying...")
                if proc is not None:
                    _terminate_process(proc)
                retry += 1
            except Exception as exc:
                tb = traceback.format_exc()
                self.log_q.put(f"[FATAL] {pkg} install raised: {exc}\n{tb}")
                return False
            finally:
                self._set_proc(None)

        try:
            kwargs = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "creationflags": self.flags,
            }
            startupinfo = _hidden_startupinfo()
            if startupinfo is not None:
                kwargs["startupinfo"] = startupinfo
            subprocess.check_call(
                [str(pyexe), "-m", "pip", "--version"],
                **kwargs,
            )
        except Exception:
            self.log_q.put(f"[ERR] pip is unavailable; skipping {pkg}")
            return False
        return False

    def log_manual_install_hint(self, pyexe, pkg, name, ort_gpu_policy, failure_reason: str) -> None:
        self.log_q.put(f"[ERR] {pkg} install failed")
        self.log_q.put(f"[ERR] Failure reason: {failure_reason}")
        self.log_q.put("")
        self.log_q.put("=" * 60)
        self.log_q.put("Manual install hint:")
        self.log_q.put("")
        self.log_q.put(f"  {self._build_manual_command(pyexe, pkg, name, ort_gpu_policy)}")
        self.log_q.put("")
        self.log_q.put("If permission errors occur:")
        self.log_q.put("  1. Close the app and run the terminal as administrator")
        self.log_q.put("  2. Or install to the user site with --user")
        self.log_q.put("  3. Or open the environment terminal from settings and run the command above")
        self.log_q.put("=" * 60)
        self.log_q.put("")
