from __future__ import annotations


from runtime.config_manager import ConfigManager


def test_config_manager_updates_multiple_values_with_one_save() -> None:
    manager = ConfigManager.__new__(ConfigManager)
    manager.data = {}
    saves: list[None] = []
    manager.save = lambda: saves.append(None)

    manager.set_many({"one": 1, "two": 2})

    assert manager.data == {"one": 1, "two": 2}
    assert saves == [None]
