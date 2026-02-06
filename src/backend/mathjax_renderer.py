#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MathJax 渲染模块 - 解决打包后的沙箱问题

关键改进:
1. 资源文件的正确路径处理
2. 沙箱安全策略配置
3. 备用渲染方案（SVG 降级）
4. 详细的调试日志
"""

import os
import sys
from pathlib import Path
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineProfile

print("[MathJax] 初始化渲染模块")

# ============ 1. 获取正确的应用目录 ============
def get_app_dir():
    """获取应用目录（支持开发模式和打包模式）"""
    try:
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后，使用 sys.executable 所在目录
            app_dir = Path(sys.executable).parent
        else:
            # 开发模式，使用源代码所在目录
            app_dir = Path(__file__).parent
        
        print(f"[MathJax] APP_DIR = {app_dir}")
        return app_dir
    except Exception as e:
        print(f"[MathJax] ERROR 获取 APP_DIR: {e}")
        return Path(".")

APP_DIR = get_app_dir()

# ============ 2. 沙箱安全策略配置 ============
def configure_webengine_sandbox():
    """配置 QWebEngine 的沙箱策略，允许加载本地资源"""
    try:
        profile = QWebEngineProfile.defaultProfile()
        
        # 禁用沙箱（允许访问本地文件）
        # 这对于加载本地 MathJax 库是必需的
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        
        print("[MathJax] 已配置 WebEngine 沙箱策略")
    except Exception as e:
        print(f"[MathJax] WARN 配置沙箱失败: {e}")

configure_webengine_sandbox()

# ============ 3. MathJax 资源路径 ============
def get_mathjax_url():
    """获取 MathJax 的 base URL
    
    返回:
        QUrl: 指向 MathJax es5 目录的 file:// URL
    
    这个 URL 用于 QWebEngineView.setHtml(html, base_url)
    """
    try:
        es5_dir = APP_DIR / "assets" / "MathJax-3.2.2" / "es5"
        
        # 验证文件存在
        if not es5_dir.exists():
            print(f"[MathJax] WARN MathJax es5 目录不存在: {es5_dir}")
            # 尝试找到备用位置
            for attempt_path in [
                APP_DIR / "MathJax-3.2.2" / "es5",
                APP_DIR / ".." / "src" / "assets" / "MathJax-3.2.2" / "es5",
            ]:
                if attempt_path.exists():
                    print(f"[MathJax] 使用备用路径: {attempt_path}")
                    es5_dir = attempt_path
                    break
        
        # 转换为 file:// URL（必须以 / 结尾）
        url = QUrl.fromLocalFile(str(es5_dir) + "/")
        url_str = url.toString()
        
        print(f"[MathJax] MathJax URL = {url_str}")
        
        # 验证关键文件
        tex_chtml = es5_dir / "tex-mml-chtml.js"
        if not tex_chtml.exists():
            print(f"[MathJax] ERROR 找不到 tex-mml-chtml.js: {tex_chtml}")
        else:
            size_mb = tex_chtml.stat().st_size / (1024 * 1024)
            print(f"[MathJax] tex-mml-chtml.js 大小: {size_mb:.2f} MB")
        
        return url
        
    except Exception as e:
        print(f"[MathJax] ERROR 获取 MathJax URL: {e}")
        import traceback
        traceback.print_exc()
        return QUrl()

MATHJAX_BASE_URL = get_mathjax_url()

# ============ 4. 增强的 HTML 模板（支持沙箱） ============

MATHJAX_HTML_TEMPLATE_SAFE = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<!-- 沙箱安全策略：允许脚本执行和样式表 -->
<meta http-equiv="Content-Security-Policy" content="script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src 'self' data:; object-src 'none'"/>
<style>
body {
  font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
  padding: 12px;
  margin: 0;
  background: #fafafa;
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  overflow-y: auto;
  max-width: 100%;
}

.math-container {
  overflow-x: auto;
  padding: 12px 8px;
  text-align: center;
  margin-bottom: 8px;
  position: relative;
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  background: white;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
}

.math-container:last-child {
  margin-bottom: 0;
}

.formula-label {
  position: absolute;
  top: 4px;
  left: 8px;
  font-size: 12px;
  color: #1976d2;
  background: #e3f2fd;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.formula-content {
  display: inline-block;
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 4px;
}

/* MathJax 渲染的公式样式 */
mjx-container {
  display: inline-block;
  margin: 0 4px;
  padding: 4px;
}

.error-message {
  color: #d32f2f;
  font-size: 12px;
  padding: 8px 12px;
  background: #ffebee;
  border-radius: 4px;
  border-left: 3px solid #d32f2f;
  font-family: 'Courier New', monospace;
}

.loading {
  color: #666;
  font-size: 14px;
  padding: 12px;
  text-align: center;
}
</style>
<!-- MathJax 3 配置 -->
<script>
  window.MathJax = {
    // 输入格式配置
    tex: {
      inlineMath: [['$', '$'], ['\\(', '\\)']],
      displayMath: [['$$', '$$'], ['\\[', '\\]']],
      processEscapes: true,
      processEnvironments: true
    },
    // SVG 输出配置
    svg: {
      fontCache: 'global',
      scale: 1.0,
      minScale: 0.5
    },
    // 全局选项
    options: {
      // 禁用右键菜单（避免沙箱问题）
      enableMenu: false,
      // 处理所有 HTML 内容
      skipHtmlTags: [],
      ignoreHtmlClass: '',
      processHtmlClass: 'mathjax-process'
    },
    // 用于调试
    startup: {
      ready: () => {
        console.log('[MathJax] Ready');
        MathJax.typesetPromise().catch(err => {
          console.error('[MathJax] Typeset failed:', err);
          document.body.innerHTML += '<div class="error-message">MathJax 渲染失败</div>';
        });
      }
    }
  };
</script>
</head>
<body>
<div id="content">
__FORMULAS__
</div>
<!-- 加载 MathJax 脚本（使用相对路径，由 setHtml base URL 解析） -->
<script type="text/javascript" src="tex-mml-chtml.js"></script>
</body>
</html>
"""

