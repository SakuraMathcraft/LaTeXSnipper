from __future__ import annotations


from ui.automation_api_controller import AutomationApiController


def test_automation_api_start_and_stop_operations_are_serialized() -> None:
    class Config:
        def __init__(self) -> None:
            self.data = {}

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set(self, key, value) -> None:
            self.data[key] = value

        def set_many(self, values) -> None:
            self.data.update(values)

    harness = AutomationApiController(Config(), recognition_coordinator=None)
    pending = []
    results = []
    harness._run_automation_api_worker = lambda worker, done: pending.append(
        (worker, done)
    )

    harness._start_automation_api_async(
        lambda ok, message: results.append((ok, message))
    )
    harness._stop_automation_api_async(
        lambda ok, message: results.append((ok, message))
    )

    assert len(pending) == 1
    assert pending[0][0]._action == "start"

    server = object()
    pending[0][1](True, "started", server)
    assert len(pending) == 2
    assert pending[1][0]._action == "stop"
    assert pending[1][0]._server is server

    pending[1][1](True, "stopped", None)
    assert harness._automation_api_server is None
    assert results == [(True, "started"), (True, "stopped")]


def test_automation_api_unchanged_settings_do_not_restart_running_server() -> None:
    class Config:
        def __init__(self) -> None:
            self.data = {
                "automation_api_access_scope": "local",
                "automation_api_bind_address": "127.0.0.1",
                "automation_api_port": 28765,
            }

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set_many(self, values) -> None:
            self.data.update(values)

    harness = AutomationApiController(Config(), recognition_coordinator=None)
    harness._automation_api_server = object()
    stopped: list[bool] = []
    harness._stop_automation_api_async = lambda _callback=None: stopped.append(True)

    harness.update_automation_api_settings_async(
        {
            "automation_api_access_scope": "local",
            "automation_api_bind_address": "127.0.0.1",
            "automation_api_port": 28765,
        }
    )

    assert stopped == []
