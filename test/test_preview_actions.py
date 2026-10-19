"""History and favorites actions must keep typed content and preview in sync."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QListWidget, QPlainTextEdit, QWidget

from runtime.history_store import load_history_store
from ui.controllers.history import HistoryController
from ui.controllers.preview import PreviewController
from ui.favorites_window import FavoritesWindow


@pytest.fixture(scope="session")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def controllers(application, tmp_path):
    view = QWidget()
    view.latex_editor = QPlainTextEdit(view)
    rendered = []
    view.preview_view = SimpleNamespace(
        setHtml=lambda html, base: rendered.append(html)
    )
    status = SimpleNamespace(set_action_status=lambda *args, **kwargs: None)
    preview = PreviewController(view, status, lambda text: "sample")
    history = HistoryController(
        view,
        SimpleNamespace(get=lambda key, default=None: default),
        None,
        preview,
        status,
        None,
        None,
    )
    history.history_file = str(tmp_path / "history.json")
    try:
        yield view, preview, history, rendered
    finally:
        preview.shutdown()
        view.deleteLater()
        application.processEvents()


@pytest.mark.parametrize("editor_source", ["x+1", "unfinished edit"])
def test_history_edit_updates_content_once_and_preserves_other_edits(
    controllers, monkeypatch, editor_source
):
    view, preview, history, rendered = controllers
    history.history = ["x+1"]
    history._formula_names = {"x+1": "sample"}
    history._formula_types = {"x+1": "mathcraft_text"}
    preview.render_latex_in_preview("x+1", "mathcraft_text")
    preview.set_source(editor_source, "mathcraft_text")
    rendered.clear()
    row = QWidget(view)
    row._latex_text = "x+1"
    row._history_index = 0
    monkeypatch.setattr(
        "ui.controllers.history.EditFormulaDialog",
        lambda *args, **kwargs: SimpleNamespace(
            exec=lambda: QDialog.DialogCode.Accepted, value=lambda: "x+2"
        ),
    )
    history._edit_history_row(row)
    assert len(rendered) == 1
    assert "x+2" in rendered[0]
    assert view.latex_editor.toPlainText() == (
        "x+2" if editor_source == "x+1" else editor_source
    )
    assert load_history_store(history.history_file) == (
        ["x+2"],
        {"x+2": "sample"},
        {"x+2": "mathcraft_text"},
    )


@pytest.mark.parametrize("already_rendered", [False, True])
def test_loading_favorite_refreshes_once_even_when_returning_to_a_record(
    controllers, already_rendered
):
    view, preview, history, rendered = controllers
    if already_rendered:
        preview.render_latex_in_preview("saved text", "mathcraft_text")
    preview.set_source("other formula", "mathcraft")
    favorites = SimpleNamespace(
        preview=preview,
        history=history,
        _favorite_types={"saved text": "mathcraft_text"},
        _favorite_names={"saved text": "sample"},
        list_widget=QListWidget(view),
        _set_status=lambda message: None,
    )
    favorites.list_widget.addItem("saved text")
    item = favorites.list_widget.item(0)
    item.setData(Qt.ItemDataRole.UserRole, "saved text")
    rendered.clear()
    FavoritesWindow._on_item_double_clicked(favorites, item)
    assert view.latex_editor.toPlainText() == "saved text"
    assert len(rendered) == 1
    assert "saved text" in rendered[0]
    assert preview._editor_preview_content_type == "mathcraft_text"
