from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QColor, QCursor, QImage, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap, QRegion, QSurfaceFormat, QWheelEvent
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QLabel, QMenu, QScrollArea, QSizePolicy, QWidget

try:
    from qfluentwidgets import InfoBar, InfoBarPosition
except Exception:  # pragma: no cover
    InfoBar = None
    InfoBarPosition = None

try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
except Exception:  # pragma: no cover
    QOpenGLWidget = None


@dataclass(frozen=True)
class PopplerBackendStatus:
    requested_backend: str
    pdfinfo_path: str
    pdftocairo_path: str
    pdftoppm_path: str
    system_poppler_found: bool
    ready: bool
    detail: str


def _which(command: str) -> str:
    try:
        return shutil.which(command) or ""
    except Exception:
        return ""


def _hidden_subprocess_kwargs() -> dict:
    kwargs: dict = {}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    except Exception:
        pass
    return kwargs


def detect_poppler_backend() -> PopplerBackendStatus:
    pdfinfo_path = _which("pdfinfo")
    pdftocairo_path = _which("pdftocairo")
    pdftoppm_path = _which("pdftoppm")
    ready = bool(pdfinfo_path and pdftocairo_path)
    system_found = bool(pdfinfo_path or pdftocairo_path or pdftoppm_path)
    if ready:
        detail = (
            "已检测到 TeX Live 或 MiKTeX 提供的 Poppler 命令；"
            "当前可直接启用 Poppler 高清预览。"
        )
    elif system_found:
        detail = (
            "已检测到部分系统级 Poppler 命令，但缺少完整渲染链；"
            "请确认 TeX Live 或 MiKTeX 已正确安装并已加入 PATH。"
        )
    else:
        detail = "未检测到系统级 Poppler 命令。请先部署 TeX Live 或 MiKTeX。"
    return PopplerBackendStatus(
        requested_backend="poppler",
        pdfinfo_path=pdfinfo_path,
        pdftocairo_path=pdftocairo_path,
        pdftoppm_path=pdftoppm_path,
        system_poppler_found=system_found,
        ready=ready,
        detail=detail,
    )


def _has_nvidia_gpu_silent() -> bool:
    try:
        nvidia_smi = shutil.which("nvidia-smi")
    except Exception:
        nvidia_smi = None
    if nvidia_smi:
        try:
            result = subprocess.run(
                [nvidia_smi, "-L"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=2,
                **_hidden_subprocess_kwargs(),
            )
            text = f"{result.stdout}\n{result.stderr}".lower()
            if result.returncode == 0 and "nvidia" in text:
                return True
        except Exception:
            pass
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "Name"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=2,
                **_hidden_subprocess_kwargs(),
            )
            if "nvidia" in f"{result.stdout}\n{result.stderr}".lower():
                return True
        except Exception:
            pass
    return False


if QOpenGLWidget is not None:
    class _MagnifierGpuSurface(QOpenGLWidget):
        def __init__(self, parent=None):
            fmt = QSurfaceFormat()
            fmt.setAlphaBufferSize(8)
            super().__init__(parent)
            try:
                self.setFormat(fmt)
            except Exception:
                pass
            self._source_image = QImage()
            self._dpr = 1.0
            self._lens_d = 0
            self._frame = QPixmap()
            self.setAutoFillBackground(False)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            try:
                self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)
            except Exception:
                pass

        def setSourceFrame(self, source_image: QImage, dpr: float, lens_d: int, frame: QPixmap) -> None:
            self._source_image = source_image
            self._dpr = max(1.0, float(dpr))
            self._lens_d = int(lens_d)
            self._frame = frame
            self.update()

        def paintGL(self) -> None:
            try:
                ctx = self.context()
                if ctx is not None:
                    funcs = ctx.functions()
                    funcs.glClearColor(0.0, 0.0, 0.0, 0.0)
                    funcs.glClear(0x00004000)  # GL_COLOR_BUFFER_BIT
            except Exception:
                pass
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            if not self._source_image.isNull() and self._lens_d > 0:
                lens_rect = QRect(8, 8, self._lens_d, self._lens_d)
                lens_path = QPainterPath()
                lens_path.addEllipse(QRectF(lens_rect))
                painter.setClipPath(lens_path)
                painter.fillPath(lens_path, QColor("#f0f0f0"))
                painter.drawImage(
                    QRectF(lens_rect),
                    self._source_image,
                    QRectF(0.0, 0.0, float(self._source_image.width()), float(self._source_image.height())),
                )
                painter.setClipping(False)
            if not self._frame.isNull():
                painter.drawPixmap(0, 0, self._frame)
            painter.end()


