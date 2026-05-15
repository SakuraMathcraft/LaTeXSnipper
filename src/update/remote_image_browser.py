import base64
from typing import Dict

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QTextDocument
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QTextBrowser


class RemoteImageBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._manager.finished.connect(self._on_reply)
        self._cache: Dict[str, bytes] = {}
        self._pending: Dict[str, QNetworkReply] = {}
        self._generation = 0

    def start_new_html(self, html: str):
        self._generation += 1
        self._abort_pending()
        super().setHtml(html)

    def start_new_markdown(self, markdown: str, stylesheet: str = ""):
        self._generation += 1
        self._abort_pending()
        if stylesheet:
            self.document().setDefaultStyleSheet(stylesheet)
        self.document().setMarkdown(
            markdown,
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub,
        )

    def _abort_pending(self):
        for r in list(self._pending.values()):
            try:
                r.finished.disconnect(self._on_reply)
            except Exception:
                pass
            r.abort()
            r.deleteLater()
        self._pending.clear()

    def loadResource(self, rtype, url: QUrl):
        if rtype == QTextDocument.ResourceType.ImageResource and url.scheme() in ("http", "https"):
            key = url.toString()
            if key in self._cache:
                return self._cache[key]
            if key not in self._pending:
                reply = self._manager.get(QNetworkRequest(url))
                reply._gen = self._generation  # type: ignore
                self._pending[key] = reply
            # Transparent 1x1 placeholder.
            return base64.b64decode("R0lGODlhAQABAPAAAAAAAAAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==")
        return super().loadResource(rtype, url)

    def _on_reply(self, reply: QNetworkReply):
        url = reply.url().toString()
        gen = getattr(reply, "_gen", -1)
        self._pending.pop(url, None)
        if gen == self._generation and reply.error() == QNetworkReply.NetworkError.NoError:
            data = bytes(reply.readAll())
            self._cache[url] = data
            self.document().addResource(QTextDocument.ResourceType.ImageResource, reply.url(), data)
            self.viewport().update()
        reply.deleteLater()