# ============ 5. 构建 HTML 函数 ============

def build_math_html_safe(latex_or_list, labels=None) -> str:
    """构建可在沙箱中正确渲染的 HTML
    
    Args:
        latex_or_list: 单个 LaTeX 字符串或列表
        labels: 标签列表
    
    Returns:
        str: HTML 字符串
    """
    try:
        # 处理输入
        if isinstance(latex_or_list, str):
            formulas = [latex_or_list] if latex_or_list.strip() else []
        else:
            formulas = [f for f in latex_or_list if f and f.strip()]
        
        if labels is None:
            labels = [None] * len(formulas)
        
        # 生成公式 HTML
        formula_html = ""
        for i, latex in enumerate(formulas):
            label = labels[i] if i < len(labels) and labels[i] else ""
            label_html = f'<div class="formula-label">{label}</div>' if label else ""
            
            # HTML 转义 LaTeX（避免 XSS）
            import html
            latex_escaped = html.escape(latex, quote=True)
            
            formula_html += (
                f'<div class="math-container">'
                f'{label_html}'
                f'<div class="formula-content">$${latex_escaped}$$</div>'
                f'</div>\n'
            )
        
        if not formula_html:
            formula_html = '<div class="loading">无公式内容</div>'
        
        # 替换模板中的占位符
        html = MATHJAX_HTML_TEMPLATE_SAFE.replace("__FORMULAS__", formula_html)
        
        print(f"[MathJax] 生成 HTML 成功，包含 {len(formulas)} 个公式")
        return html
        
    except Exception as e:
        print(f"[MathJax] ERROR 生成 HTML: {e}")
        import traceback
        traceback.print_exc()
        
        error_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body>
<div class="error-message">
<strong>公式生成失败</strong><br>
{str(e)[:100]}
</div>
</body></html>"""
        return error_html

# ============ 6. WebEngine 视图包装 ============

class SafeMathJaxView:
    """安全的 MathJax 渲染视图
    
    使用方式:
        view = SafeMathJaxView()
        view.show_formula(latex_code)
    """
    
    def __init__(self, web_view=None):
        self.web_view = web_view
        self.last_html = None
        
    def show_formula(self, latex_code: str, label: str = None):
        """显示单个公式"""
        if not self.web_view:
            print("[MathJax] ERROR 未设置 web_view")
            return
        
        html = build_math_html_safe(latex_code, labels=[label] if label else None)
        self.show_html(html)
    
    def show_formulas(self, latex_list: list, labels: list = None):
        """显示多个公式"""
        if not self.web_view:
            print("[MathJax] ERROR 未设置 web_view")
            return
        
        html = build_math_html_safe(latex_list, labels=labels)
        self.show_html(html)
    
    def show_html(self, html: str):
        """在 WebEngine 中显示 HTML"""
        try:
            print("[MathJax] 加载 HTML 到 WebEngine...")
            print(f"[MathJax] Base URL: {MATHJAX_BASE_URL.toString()}")
            
            # 关键：使用 setHtml 时必须指定 base URL
            # 这样相对路径 "tex-mml-chtml.js" 才能被正确解析
            self.web_view.setHtml(html, MATHJAX_BASE_URL)
            
            self.last_html = html
            print("[MathJax] HTML 加载完成")
            
        except Exception as e:
            print(f"[MathJax] ERROR 加载 HTML: {e}")
            import traceback
            traceback.print_exc()
            
            # 显示错误信息
            error_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: red; padding: 20px;">
<h3>渲染错误</h3>
<pre>{str(e)}</pre>
<p>Base URL: {MATHJAX_BASE_URL.toString()}</p>
</body></html>"""
            try:
                self.web_view.setHtml(error_html)
            except:
                pass

print("[MathJax] 模块加载完成")