class _PopplerSvgCanvas(QWidget):
    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self.owner = owner
        self.setMouseTracking(True)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#7d7d7d"))
        for rect in self.owner._page_rects:
            painter.fillRect(rect, QColor("#ffffff"))
        for index, (renderer, rect) in enumerate(zip(self.owner._page_renderers, self.owner._page_rects)):
            pixmap = self.owner._page_pixmaps[index] if index < len(self.owner._page_pixmaps) else None
            if pixmap is not None and not pixmap.isNull() and self.owner._pixmap_matches_rect(pixmap, rect):
                painter.drawPixmap(rect, pixmap)
                continue
            if renderer is None or not renderer.isValid():
                continue
            renderer.render(painter, QRectF(rect))
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.owner._handle_mouse_press(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self.owner._handle_mouse_move(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.owner._handle_mouse_release(event)

    def leaveEvent(self, event) -> None:
        self.owner._handle_leave(event)
        super().leaveEvent(event)


class _MagnifierRenderWorker(QObject):
    finished = pyqtSignal(int, QImage, float, bool)

    def __init__(self):
        super().__init__()
        self._renderer_cache: dict[str, QSvgRenderer] = {}

    @pyqtSlot(int, str, float, float, float, float, int, float, float, bool)
    def render_region(
        self,
        token: int,
        svg_path: str,
        rel_x: float,
        rel_y: float,
        page_w: float,
        page_h: float,
        render_side: int,
        scale: float,
        dpr: float,
        is_hq: bool,
    ) -> None:
        image = QImage()
        try:
            path = str(svg_path or "")
            renderer = self._renderer_cache.get(path)
            if renderer is None or not renderer.isValid():
                renderer = QSvgRenderer(path)
                self._renderer_cache[path] = renderer
            if renderer is not None and renderer.isValid():
                side = max(1, int(render_side))
                image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(QColor("#f0f0f0"))
                target_w = max(1.0, float(page_w) * float(scale))
                target_h = max(1.0, float(page_h) * float(scale))
                center = side / 2.0
                target_rect = QRectF(
                    center - float(rel_x) * target_w,
                    center - float(rel_y) * target_h,
                    target_w,
                    target_h,
                )
                painter = QPainter(image)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                renderer.render(painter, target_rect)
                painter.end()
        except Exception:
            image = QImage()
        self.finished.emit(int(token), image, float(dpr), bool(is_hq))


class PopplerPdfView(QScrollArea):
    syncJumpRequested = pyqtSignal(int, float, float)
    _magnifier_render_request = pyqtSignal(int, str, float, float, float, float, int, float, float, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._backend_status = detect_poppler_backend()
        if not self._backend_status.ready:
            raise RuntimeError(self._backend_status.detail)
        self._doc_path = ""
        self._page_count = 0
        self._page_sizes: list[tuple[float, float]] = []
        self._page_rects: list[QRect] = []
        self._page_renderers: list[QSvgRenderer | None] = []
        self._page_svg_files: list[str] = []
        self._page_pixmaps: list[QPixmap | None] = []
        self._renderer_lru: list[int] = []
        self._renderer_cache_limit = 20
        self._renderer_cache_limit_min = 12
        self._renderer_cache_limit_max = 32
        self._renderer_prefetch_radius = 2
        self._renderer_prefetch_radius_dynamic = 2
        self._zoom_factor = 1.0
        self._zoom_mode = "fit_width"
        self._page_spacing = 12
        self._page_margin = 2
        self._text_width_ratio = 0.82
        self._page_grid_cols = 1
        self._page_grid_rows = 1
        self._magnifier_active = False
        self._magnifier_size = 300
        self._magnifier_zoom = 3.2
        self._magnifier_oversample = 1.0
        self._magnifier_output_dpr = 1.0
        self._magnifier_last_viewport_pos: QPoint | None = None
        self._magnifier_pending_hq_pos: QPoint | None = None
        self._magnifier_min_move_px = 2
        self._magnifier_frame_cache: dict[tuple[int, float, str], QPixmap] = {}
        self._magnifier_interactive_interval_ms = 16
        self._magnifier_hq_idle_ms = 70
        self._magnifier_fast_dpr_cap = 1.25
        self._magnifier_request_seq = 0
        self._magnifier_last_applied_seq = 0
        self._magnifier_request_positions: dict[int, QPoint] = {}
        self._magnifier_request_meta: dict[int, tuple[int, float]] = {}
        self._magnifier_request_keys: dict[int, tuple[int, bool]] = {}
        self._magnifier_inflight_keys: set[tuple[int, bool]] = set()
        self._magnifier_deferred_by_key: dict[tuple[int, bool], dict] = {}
        self._magnifier_last_source_image = QImage()
        self._magnifier_last_source_dpr = 1.0
        self._magnifier_last_lens_d = self._magnifier_size - 16
        self._magnifier_last_presented_pos: QPoint | None = None
        self._magnifier_last_hq_pos: QPoint | None = None
        self._magnifier_last_hq_dpr = 0.0
        self._magnifier_hq_cooldown_until = 0.0
        self._cache_refresh_cost_ema_ms = 0.0
        self._gpu_probe_remaining = 6
        self._gpu_fallback_notified = False
        self._last_scroll_h = 0
        self._last_scroll_v = 0
        self._last_scroll_ts = 0.0
        self._pan_active = False
        self._pan_dragged = False
        self._pan_start_pos = QPoint()
        self._pan_start_h = 0
        self._pan_start_v = 0
        self._pending_magnifier_pos: QPoint | None = None
        self._magnifier_gpu_enabled = bool(QOpenGLWidget is not None and _has_nvidia_gpu_silent())
        if self._magnifier_gpu_enabled and self._window_has_qquickwidget():
            self._magnifier_gpu_enabled = False
        self._temp_dir = tempfile.TemporaryDirectory(prefix="latexsnipper-poppler-svg-")
        self._canvas = _PopplerSvgCanvas(self, self)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setWidget(self._canvas)
        self.setWidgetResizable(False)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._magnifier_label = None
        if self._magnifier_gpu_enabled and QOpenGLWidget is not None:
            try:
                self._magnifier_label = _MagnifierGpuSurface(self.viewport())
            except Exception:
                self._magnifier_label = None
                self._magnifier_gpu_enabled = False
        if self._magnifier_label is None:
            self._magnifier_label = QLabel(self.viewport())
        self._magnifier_label.setFixedSize(self._magnifier_size, self._magnifier_size)
        try:
            self._magnifier_label.setMask(QRegion(0, 0, self._magnifier_size, self._magnifier_size, QRegion.RegionType.Ellipse))
        except Exception:
            pass
        self._magnifier_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._magnifier_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._magnifier_label.setStyleSheet("background: transparent;")
        self._magnifier_label.hide()
        self._magnifier_update_timer = QTimer(self)
        self._magnifier_update_timer.setSingleShot(True)
        self._magnifier_update_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._magnifier_update_timer.setInterval(self._magnifier_interactive_interval_ms)
        self._magnifier_update_timer.timeout.connect(self._flush_magnifier_update)
        self._magnifier_hq_timer = QTimer(self)
        self._magnifier_hq_timer.setSingleShot(True)
        self._magnifier_hq_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._magnifier_hq_timer.setInterval(self._magnifier_hq_idle_ms)
        self._magnifier_hq_timer.timeout.connect(self._flush_magnifier_hq)
        self._magnifier_render_thread = None
        self._magnifier_render_worker = None
        self._page_cache_timer = QTimer(self)
        self._page_cache_timer.setSingleShot(True)
        self._page_cache_timer.setInterval(60)
        self._page_cache_timer.timeout.connect(self._refresh_visible_page_cache)
        self._magnifier_cursor = self._build_magnifier_cursor()
        self.viewport().setCursor(self._magnifier_cursor)
        self.horizontalScrollBar().valueChanged.connect(self._on_viewport_scrolled)
        self.verticalScrollBar().valueChanged.connect(self._on_viewport_scrolled)
        self._configure_magnifier_timing_for_display()

    def _configure_magnifier_timing_for_display(self) -> None:
        refresh = 0.0
        try:
            scr = self.screen()
            if scr is not None:
                refresh = float(scr.refreshRate() or 0.0)
        except Exception:
            refresh = 0.0
        if refresh <= 1.0:
            refresh = 60.0
        interval = max(5, min(16, int(round(1000.0 / refresh))))
        self._magnifier_interactive_interval_ms = int(interval)
        self._magnifier_update_timer.setInterval(self._magnifier_interactive_interval_ms)
        self._magnifier_min_move_px = 1 if self._magnifier_interactive_interval_ms <= 8 else 2
        if refresh >= 140.0:
            self._magnifier_fast_dpr_cap = 1.1
        elif refresh >= 100.0:
            self._magnifier_fast_dpr_cap = 1.15
        else:
            self._magnifier_fast_dpr_cap = 1.25

    def _build_magnifier_cursor(self) -> QCursor:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("#1c1c1c"), 4))
        painter.drawEllipse(4, 4, 16, 16)
        painter.drawLine(17, 17, 28, 28)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawEllipse(4, 4, 16, 16)
        painter.drawLine(17, 17, 28, 28)
        painter.end()
        return QCursor(pixmap, 12, 12)

    def _hide_magnifier_cursor(self) -> None:
        self.viewport().setCursor(Qt.CursorShape.BlankCursor)

    def _restore_magnifier_cursor(self) -> None:
        self.viewport().setCursor(self._magnifier_cursor)

    def _run_command(self, command: list[str], timeout: int = 30) -> str:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            **_hidden_subprocess_kwargs(),
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Poppler 命令执行失败").strip())
        return result.stdout

    def _ensure_magnifier_render_worker(self) -> None:
        if self._magnifier_render_thread is not None and self._magnifier_render_worker is not None:
            return
        thread = QThread(self)
        worker = _MagnifierRenderWorker()
        worker.moveToThread(thread)
        self._magnifier_render_request.connect(worker.render_region)
        worker.finished.connect(self._on_magnifier_render_finished)
        thread.start()
        self._magnifier_render_thread = thread
        self._magnifier_render_worker = worker

    def shutdown_render_worker(self) -> None:
        thread = self._magnifier_render_thread
        worker = self._magnifier_render_worker
        if thread is None:
            return
        try:
            if worker is not None:
                try:
                    self._magnifier_render_request.disconnect(worker.render_region)
                except Exception:
                    pass
                try:
                    worker.finished.disconnect(self._on_magnifier_render_finished)
                except Exception:
                    pass
            if thread.isRunning():
                thread.quit()
                thread.wait(1200)
        except Exception:
            pass
        self._magnifier_render_thread = None
        self._magnifier_render_worker = None

    def _load_page_metadata(self) -> None:
        output = self._run_command([self._backend_status.pdfinfo_path, self._doc_path], timeout=20)
        pages_match = re.search(r"Pages:\s+(\d+)", output)
        self._page_count = int(pages_match.group(1)) if pages_match else 0
        self._page_sizes = []
        for index in range(self._page_count):
            page_out = self._run_command(
                [self._backend_status.pdfinfo_path, "-f", str(index + 1), "-l", str(index + 1), "-box", self._doc_path],
                timeout=20,
            )
            size_match = re.search(r"Page\s+\d+\s+size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", page_out)
            if not size_match:
                size_match = re.search(r"Page size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", page_out)
            if size_match:
                self._page_sizes.append((float(size_match.group(1)), float(size_match.group(2))))
            else:
                self._page_sizes.append((595.0, 842.0))

    def load_document(self, pdf_path: str) -> None:
        self._doc_path = str(pdf_path or "")
        self._page_count = 0
        self._page_sizes = []
        self._page_rects = []
        self._page_renderers = []
        self._page_svg_files = []
        self._page_pixmaps = []
        self._renderer_lru = []
        self._renderer_prefetch_radius_dynamic = self._renderer_prefetch_radius
        self._magnifier_update_timer.stop()
        self._magnifier_hq_timer.stop()
        self._pending_magnifier_pos = None
        self._pending_magnifier_hq_pos = None
        self._magnifier_last_viewport_pos = None
        self._magnifier_active = False
        self._magnifier_label.hide()
        self._magnifier_request_seq = 0
        self._magnifier_last_applied_seq = 0
        self._magnifier_request_positions.clear()
        self._magnifier_request_meta.clear()
        self._magnifier_inflight_keys.clear()
        self._magnifier_deferred_by_key.clear()
        self._magnifier_request_keys.clear()
        self._magnifier_last_source_image = QImage()
        self._magnifier_last_source_dpr = 1.0
        self._magnifier_last_lens_d = self._magnifier_size - 16
        self._magnifier_last_presented_pos = None
        self._magnifier_last_hq_pos = None
        self._magnifier_last_hq_dpr = 0.0
        self._magnifier_hq_cooldown_until = 0.0
        self._cache_refresh_cost_ema_ms = 0.0
        self._gpu_probe_remaining = 6
        self._last_scroll_h = 0
        self._last_scroll_v = 0
        self._last_scroll_ts = 0.0
        # Warm the worker upfront so the first magnifier request is not lost during lazy thread startup.
        self._ensure_magnifier_render_worker()
        if self._doc_path:
            self._load_page_metadata()
            self._page_renderers = [None] * self._page_count
            self._page_svg_files = [""] * self._page_count
            self._page_pixmaps = [None] * self._page_count
        self._layout_pages()

    def closeEvent(self, event) -> None:
        self.shutdown_render_worker()
        try:
            self._temp_dir.cleanup()
        except Exception:
            pass
        super().closeEvent(event)

    def zoomFactor(self) -> float:
        return float(self._zoom_factor)

    def setZoomFactor(self, factor: float) -> None:
        self._zoom_mode = "custom"
        self._zoom_factor = max(0.25, min(5.0, float(factor)))
        self._layout_pages()

    def set_actual_size(self) -> None:
        self._zoom_mode = "custom"
        self._zoom_factor = 1.0
        self._layout_pages()

    def set_fit_window(self) -> None:
        self._zoom_mode = "fit_window"
        self._layout_pages()

    def set_fit_width(self) -> None:
        self._zoom_mode = "fit_width"
        self._layout_pages()

    def set_fit_text_width(self) -> None:
        self._zoom_mode = "fit_text_width"
        self._layout_pages()

    def set_page_grid(self, cols: int, rows: int = 1) -> None:
        self._page_grid_cols = max(1, int(cols or 1))
        self._page_grid_rows = max(1, int(rows or 1))
        self._layout_pages()

    def _grid_cell_width(self) -> int:
        cols = max(1, int(self._page_grid_cols))
        viewport_w = max(1, self.viewport().width())
        gap = self._grid_spacing()
        total_gap = max(0, cols - 1) * gap
        usable = max(1, viewport_w - 2 * self._page_margin - total_gap)
        return max(1, int(usable // cols))

    def _grid_spacing(self) -> int:
        cols = max(1, int(self._page_grid_cols))
        rows = max(1, int(self._page_grid_rows))
        if cols > 1 or rows > 1:
            return max(1, int(self._page_margin))
        return max(1, int(self._page_spacing))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._zoom_mode != "custom":
            self._layout_pages()

    def _effective_zoom(self, page_width: float, page_height: float) -> float:
        viewport_w = max(1, self._grid_cell_width())
        viewport_h = max(1, self.viewport().height() - 2 * self._page_margin)
        if self._zoom_mode == "fit_width":
            return max(0.01, viewport_w / max(1.0, page_width))
        if self._zoom_mode == "fit_text_width":
            return max(0.01, viewport_w / max(1.0, page_width * self._text_width_ratio))
        if self._zoom_mode == "fit_window":
            return max(0.01, min(viewport_w / max(1.0, page_width), viewport_h / max(1.0, page_height)))
        return max(0.01, self._zoom_factor)

    def _svg_path_candidates(self, prefix: Path) -> list[Path]:
        candidates: list[Path] = []
        direct_svg = prefix.with_suffix(".svg")
        if direct_svg.exists():
            candidates.append(direct_svg)
        for match in sorted(prefix.parent.glob(f"{prefix.name}*.svg")):
            if match not in candidates:
                candidates.append(match)
        if prefix.exists() and prefix not in candidates:
            candidates.append(prefix)
        return candidates

    def _ensure_page_renderer(self, index: int) -> None:
        if index < 0 or index >= self._page_count:
            return
        if self._page_renderers[index] is not None and self._page_renderers[index].isValid():
            self._touch_renderer(index)
            return
        prefix = Path(self._temp_dir.name) / f"page_{index + 1}"
        for candidate in self._svg_path_candidates(prefix):
            if candidate.exists():
                try:
                    candidate.unlink()
                except Exception:
                    pass
        self._run_command(
            [
                self._backend_status.pdftocairo_path,
                "-svg",
                "-f",
                str(index + 1),
                "-l",
                str(index + 1),
                self._doc_path,
                str(prefix),
            ],
            timeout=30,
        )
        svg_path = next((str(candidate) for candidate in self._svg_path_candidates(prefix) if candidate.exists()), "")
        if not svg_path:
            raise RuntimeError("pdftocairo 未生成 SVG 文件")
        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            raise RuntimeError("Poppler 生成的 SVG 无法加载")
        self._page_svg_files[index] = svg_path
        self._page_renderers[index] = renderer
        self._touch_renderer(index)
        if index < len(self._page_pixmaps):
            self._page_pixmaps[index] = None

    def _attach_renderer_from_svg(self, index: int, svg_path: str) -> bool:
        if index < 0 or index >= self._page_count:
            return False
        path = str(svg_path or "")
        if not path:
            return False
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            return False
        self._page_svg_files[index] = path
        self._page_renderers[index] = renderer
        self._touch_renderer(index)
        if index < len(self._page_pixmaps):
            self._page_pixmaps[index] = None
        return True

    def _batch_svg_candidates(self, prefix: Path) -> list[Path]:
        candidates: list[Path] = []
        direct_svg = prefix.with_suffix(".svg")
        if direct_svg.exists():
            candidates.append(direct_svg)
        for match in sorted(prefix.parent.glob(f"{prefix.name}*.svg")):
            if match not in candidates:
                candidates.append(match)
        return candidates

    def _ensure_page_renderers_batched(self, indexes: list[int]) -> None:
        wanted = sorted({int(i) for i in indexes if 0 <= int(i) < self._page_count})
        if not wanted:
            return
        missing = [
            i for i in wanted
            if not (self._page_renderers[i] is not None and self._page_renderers[i].isValid())
        ]
        if not missing:
            for i in wanted:
                self._touch_renderer(i)
            return
        groups: list[tuple[int, int]] = []
        start = missing[0]
        prev = start
        for idx in missing[1:]:
            if idx == prev + 1:
                prev = idx
                continue
            groups.append((start, prev))
            start = idx
            prev = idx
        groups.append((start, prev))
        for g_start, g_end in groups:
            if g_start == g_end:
                self._ensure_page_renderer(g_start)
                continue
            prefix = Path(self._temp_dir.name) / f"batch_{g_start + 1}_{g_end + 1}"
            for candidate in self._batch_svg_candidates(prefix):
                try:
                    candidate.unlink()
                except Exception:
                    pass
            try:
                self._run_command(
                    [
                        self._backend_status.pdftocairo_path,
                        "-svg",
                        "-f",
                        str(g_start + 1),
                        "-l",
                        str(g_end + 1),
                        self._doc_path,
                        str(prefix),
                    ],
                    timeout=45,
                )
                generated = self._batch_svg_candidates(prefix)
                expected = g_end - g_start + 1
                if len(generated) != expected:
                    for i in range(g_start, g_end + 1):
                        self._ensure_page_renderer(i)
                    continue
                ok_all = True
                for offset, path in enumerate(generated):
                    if not self._attach_renderer_from_svg(g_start + offset, str(path)):
                        ok_all = False
                        break
                if not ok_all:
                    for i in range(g_start, g_end + 1):
                        self._ensure_page_renderer(i)
            except Exception:
                for i in range(g_start, g_end + 1):
                    self._ensure_page_renderer(i)

    def _touch_renderer(self, index: int) -> None:
        try:
            self._renderer_lru.remove(index)
        except ValueError:
            pass
        self._renderer_lru.append(index)

    def _visible_window_indexes(self, radius: int | None = None) -> set[int]:
        base = self._visible_page_indexes()
        if not base:
            return set()
        r = self._renderer_prefetch_radius_dynamic if radius is None else max(0, int(radius))
        window: set[int] = set()
        for idx in base:
            start = max(0, idx - r)
            end = min(self._page_count - 1, idx + r)
            for i in range(start, end + 1):
                window.add(i)
        return window

    def _evict_renderer_cache(self, protected: set[int] | None = None) -> None:
        keep = protected or set()
        while len(self._renderer_lru) > self._renderer_cache_limit:
            victim = self._renderer_lru.pop(0)
            if victim in keep:
                self._renderer_lru.append(victim)
                # All cached renderers are protected for now.
                if all(i in keep for i in self._renderer_lru):
                    break
                continue
            if 0 <= victim < len(self._page_renderers):
                self._page_renderers[victim] = None

    def _layout_pages(self) -> None:
        self._page_rects = []
        if self._page_count <= 0:
            self._canvas.resize(10, 10)
            self._canvas.update()
            return
        cols = max(1, int(self._page_grid_cols))
        cell_w = self._grid_cell_width()
        gap = self._grid_spacing()
        page_draw_sizes: list[tuple[int, int]] = []
        max_draw_w = 1
        for page_w, page_h in self._page_sizes:
            zoom = self._effective_zoom(page_w, page_h)
            draw_w = max(1, int(round(page_w * zoom)))
            draw_h = max(1, int(round(page_h * zoom)))
            page_draw_sizes.append((draw_w, draw_h))
            if draw_w > max_draw_w:
                max_draw_w = draw_w
        col_w = max(cell_w, int(max_draw_w))
        row_y = self._page_margin
        row_max_h = 0
        viewport_w = self.viewport().width()
        max_w = viewport_w
        for index, (page_w, page_h) in enumerate(self._page_sizes):
            draw_w, draw_h = page_draw_sizes[index]
            col = index % cols
            if index > 0 and col == 0:
                row_y += row_max_h + gap
                row_max_h = 0
            cell_left = self._page_margin + col * (col_w + gap)
            x = cell_left + max(0, (col_w - draw_w) // 2)
            rect = QRect(x, row_y, draw_w, draw_h)
            self._page_rects.append(rect)
            row_max_h = max(row_max_h, draw_h)
            max_w = max(max_w, self._page_margin * 2 + cols * col_w + max(0, cols - 1) * gap)
        total_h = row_y + row_max_h + self._page_margin
        self._canvas.resize(max_w, max(total_h, self.viewport().height()))
        self._canvas.update()
        self._schedule_page_cache_refresh()

    def _schedule_page_cache_refresh(self) -> None:
        if self._page_count <= 0:
            return
        self._page_cache_timer.start()

    def _on_viewport_scrolled(self, _value: int) -> None:
        now = time.perf_counter()
        h = int(self.horizontalScrollBar().value())
        v = int(self.verticalScrollBar().value())
        if self._last_scroll_ts > 0.0:
            dt = max(1e-3, now - self._last_scroll_ts)
            dist = abs(h - self._last_scroll_h) + abs(v - self._last_scroll_v)
            speed = float(dist) / dt
            if speed >= 3000.0:
                self._renderer_prefetch_radius_dynamic = 0
            elif speed >= 1800.0:
                self._renderer_prefetch_radius_dynamic = 1
            elif speed >= 900.0:
                self._renderer_prefetch_radius_dynamic = 2
            else:
                self._renderer_prefetch_radius_dynamic = 3
        self._last_scroll_h = h
        self._last_scroll_v = v
        self._last_scroll_ts = now
        self._schedule_page_cache_refresh()

    def _target_cache_dpr(self) -> float:
        base = max(float(self.devicePixelRatioF()), float(self.viewport().devicePixelRatioF()))
        return max(1.0, min(2.25, base))

    def _target_magnifier_dpr(self) -> float:
        return max(1.0, min(2.0, self._target_cache_dpr()))

    def _pixmap_matches_rect(self, pixmap: QPixmap, rect: QRect) -> bool:
        if pixmap.isNull():
            return False
        dpr = max(0.01, float(pixmap.devicePixelRatioF()))
        logical_w = float(pixmap.width()) / dpr
        logical_h = float(pixmap.height()) / dpr
        if abs(logical_w - float(rect.width())) > 0.75 or abs(logical_h - float(rect.height())) > 0.75:
            return False
        return dpr + 0.05 >= self._target_cache_dpr()

    def _visible_page_indexes(self) -> list[int]:
        if not self._page_rects:
            return []
        top = self.verticalScrollBar().value() - self.viewport().height()
        bottom = self.verticalScrollBar().value() + self.viewport().height() * 2
        left = self.horizontalScrollBar().value() - self.viewport().width()
        right = self.horizontalScrollBar().value() + self.viewport().width() * 2
        visible: list[int] = []
        view_rect = QRect(left, top, max(1, right - left), max(1, bottom - top))
        for index, rect in enumerate(self._page_rects):
            if rect.intersects(view_rect):
                visible.append(index)
        return visible

    def _refresh_visible_page_cache(self) -> None:
        if self._page_count <= 0:
            return
        refresh_start = time.perf_counter()
        visible_indexes = self._visible_page_indexes()
        warm_indexes = self._visible_window_indexes()
        missing_warm = [
            i for i in sorted(warm_indexes)
            if 0 <= i < self._page_count and not (self._page_renderers[i] is not None and self._page_renderers[i].isValid())
        ]
        if missing_warm:
            self._ensure_page_renderers_batched(missing_warm)
        for index in sorted(warm_indexes):
            if 0 <= index < self._page_count and self._page_renderers[index] is not None and self._page_renderers[index].isValid():
                self._touch_renderer(index)
        self._evict_renderer_cache(protected=warm_indexes)
        for index in visible_indexes:
            if index >= len(self._page_rects):
                continue
            rect = self._page_rects[index]
            if rect.width() <= 0 or rect.height() <= 0:
                continue
            pixmap = self._page_pixmaps[index] if index < len(self._page_pixmaps) else None
            if pixmap is not None and self._pixmap_matches_rect(pixmap, rect):
                continue
            renderer = self._page_renderers[index]
            if renderer is None or not renderer.isValid():
                continue
            dpr = self._target_cache_dpr()
            image_w = max(1, int(round(float(rect.width()) * dpr)))
            image_h = max(1, int(round(float(rect.height()) * dpr)))
            image = QImage(image_w, image_h, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QColor("#ffffff"))
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            renderer.render(painter, QRectF(0.0, 0.0, float(image_w), float(image_h)))
            painter.end()
            if index < len(self._page_pixmaps):
                page_pixmap = QPixmap.fromImage(image)
                page_pixmap.setDevicePixelRatio(dpr)
                self._page_pixmaps[index] = page_pixmap
        refresh_ms = (time.perf_counter() - refresh_start) * 1000.0
        self._update_renderer_cache_limit(visible_indexes, refresh_ms)
        self._evict_renderer_cache(protected=warm_indexes)
        self._canvas.update()

    def _content_pos(self, pos: QPoint) -> QPoint:
        return QPoint(pos.x() + self.horizontalScrollBar().value(), pos.y() + self.verticalScrollBar().value())

    def _clamp_magnifier_center_to_page(self, viewport_pos: QPoint) -> QPoint:
        hit = self._locate_page_at(self._content_pos(viewport_pos), allow_outside=True)
        if hit is None:
            return QPoint(viewport_pos)
        _idx, rect, _rel_x, _rel_y = hit
        content_pos = self._content_pos(viewport_pos)
        cx = int(min(max(content_pos.x(), rect.left()), rect.right()))
        cy = int(min(max(content_pos.y(), rect.top()), rect.bottom()))
        return QPoint(
            cx - self.horizontalScrollBar().value(),
            cy - self.verticalScrollBar().value(),
        )

    def _locate_page_at(self, content_pos: QPoint, allow_outside: bool = False):
        if not allow_outside:
            for index, rect in enumerate(self._page_rects):
                if rect.contains(content_pos):
                    rel_x = (content_pos.x() - rect.x()) / max(1, rect.width())
                    rel_y = (content_pos.y() - rect.y()) / max(1, rect.height())
                    return index, rect, rel_x, rel_y
            return None
        px = int(content_pos.x())
        py = int(content_pos.y())
        best = None
        best_d2 = None
        for index, rect in enumerate(self._page_rects):
            rel_x = (content_pos.x() - rect.x()) / max(1, rect.width())
            rel_y = (content_pos.y() - rect.y()) / max(1, rect.height())
            if rect.left() <= px <= rect.right():
                dx = 0
            elif px < rect.left():
                dx = int(rect.left() - px)
            else:
                dx = int(px - rect.right())
            if rect.top() <= py <= rect.bottom():
                dy = 0
            elif py < rect.top():
                dy = int(rect.top() - py)
            else:
                dy = int(py - rect.bottom())
            d2 = int(dx * dx + dy * dy)
            if best is None or d2 < int(best_d2):
                best = (index, rect, rel_x, rel_y)
                best_d2 = d2
        return best

    def _build_magnifier_frame(self, size: int, dpr: float, quality: str = "hq") -> QPixmap:
        quality_key = "unified"
        key = (int(size), round(float(dpr), 2), quality_key)
        cached = self._magnifier_frame_cache.get(key)
        if cached is not None and not cached.isNull():
            return cached
        px = max(1, int(round(float(size) * dpr)))
        frame = QPixmap(px, px)
        frame.fill(Qt.GlobalColor.transparent)
        painter = QPainter(frame)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(dpr, dpr)
        lens_rect = QRect(8, 8, size - 16, size - 16)
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(lens_rect))
        painter.setPen(QPen(QColor(220, 220, 220, 180), 1.0))
        painter.drawEllipse(QRectF(lens_rect.adjusted(2, 2, -2, -2)))
        painter.end()
        frame.setDevicePixelRatio(dpr)
        self._magnifier_frame_cache[key] = frame
        return frame

    def _compose_magnifier_pixmap(self, source_image: QImage, dpr: float, lens_d: int, quality: str) -> QPixmap:
        use_dpr = max(1.0, float(dpr))
        result_px = max(1, int(round(float(self._magnifier_size) * use_dpr)))
        result = QPixmap(result_px, result_px)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.scale(use_dpr, use_dpr)
        lens_rect = QRect(8, 8, int(lens_d), int(lens_d))
        lens_path = QPainterPath()
        lens_path.addEllipse(QRectF(lens_rect))
        painter.setClipPath(lens_path)
        painter.fillPath(lens_path, QColor("#f0f0f0"))
        painter.drawImage(
            QRectF(lens_rect),
            source_image,
            QRectF(0.0, 0.0, float(source_image.width()), float(source_image.height())),
        )
        painter.setClipping(False)
        painter.drawPixmap(0, 0, self._build_magnifier_frame(self._magnifier_size, use_dpr, quality=quality))
        painter.end()
        result.setDevicePixelRatio(use_dpr)
        return result

    def _show_gpu_fallback_infobar(self, reason: str) -> None:
        if self._gpu_fallback_notified:
            return
        self._gpu_fallback_notified = True
        if InfoBar is None or InfoBarPosition is None:
            return
        try:
            InfoBar.warning(
                title="GPU 放大镜已回退",
                content=str(reason or "检测到显卡驱动合成异常，已自动切换为 CPU 放大镜。"),
                parent=self.window() if isinstance(self.window(), QWidget) else self,
                position=InfoBarPosition.TOP,
                duration=4200,
            )
        except Exception:
            pass

    def _window_has_qquickwidget(self) -> bool:
        try:
            top = self.window()
            if top is None:
                return False
            for w in top.findChildren(QWidget):
                name = str(w.metaObject().className() if w is not None else "")
                if "QQuickWidget" in name:
                    return True
        except Exception:
            pass
        return False

    def _switch_magnifier_to_cpu(self, reason: str) -> None:
        if not self._magnifier_gpu_enabled:
            return
        old = self._magnifier_label
        self._magnifier_gpu_enabled = False
        self._magnifier_label = QLabel(self.viewport())
        self._magnifier_label.setFixedSize(self._magnifier_size, self._magnifier_size)
        try:
            self._magnifier_label.setMask(QRegion(0, 0, self._magnifier_size, self._magnifier_size, QRegion.RegionType.Ellipse))
        except Exception:
            pass
        self._magnifier_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._magnifier_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._magnifier_label.setStyleSheet("background: transparent;")
        self._magnifier_label.hide()
        try:
            if old is not None:
                old.hide()
                old.setParent(None)
                old.deleteLater()
        except Exception:
            pass
        self._show_gpu_fallback_infobar(reason)

    def _gpu_surface_has_artifact(self) -> bool:
        if not self._magnifier_gpu_enabled:
            return False
        surface = self._magnifier_label
        if surface is None or not hasattr(surface, "grabFramebuffer"):
            return False
        try:
            img = surface.grabFramebuffer()
        except Exception:
            return False
        if img.isNull():
            return False
        w = int(img.width())
        h = int(img.height())
        if w <= 4 or h <= 4:
            return False
        cx = (w - 1) * 0.5
        cy = (h - 1) * 0.5
        radius = min(w, h) * 0.5
        r_outer = radius - 1.5
        r_inner = max(1.0, r_outer - 9.0)
        ring_black = 0
        ring_samples = 0
        outer_opaque = 0
        outer_samples = 0
        step = 2
        for y in range(0, h, step):
            dy = float(y) - cy
            for x in range(0, w, step):
                dx = float(x) - cx
                rr = (dx * dx + dy * dy) ** 0.5
                c = img.pixelColor(x, y)
                if rr > radius - 0.5:
                    outer_samples += 1
                    if c.alpha() > 60:
                        outer_opaque += 1
                    continue
                if rr < r_inner or rr > r_outer:
                    continue
                if c.alpha() < 70:
                    continue
                ring_samples += 1
                if c.red() < 36 and c.green() < 36 and c.blue() < 36:
                    ring_black += 1
        if outer_samples > 0 and (outer_opaque / float(outer_samples)) > 0.08:
            return True
        if ring_samples <= 0:
            return False
        return (ring_black / float(ring_samples)) > 0.06

    def _present_magnifier_pixmap(self, pixmap: QPixmap, viewport_pos: QPoint) -> None:
        self._magnifier_label.resize(self._magnifier_size, self._magnifier_size)
        if hasattr(self._magnifier_label, "setPixmap"):
            self._magnifier_label.setPixmap(pixmap)
        self._position_magnifier_label(viewport_pos)
        self._magnifier_label.show()
        self._magnifier_label.raise_()

    def _present_magnifier_source(self, source_image: QImage, dpr: float, lens_d: int, quality: str, viewport_pos: QPoint) -> None:
        if self._magnifier_gpu_enabled and self._window_has_qquickwidget():
            self._switch_magnifier_to_cpu("检测到窗口内存在 QQuickWidget，与 OpenGL 放大镜合成不兼容，已自动切换 CPU 放大镜。")
        if self._magnifier_gpu_enabled and hasattr(self._magnifier_label, "setSourceFrame"):
            frame = self._build_magnifier_frame(self._magnifier_size, dpr, quality="gpu")
            self._magnifier_label.resize(self._magnifier_size, self._magnifier_size)
            self._magnifier_label.setSourceFrame(source_image, dpr, lens_d, frame)
            self._position_magnifier_label(viewport_pos)
            self._magnifier_label.show()
            self._magnifier_label.raise_()
            if self._gpu_probe_remaining > 0:
                self._gpu_probe_remaining -= 1
                if self._gpu_surface_has_artifact():
                    self._switch_magnifier_to_cpu("检测到显卡驱动合成异常（黑边/残影），已自动切换 CPU 放大镜。")
                    pixmap = self._compose_magnifier_pixmap(source_image, dpr, lens_d, quality=quality)
                    self._present_magnifier_pixmap(pixmap, viewport_pos)
            return
        pixmap = self._compose_magnifier_pixmap(source_image, dpr, lens_d, quality=quality)
        self._present_magnifier_pixmap(pixmap, viewport_pos)

    def _predictive_magnifier_reuse(self, viewport_pos: QPoint) -> None:
        if self._magnifier_gpu_enabled:
            return
        if not self._magnifier_active:
            return
        if self._magnifier_last_presented_pos is None:
            return
        if self._magnifier_last_source_image.isNull():
            return
        delta = QPoint(viewport_pos - self._magnifier_last_presented_pos)
        if delta.manhattanLength() < 1:
            return
        dpr = max(1.0, float(self._magnifier_last_source_dpr))
        shift_x = int(round(float(-delta.x()) * dpr))
        shift_y = int(round(float(-delta.y()) * dpr))
        src = self._magnifier_last_source_image
        shifted = QImage(src.size(), QImage.Format.Format_ARGB32_Premultiplied)
        shifted.fill(QColor("#f0f0f0"))
        painter = QPainter(shifted)
        painter.drawImage(shift_x, shift_y, src)
        painter.end()
        self._present_magnifier_source(shifted, dpr, self._magnifier_last_lens_d, quality="fast", viewport_pos=viewport_pos)
        self._magnifier_last_source_image = shifted
        self._magnifier_last_presented_pos = QPoint(viewport_pos)

    def _update_renderer_cache_limit(self, visible_indexes: list[int], refresh_ms: float) -> None:
        if refresh_ms <= 0:
            return
        if self._cache_refresh_cost_ema_ms <= 0:
            self._cache_refresh_cost_ema_ms = float(refresh_ms)
        else:
            self._cache_refresh_cost_ema_ms = 0.75 * self._cache_refresh_cost_ema_ms + 0.25 * float(refresh_ms)
        dpr = self._target_cache_dpr()
        total_pixels = 0.0
        for idx in visible_indexes:
            if 0 <= idx < len(self._page_rects):
                rect = self._page_rects[idx]
                total_pixels += float(rect.width()) * float(rect.height()) * dpr * dpr
        megapixels = total_pixels / 1_000_000.0
        if megapixels >= 10.0:
            target = 12
        elif megapixels >= 6.0:
            target = 16
        elif megapixels >= 3.0:
            target = 20
        else:
            target = 24
        if self._cache_refresh_cost_ema_ms > 52.0:
            target -= 4
        elif self._cache_refresh_cost_ema_ms < 22.0:
            target += 2
        target = max(int(self._renderer_cache_limit_min), min(int(self._renderer_cache_limit_max), int(target)))
        self._renderer_cache_limit = target

    def _position_magnifier_label(self, viewport_pos: QPoint) -> None:
        radius = self._magnifier_size // 2
        top_left = QPoint(viewport_pos.x() - radius, viewport_pos.y() - radius)
        # Do not clamp to viewport; viewport clipping should reveal half/quarter disk near page edges.
        self._magnifier_label.move(top_left)

    def _request_magnifier_render(self, viewport_pos: QPoint, dpr_override: float | None = None, is_hq: bool = False) -> None:
        self._ensure_magnifier_render_worker()
        content_pos = self._content_pos(viewport_pos)
        hit = self._locate_page_at(content_pos, allow_outside=True)
        if hit is None:
            self._magnifier_label.hide()
            return
        page_index, page_rect, rel_x, rel_y = hit
        if page_index < 0 or page_index >= len(self._page_svg_files):
            self._magnifier_label.hide()
            return
        if not self._page_svg_files[page_index]:
            self._ensure_page_renderer(page_index)
        self._touch_renderer(page_index)
        keep = self._visible_window_indexes(radius=1)
        keep.add(page_index)
        self._evict_renderer_cache(protected=keep)
        svg_path = self._page_svg_files[page_index] if page_index < len(self._page_svg_files) else ""
        if not svg_path:
            self._magnifier_label.hide()
            return
        dpr = max(1.0, float(dpr_override if dpr_override is not None else self._target_magnifier_dpr()))
        self._magnifier_output_dpr = dpr
        lens_d = self._magnifier_size - 16
        render_side = max(1, int(round(float(lens_d) * dpr)))
        scale = max(1.0, self._magnifier_zoom) * max(1.0, self._magnifier_oversample)
        req_key = (int(page_index), bool(is_hq))
        payload = {
            "key": req_key,
            "svg_path": svg_path,
            "rel_x": float(rel_x),
            "rel_y": float(rel_y),
            "page_w": float(page_rect.width()),
            "page_h": float(page_rect.height()),
            "render_side": int(render_side),
            "scale": float(scale),
            "dpr": float(dpr),
            "lens_d": int(lens_d),
            "viewport_pos": QPoint(viewport_pos),
            "is_hq": bool(is_hq),
        }
        if req_key in self._magnifier_inflight_keys:
            self._magnifier_deferred_by_key[req_key] = payload
            return
        self._dispatch_magnifier_payload(payload)

    def _dispatch_magnifier_payload(self, payload: dict) -> None:
        self._magnifier_request_seq += 1
        token = int(self._magnifier_request_seq)
        key = tuple(payload.get("key") or (0, False))
        self._magnifier_inflight_keys.add(key)
        self._magnifier_request_keys[token] = key
        self._magnifier_request_positions[token] = QPoint(payload["viewport_pos"])
        self._magnifier_request_meta[token] = (int(payload["lens_d"]), float(payload["dpr"]))
        self._magnifier_render_request.emit(
            token,
            str(payload["svg_path"]),
            float(payload["rel_x"]),
            float(payload["rel_y"]),
            float(payload["page_w"]),
            float(payload["page_h"]),
            int(payload["render_side"]),
            float(payload["scale"]),
            float(payload["dpr"]),
            bool(payload["is_hq"]),
        )

    @pyqtSlot(int, QImage, float, bool)
    def _on_magnifier_render_finished(self, token: int, source_image: QImage, dpr: float, _is_hq: bool) -> None:
        pos = self._magnifier_request_positions.pop(int(token), None)
        meta = self._magnifier_request_meta.pop(int(token), None)
        key = self._magnifier_request_keys.pop(int(token), None)
        if key is not None:
            self._magnifier_inflight_keys.discard(key)
            deferred = self._magnifier_deferred_by_key.pop(key, None)
            if deferred is not None:
                self._dispatch_magnifier_payload(deferred)
        if pos is None or meta is None:
            return
        if not self._magnifier_active:
            return
        if int(token) < int(self._magnifier_last_applied_seq):
            return
        if source_image.isNull():
            return
        lens_d = int(meta[0])
        use_dpr = max(1.0, float(dpr))
        quality = "hq" if bool(_is_hq) else "fast"
        self._present_magnifier_source(source_image, use_dpr, lens_d, quality=quality, viewport_pos=pos)
        self._magnifier_last_source_image = source_image
        self._magnifier_last_source_dpr = use_dpr
        self._magnifier_last_lens_d = lens_d
        self._magnifier_last_presented_pos = QPoint(pos)
        if bool(_is_hq):
            self._magnifier_last_hq_pos = QPoint(pos)
            self._magnifier_last_hq_dpr = use_dpr
            self._magnifier_hq_cooldown_until = time.perf_counter() + 0.12
        self._magnifier_last_applied_seq = int(token)

    def _queue_magnifier_update(self, viewport_pos: QPoint) -> None:
        viewport_pos = self._clamp_magnifier_center_to_page(viewport_pos)
        if self._magnifier_last_viewport_pos is not None:
            if (viewport_pos - self._magnifier_last_viewport_pos).manhattanLength() < self._magnifier_min_move_px:
                return
        self._predictive_magnifier_reuse(viewport_pos)
        self._pending_magnifier_pos = QPoint(viewport_pos)
        self._pending_magnifier_hq_pos = None
        self._magnifier_hq_timer.stop()
        if not self._magnifier_update_timer.isActive():
            self._magnifier_update_timer.start()

    def _flush_magnifier_update(self) -> None:
        if self._pending_magnifier_pos is None or not self._magnifier_active:
            return
        pos = QPoint(self._pending_magnifier_pos)
        self._magnifier_last_viewport_pos = QPoint(pos)
        self._request_magnifier_render(pos, dpr_override=self._target_magnifier_dpr(), is_hq=True)

    def _flush_magnifier_hq(self) -> None:
        return

    def _handle_mouse_press(self, event: QMouseEvent) -> None:
        vp = event.position().toPoint() - QPoint(self.horizontalScrollBar().value(), self.verticalScrollBar().value())
        if event.button() == Qt.MouseButton.LeftButton:
            vp = self._clamp_magnifier_center_to_page(vp)
            self._magnifier_active = True
            self._hide_magnifier_cursor()
            self._pending_magnifier_pos = QPoint(vp)
            self._pending_magnifier_hq_pos = None
            self._request_magnifier_render(
                vp,
                dpr_override=self._target_magnifier_dpr(),
                is_hq=True,
            )
            self._magnifier_hq_timer.stop()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._pan_active = True
            self._pan_dragged = False
            self._pan_start_pos = vp
            self._pan_start_h = self.horizontalScrollBar().value()
            self._pan_start_v = self.verticalScrollBar().value()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            self._magnifier_label.hide()
            event.accept()
            return

    def _show_context_menu(self, viewport_pos: QPoint, global_pos: QPoint) -> None:
        menu = QMenu(self)
        jump_action = QAction("跳转到源", menu)
        zoom_in_action = QAction("放大", menu)
        zoom_out_action = QAction("缩小", menu)
        menu.addAction(jump_action)
        menu.addAction(zoom_in_action)
        menu.addAction(zoom_out_action)
        chosen = menu.exec(global_pos)
        if chosen is jump_action:
            hit = self._locate_page_at(self._content_pos(viewport_pos))
            if hit is None:
                return
            idx, _rect, rel_x, rel_y = hit
            page_w, page_h = self._page_sizes[idx]
            self.syncJumpRequested.emit(idx + 1, float(rel_x) * float(page_w), float(rel_y) * float(page_h))
            return
        current = self.zoomFactor()
        if chosen is zoom_in_action:
            self._zoom_at(viewport_pos, current + 0.18)
        elif chosen is zoom_out_action:
            self._zoom_at(viewport_pos, current - 0.18)

    def _zoom_at(self, viewport_pos: QPoint, factor: float) -> None:
        content_before = self._content_pos(viewport_pos)
        hit = self._locate_page_at(content_before)
        self.setZoomFactor(factor)
        if hit is None:
            return
        index, _rect, rel_x, rel_y = hit
        if index >= len(self._page_rects):
            return
        rect = self._page_rects[index]
        target = QPoint(
            int(round(rect.x() + rel_x * rect.width() - viewport_pos.x())),
            int(round(rect.y() + rel_y * rect.height() - viewport_pos.y())),
        )
        self.horizontalScrollBar().setValue(max(0, target.x()))
        self.verticalScrollBar().setValue(max(0, target.y()))

    def _handle_mouse_move(self, event: QMouseEvent) -> None:
        vp = event.position().toPoint() - QPoint(self.horizontalScrollBar().value(), self.verticalScrollBar().value())
        if self._pan_active:
            delta = vp - self._pan_start_pos
            if not self._pan_dragged and delta.manhattanLength() > 4:
                self._pan_dragged = True
            self.horizontalScrollBar().setValue(self._pan_start_h - delta.x())
            self.verticalScrollBar().setValue(self._pan_start_v - delta.y())
            event.accept()
            return
        if self._magnifier_active:
            self._queue_magnifier_update(vp)
            event.accept()

    def _handle_mouse_release(self, event: QMouseEvent) -> None:
        vp = event.position().toPoint() - QPoint(self.horizontalScrollBar().value(), self.verticalScrollBar().value())
        if event.button() == Qt.MouseButton.LeftButton and self._magnifier_active:
            self._magnifier_active = False
            self._magnifier_update_timer.stop()
            self._magnifier_hq_timer.stop()
            self._pending_magnifier_pos = None
            self._pending_magnifier_hq_pos = None
            self._magnifier_last_viewport_pos = None
            self._magnifier_request_positions.clear()
            self._magnifier_request_meta.clear()
            self._magnifier_request_keys.clear()
            self._magnifier_inflight_keys.clear()
            self._magnifier_deferred_by_key.clear()
            self._magnifier_last_source_image = QImage()
            self._magnifier_last_source_dpr = 1.0
            self._magnifier_last_lens_d = self._magnifier_size - 16
            self._magnifier_last_presented_pos = None
            self._magnifier_last_hq_pos = None
            self._magnifier_last_hq_dpr = 0.0
            self._magnifier_hq_cooldown_until = 0.0
            self._magnifier_label.hide()
            self._restore_magnifier_cursor()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton and self._pan_active:
            dragged = self._pan_dragged
            self._pan_active = False
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor if dragged else self._magnifier_cursor)
            if not dragged:
                self._show_context_menu(vp, event.globalPosition().toPoint())
            event.accept()

    def _handle_leave(self, event) -> None:
        if not self._pan_active and not self._magnifier_active:
            self._magnifier_update_timer.stop()
            self._magnifier_hq_timer.stop()
            self._pending_magnifier_pos = None
            self._pending_magnifier_hq_pos = None
            self._magnifier_last_viewport_pos = None
            self._magnifier_request_positions.clear()
            self._magnifier_request_meta.clear()
            self._magnifier_request_keys.clear()
            self._magnifier_inflight_keys.clear()
            self._magnifier_deferred_by_key.clear()
            self._magnifier_last_source_image = QImage()
            self._magnifier_last_source_dpr = 1.0
            self._magnifier_last_lens_d = self._magnifier_size - 16
            self._magnifier_last_presented_pos = None
            self._magnifier_last_hq_pos = None
            self._magnifier_last_hq_dpr = 0.0
            self._magnifier_hq_cooldown_until = 0.0
            self._magnifier_label.hide()
            self._restore_magnifier_cursor()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            step = 0.18 if delta > 0 else -0.18
            self._zoom_at(event.position().toPoint(), self.zoomFactor() + step)
            event.accept()
            return
        super().wheelEvent(event)
