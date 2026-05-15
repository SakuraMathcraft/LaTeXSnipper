import os
import shutil

from ui.settings_dialog_helpers import _select_open_file_with_icon


class SettingsLatexMixin:

    def _compiler_for_engine(self, engine: str) -> str:
        return "xelatex" if str(engine or "").strip() == "latex_xelatex" else "pdflatex"

    def _sync_latex_path_for_engine(self, engine: str) -> None:
        if not str(engine or "").startswith("latex_"):
            return
        target = self._compiler_for_engine(engine)
        target_exe = f"{target}.exe"
        other_exe = "pdflatex.exe" if target == "xelatex" else "xelatex.exe"
        current_path = (self.latex_path_input.text() or "").strip()
        if current_path:
            base = os.path.basename(current_path).lower()
            if base == other_exe:
                self.latex_path_input.setText(os.path.join(os.path.dirname(current_path), target_exe))
            return
        candidate = shutil.which(target) or target_exe
        if candidate:
            self.latex_path_input.setText(candidate)

    def _init_render_engine(self):
        """Initialize render-engine selection."""
        try:
            from backend.latex_renderer import _latex_settings, LaTeXRenderer, TypstRenderer
            if _latex_settings:
                mode = _latex_settings.get_render_mode()
                self.render_engine_combo.currentIndexChanged.disconnect(self._on_render_engine_changed)
                # Find the matching index from _render_modes.
                if mode in self._render_modes:
                    index = self._render_modes.index(mode)
                    self.render_engine_combo.setCurrentIndex(index)
                else:
                    # Default to auto detection.
                    self.render_engine_combo.setCurrentIndex(0)
                self.render_engine_combo.currentIndexChanged.connect(self._on_render_engine_changed)
                current_index = self.render_engine_combo.currentIndex()
                if current_index >= 0 and current_index < len(self._render_modes):
                    engine = self._render_modes[current_index]
                    is_latex = engine.startswith("latex_")
                    is_typst = engine == "typst"
                    self.latex_options_widget.setVisible(is_latex)
                    self.typst_options_widget.setVisible(is_typst)
                    # Try auto detection in LaTeX mode.
                    if is_latex and not _latex_settings.get_latex_path():
                        renderer = LaTeXRenderer()
                        if renderer.is_available():
                            self.latex_path_input.setText(renderer.latex_cmd)
                            _latex_settings.set_latex_path(renderer.latex_cmd)
                            _latex_settings.save()
                    # Try auto detection in Typst mode.
                    if is_typst and not _latex_settings.get_typst_path():
                        renderer = TypstRenderer()
                        if renderer.is_available():
                            self.typst_path_input.setText(renderer.typst_cmd)
                            _latex_settings.set_typst_path(renderer.typst_cmd)
                            _latex_settings.save()
        except Exception as e:
            print(f"[WARN] 初始化渲染引擎失败: {e}")

    def _on_render_engine_changed(self, index: int):
        """Handle render-engine changes immediately without heavy validation on the UI thread."""
        if index < 0:
            return
        # Read the engine data from _render_modes.
        if index < 0 or index >= len(self._render_modes):
            print(f"[WARN] 渲染引擎索引无效: {index}")
            return
        engine = self._render_modes[index]
        # Show or hide LaTeX/Typst options.
        is_latex = engine.startswith("latex_")
        is_typst = engine == "typst"
        self.latex_options_widget.setVisible(is_latex)
        self.typst_options_widget.setVisible(is_typst)
        if is_latex:
            self._sync_latex_path_for_engine(engine)
            latex_path = self.latex_path_input.text().strip()
            if not latex_path:
                self._show_notification("warning", "LaTeX 路径未配置", '已切换引擎。请点击"自动检测"或手动选择路径，再点"验证路径"。')
        if is_typst:
            typst_path = self.typst_path_input.text().strip()
            if not typst_path:
                # Try auto-detect on switch
                try:
                    from backend.latex_renderer import TypstRenderer
                    renderer = TypstRenderer()
                    if renderer.is_available():
                        self.typst_path_input.setText(renderer.typst_cmd)
                except Exception:
                    pass
            if not self.typst_path_input.text().strip():
                self._show_notification("warning", "Typst 路径未配置", '已切换引擎。请点击"自动检测"或手动选择路径，再点"验证路径"。')

        # Save engine changes immediately; expensive validation is triggered by the path validation button.
        self._save_render_mode(engine)

    def _load_latex_settings(self):
        """Load LaTeX and Typst settings."""
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                latex_path = _latex_settings.get_latex_path()
                if latex_path:
                    self.latex_path_input.setText(latex_path)
                typst_path = _latex_settings.get_typst_path()
                if typst_path:
                    self.typst_path_input.setText(typst_path)
        except Exception as e:
            print(f"[WARN] 加载 LaTeX 设置失败: {e}")

    def _on_latex_path_changed(self):
        """Handle LaTeX path changes by clearing validation state."""
        if getattr(self, "_latex_test_in_progress", False):
            return
        self.btn_test_latex.setText("验证路径")
        self.btn_test_latex.setEnabled(True)

    def _browse_latex_path(self):
        """Browse for a LaTeX executable path."""
        file_path, _ = _select_open_file_with_icon(
            self,
            "选择 pdflatex 或 xelatex 可执行文件",
            "",
            "可执行文件 (pdflatex.exe xelatex.exe);;所有文件 (*.*)"
        )
        if file_path:
            self.latex_path_input.setText(file_path)
            self._save_latex_settings()

    def _detect_latex(self):
        """Detect LaTeX asynchronously, checking both pdflatex and xelatex."""
        if getattr(self, "_latex_detect_in_progress", False):
            return

        self._latex_detect_in_progress = True
        self.btn_detect_latex.setText("检测中...")
        self.btn_detect_latex.setEnabled(False)

        # Use the current render-engine selection as the detection preference; infer from the current path outside LaTeX mode.
        current_engine = ""
        idx = self.render_engine_combo.currentIndex()
        if 0 <= idx < len(self._render_modes):
            current_engine = self._render_modes[idx]
        if current_engine == "latex_xelatex":
            selected_compiler = "xelatex"
        elif current_engine == "latex_pdflatex":
            selected_compiler = "pdflatex"
        else:
            base = os.path.basename((self.latex_path_input.text() or "").strip()).lower()
            selected_compiler = "xelatex" if base == "xelatex.exe" else "pdflatex"
        current_path = self.latex_path_input.text().strip()

        def worker(preferred: str, current: str):
            candidates = {
                "pdflatex": (shutil.which("pdflatex") or "").strip(),
                "xelatex": (shutil.which("xelatex") or "").strip(),
            }

            # If PATH misses, infer the sibling compiler from the current path directory.
            try:
                if current:
                    base_dir = os.path.dirname(current)
                    if base_dir and os.path.isdir(base_dir):
                        pdflatex_exe = os.path.join(base_dir, "pdflatex.exe")
                        xelatex_exe = os.path.join(base_dir, "xelatex.exe")
                        if (not candidates["pdflatex"]) and os.path.exists(pdflatex_exe):
                            candidates["pdflatex"] = pdflatex_exe
                        if (not candidates["xelatex"]) and os.path.exists(xelatex_exe):
                            candidates["xelatex"] = xelatex_exe
            except Exception:
                pass

            chosen = ""
            if candidates.get(preferred):
                chosen = candidates[preferred]
            elif candidates.get("pdflatex"):
                chosen = candidates["pdflatex"]
            elif candidates.get("xelatex"):
                chosen = candidates["xelatex"]

            pd = candidates.get("pdflatex") or "未找到"
            xe = candidates.get("xelatex") or "未找到"
            detail = f"pdflatex: {pd}\nxelatex: {xe}"
            self.latex_auto_detect_done.emit(bool(chosen), chosen, detail)

        import threading
        threading.Thread(target=worker, args=(selected_compiler, current_path), daemon=True).start()

    def _on_latex_auto_detect_done(self, ok: bool, latex_path: str, detail: str):
        self._latex_detect_in_progress = False
        self.btn_detect_latex.setText("自动检测")
        self.btn_detect_latex.setEnabled(True)

        if ok:
            self.latex_path_input.setText(str(latex_path or ""))
            self._save_latex_settings()
            self._show_notification("success", "检测成功", detail)
        else:
            self._show_notification("warning", "检测失败", f"未检测到 LaTeX。\n\n{detail}")

    def _save_latex_settings(self):
        """Save LaTeX and Typst settings."""
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                latex_path = self.latex_path_input.text().strip()
                typst_path = self.typst_path_input.text().strip()
                mode = "auto"
                idx = self.render_engine_combo.currentIndex()
                if 0 <= idx < len(self._render_modes):
                    mode = self._render_modes[idx]
                if mode == "latex_xelatex":
                    use_xelatex = True
                elif mode == "latex_pdflatex":
                    use_xelatex = False
                else:
                    use_xelatex = os.path.basename(latex_path).lower() == "xelatex.exe"
                if latex_path:
                    _latex_settings.set_latex_path(latex_path)
                    _latex_settings.settings["use_xelatex"] = use_xelatex
                    print(f"[LaTeX] 设置已保存: {latex_path}")
                if typst_path:
                    _latex_settings.set_typst_path(typst_path)
                    print(f"[Typst] 设置已保存: {typst_path}")
        except Exception as e:
            print(f"[WARN] 保存 LaTeX 设置失败: {e}")

    def _test_latex_path(self):
        """Test the LaTeX path asynchronously to avoid blocking the UI thread."""
        latex_path = self.latex_path_input.text().strip()
        if not latex_path:
            self._show_notification("error", "路径为空", "请输入 LaTeX 路径或点击自动检测")
            return False
        if getattr(self, "_latex_test_in_progress", False):
            return False

        current_index = self.render_engine_combo.currentIndex()
        engine = self._render_modes[current_index] if 0 <= current_index < len(self._render_modes) else "auto"
        self._latex_test_in_progress = True
        self.btn_test_latex.setText("验证中...")
        self.btn_test_latex.setEnabled(False)

        def worker(path_value: str, engine_value: str):
            from backend.latex_renderer import LaTeXRenderer

            ok = False
            title = "验证失败"
            message = "无法用该路径渲染公式，请检查安装"
            try:
                renderer = LaTeXRenderer(path_value)
                if not renderer.is_available():
                    title = "路径无效"
                    message = "找不到 LaTeX 可执行文件"
                else:
                    print(f"[LaTeX] 测试路径: {path_value}")
                    test_svg = renderer.render_to_svg(r"\frac{1}{2} + \frac{1}{3} = \frac{5}{6}")
                    if test_svg and len(test_svg) > 100:
                        ok = True
                        title = "验证成功"
                        message = "LaTeX 环境已就绪"
            except Exception as e:
                print(f"[ERROR] LaTeX 验证失败: {e}")
                title = "验证出错"
                message = str(e)[:100]
            self.latex_path_test_done.emit(bool(ok), str(title), str(message), str(engine_value), str(path_value))

        import threading

        threading.Thread(target=worker, args=(latex_path, engine), daemon=True).start()
        return True

    def _on_latex_path_test_done(self, ok: bool, title: str, message: str, engine: str, tested_path: str):
        self._latex_test_in_progress = False
        if ok:
            self.btn_test_latex.setText("✓ 已验证")
            self.btn_test_latex.setEnabled(False)
            # Save directly if the path was unchanged during validation; otherwise keep the success state visible.
            try:
                if self.latex_path_input.text().strip() == (tested_path or "").strip():
                    self._save_latex_settings()
            except Exception:
                pass
            compiler = "xelatex" if os.path.basename((tested_path or "").strip()).lower() == "xelatex.exe" else "pdflatex"
            self._show_notification("success", title or "验证成功", f"已验证编译器: {compiler}\n路径: {tested_path or ''}")
            return
        self.btn_test_latex.setText("验证路径")
        self.btn_test_latex.setEnabled(True)
        self._show_notification("error", title or "验证失败", message or "无法用该路径渲染公式，请检查安装")

    def _show_notification(self, level: str, title: str, message: str):
        """Show a floating notification."""
        try:
            from qfluentwidgets import InfoBar, InfoBarPosition
            # Call the matching method for the requested level.
            if level == "success":
                InfoBar.success(
                    title=title,
                    content=message,
                    orient=None,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
            elif level == "warning":
                InfoBar.warning(
                    title=title,
                    content=message,
                    orient=None,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
            elif level == "error":
                InfoBar.error(
                    title=title,
                    content=message,
                    orient=None,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
            else:
                InfoBar.info(
                    title=title,
                    content=message,
                    orient=None,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
        except Exception as e:
            print(f"[WARN] 显示通知失败: {e}")
            print(f"[INFO] {title}: {message}")

    def _save_render_mode(self, engine: str):
        """Save the render-engine selection."""
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                _latex_settings.set_render_mode(engine)
                print(f"[Render] 已切换渲染引擎: {engine}")
                # Show success through a floating InfoBar instead of MessageBox.
                mode_names = {
                    "auto": "自动检测（推荐）",
                    "mathjax_local": "本地 MathJax",
                    "mathjax_cdn": "CDN MathJax",
                    "latex_pdflatex": "LaTeX + pdflatex",
                    "latex_xelatex": "LaTeX + xelatex",
                    "typst": "Typst",
                }
                if engine in mode_names:
                    self._show_notification(
                        "success",
                        "切换成功",
                        f"已切换到: {mode_names[engine]}"
                    )
        except Exception as e:
            print(f"[ERROR] 保存渲染模式失败: {e}")

    # ------------------------------------------------------------------
    # Typst path & validation methods
    # ------------------------------------------------------------------

    def _on_typst_path_changed(self):
        """Handle Typst path changes by clearing validation state."""
        if getattr(self, "_typst_test_in_progress", False):
            return
        self.btn_test_typst.setText("验证路径")
        self.btn_test_typst.setEnabled(True)

    def _browse_typst_path(self):
        """Browse for a Typst executable path."""
        import sys
        if sys.platform == "win32":
            file_filter = "可执行文件 (typst.exe);;所有文件 (*.*)"
        else:
            file_filter = "所有文件 (*)"
        file_path, _ = _select_open_file_with_icon(
            self,
            "选择 Typst 可执行文件",
            "",
            file_filter,
        )
        if file_path:
            self.typst_path_input.setText(file_path)
            self._save_latex_settings()

    def _detect_typst(self):
        """Detect Typst asynchronously."""
        if getattr(self, "_typst_detect_in_progress", False):
            return

        self._typst_detect_in_progress = True
        self.btn_detect_typst.setText("检测中...")
        self.btn_detect_typst.setEnabled(False)

        def worker():
            import shutil as _shutil
            import subprocess as _subprocess
            import os as _os

            found_path = ""
            detail = ""
            try:
                # Try shutil.which first (cross-platform)
                found_path = (_shutil.which("typst") or "").strip()
                if found_path:
                    detail = f"在 PATH 中找到: {found_path}"
                else:
                    # Try common install locations
                    home = _os.path.expanduser("~")
                    candidates = [
                        _os.path.join(home, ".cargo", "bin", "typst"),
                        _os.path.join(home, ".cargo", "bin", "typst.exe"),
                    ]
                    if _os.name == "nt":
                        import platform
                        if platform.machine().endswith("64"):
                            candidates.append(_os.path.join(
                                _os.environ.get("ProgramFiles", "C:\\Program Files"),
                                "typst", "typst.exe"
                            ))
                    for c in candidates:
                        if _os.path.isfile(c):
                            found_path = c
                            detail = f"在常见路径中找到: {c}"
                            break
                    if not found_path:
                        detail = "未找到 Typst。请安装: https://github.com/typst/typst/releases"
            except Exception as e:
                detail = f"检测出错: {e}"

            self.typst_auto_detect_done.emit(bool(found_path), found_path, detail)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _on_typst_auto_detect_done(self, ok: bool, typst_path: str, detail: str):
        self._typst_detect_in_progress = False
        self.btn_detect_typst.setText("自动检测")
        self.btn_detect_typst.setEnabled(True)

        if ok:
            self.typst_path_input.setText(str(typst_path or ""))
            self._save_latex_settings()
            self._show_notification("success", "检测成功", detail)
        else:
            self._show_notification("warning", "检测失败", detail)

    def _test_typst_path(self):
        """Test the Typst path asynchronously."""
        typst_path = self.typst_path_input.text().strip()
        if not typst_path:
            self._show_notification("error", "路径为空", "请输入 Typst 路径或点击自动检测")
            return False
        if getattr(self, "_typst_test_in_progress", False):
            return False

        self._typst_test_in_progress = True
        self.btn_test_typst.setText("验证中...")
        self.btn_test_typst.setEnabled(False)

        def worker(path_value: str):
            from backend.latex_renderer import TypstRenderer

            ok = False
            title = "验证失败"
            message = "无法用该路径渲染公式，请检查安装"
            try:
                renderer = TypstRenderer(path_value)
                if not renderer.is_available():
                    title = "路径无效"
                    message = "找不到 Typst 可执行文件"
                else:
                    print(f"[Typst] 测试路径: {path_value}")
                    test_svg = renderer.render_to_svg(r"\frac{1}{2} + \frac{1}{3} = \frac{5}{6}")
                    if test_svg and len(test_svg) > 100:
                        ok = True
                        title = "验证成功"
                        message = "Typst 环境已就绪"
                    else:
                        message = "Typst 渲染失败，请检查 Typst 安装和 pypandoc 是否可用"
            except Exception as e:
                print(f"[ERROR] Typst 验证失败: {e}")
                title = "验证出错"
                message = str(e)[:100]
            self.typst_path_test_done.emit(bool(ok), str(title), str(message), str(path_value))

        import threading
        threading.Thread(target=worker, args=(typst_path,), daemon=True).start()
        return True

    def _on_typst_path_test_done(self, ok: bool, title: str, message: str, tested_path: str):
        self._typst_test_in_progress = False
        if ok:
            self.btn_test_typst.setText("✓ 已验证")
            self.btn_test_typst.setEnabled(False)
            try:
                if self.typst_path_input.text().strip() == (tested_path or "").strip():
                    self._save_latex_settings()
            except Exception:
                pass
            self._show_notification("success", title or "验证成功", f"Typst 环境已就绪\n路径: {tested_path or ''}")
            return
        self.btn_test_typst.setText("验证路径")
        self.btn_test_typst.setEnabled(True)
        self._show_notification("error", title or "验证失败", message or "无法用该路径渲染公式，请检查安装")
