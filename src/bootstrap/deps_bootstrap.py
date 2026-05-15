# pyright: reportUnusedImport=false

"""Compatibility facade for the dependency bootstrap package.

The implementation is intentionally split across focused modules. Keep new logic out
of this file so old imports continue to work without rebuilding the monolith.
"""

# ruff: noqa: F401

from bootstrap.deps_context import (
    CONFIG_FILE,
    PIP_INSTALL_SUPPRESS_ARGS,
    STATE_FILE,
    _config_dir_path,
    _hidden_subprocess_kwargs,
    flags,
    pip_ready_event,
    psutil,
    safe_run,
    subprocess_lock,
    was_last_ensure_deps_force_enter,
)
from bootstrap.deps_entry import (
    _ensure_pip,
    _find_local_python311_installer,
    _load_config_path,
    _read_config_install_dir,
    _run_local_python311_installer,
    _setup_python_venv_from_system,
    _system_python_install_hint,
    _write_config_install_dir,
    clear_deps_state,
    ensure_deps,
)
from bootstrap.deps_layer_specs import (
    LAYER_MAP,
    MATHCRAFT_RUNTIME_LAYERS,
    ORT_CPU_SPEC,
    ORT_GPU_DEFAULT_SPEC,
    _cuda_toolkit_available,
    _diagnose_install_failure,
    _filter_packages,
    _gpu_available,
    _normalize_chosen_layers,
    _reorder_mathcraft_install_specs,
    _sanitize_state_layers,
    _split_spec_name,
    _version_satisfies_spec,
)
from bootstrap.deps_pandoc import (
    _PANDOC_VERSION,
    _build_pandoc_mirrors,
    _cleanup_pandoc_leftovers,
    _download_pandoc_from_mirrors,
    _ensure_pandoc_binary,
    _extract_pandoc_binary,
    _get_pandoc_version,
    _pandoc_data_dir,
    _pandoc_platform_archive,
    _pandoc_version_too_old,
    _rank_mirrors_by_speed,
)
from bootstrap.deps_runtime_verify import (
    CRITICAL_VERSIONS,
    LAYER_VERIFY_CODE,
    RUNTIME_IMPORT_CHECKS,
    _CORE_VERIFY_CODE,
    _current_installed,
    _fix_critical_versions,
    _force_repair_broken_runtime_imports,
    _layer_verify_failure_diagnostics,
    _onnxruntime_session_verify_code,
    _pip_install,
    _repair_gpu_onnxruntime_runtime,
    _uninstall_package_if_present,
    _verify_installed_layers,
    _verify_layer_runtime,
    _verify_onnxruntime_runtime,
    _verify_runtime_support_imports,
)
from bootstrap.deps_ui import (
    _apply_app_window_icon,
    _apply_close_only_window_flags,
    _build_layers_ui,
    _deps_dialog_theme,
    _exec_close_only_message_box,
    _progress_dialog,
    _select_existing_directory_with_icon,
    _sync_deps_fluent_theme,
    custom_warning_dialog,
)
from bootstrap.deps_workers import InstallWorker, LayerVerifyWorker, UninstallLayerWorker
from bootstrap.deps_python_runtime import site_packages_root as _site_packages_root
import bootstrap.deps_runtime_verify as _runtime_verify


def _cleanup_pip_interrupted_leftovers(pyexe, log_fn=None):
    original_site_packages_root = _runtime_verify._site_packages_root
    _runtime_verify._site_packages_root = globals().get("_site_packages_root", original_site_packages_root)
    try:
        return _runtime_verify._cleanup_pip_interrupted_leftovers(pyexe, log_fn=log_fn)
    finally:
        _runtime_verify._site_packages_root = original_site_packages_root


def _cleanup_orphan_onnxruntime_namespace(pyexe, installed_map=None, log_fn=None):
    original_current_installed = _runtime_verify._current_installed
    original_site_packages_root = _runtime_verify._site_packages_root
    _runtime_verify._current_installed = globals().get("_current_installed", original_current_installed)
    _runtime_verify._site_packages_root = globals().get("_site_packages_root", original_site_packages_root)
    try:
        return _runtime_verify._cleanup_orphan_onnxruntime_namespace(pyexe, installed_map=installed_map, log_fn=log_fn)
    finally:
        _runtime_verify._current_installed = original_current_installed
        _runtime_verify._site_packages_root = original_site_packages_root
