from application import dependency_controller as controller
from ui import startup_splash


def test_dependency_cache_reused_but_settings_checks_again(monkeypatch):
    from bootstrap import deps_entry

    calls = []
    monkeypatch.setattr(controller, "_dependencies_ready", False)
    monkeypatch.setattr(controller, "deps_force_entered", lambda: False)
    monkeypatch.setattr(
        deps_entry, "ensure_deps", lambda *args, **kwargs: calls.append(kwargs) or True
    )
    assert controller.ensure_deps(prompt_ui=False)
    assert controller.ensure_deps(prompt_ui=False)
    assert len(calls) == 1
    assert controller.ensure_deps(prompt_ui=False, from_settings=True)
    assert len(calls) == 2


def test_force_enter_message_consumed_once(monkeypatch):
    monkeypatch.setattr(startup_splash, "_FORCE_ENTERED", False)
    monkeypatch.setattr(startup_splash, "ensure_startup_splash", lambda *args: None)
    monkeypatch.setattr(startup_splash, "take_startup_splash", lambda *args: None)
    startup_splash.mark_startup_force_entered()
    assert startup_splash.startup_force_enter_pending()
    message = startup_splash.startup_deps_resume_message()
    assert not startup_splash.startup_force_enter_pending()
    assert startup_splash.startup_deps_resume_message() != message


def test_cancelled_dependency_startup_exits(monkeypatch, tmp_path):
    import pytest
    from application import bootstrap

    monkeypatch.delenv("LATEXSNIPPER_BOOTSTRAPPED", raising=False)
    monkeypatch.delenv("LATEXSNIPPER_OPEN_DEPENDENCY_MANAGEMENT", raising=False)
    monkeypatch.setattr(bootstrap, "_sanitize_sys_path", lambda *args: None)
    monkeypatch.setattr(bootstrap, "_is_packaged_mode", lambda: False)
    monkeypatch.setattr(bootstrap, "ensure_startup_splash", lambda *args: None)
    monkeypatch.setattr(bootstrap, "ensure_deps", lambda **kwargs: False)
    with pytest.raises(SystemExit) as result:
        bootstrap._bootstrap_dependencies(tmp_path, "python")
    assert result.value.code == 0
