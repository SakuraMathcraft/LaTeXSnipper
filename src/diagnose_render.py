#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LaTeXSnipper 渲染问题诊断工具

用途：诊断打包后 MathJax 渲染失败的原因
"""

import os
import sys
from pathlib import Path
import json

def diagnose():
    """诊断渲染问题"""
    
    print("=" * 70)
    print("LaTeXSnipper 渲染诊断工具")
    print("=" * 70)
    
    # 1. 检查 APP_DIR
    print("\n【检查 APP_DIR】")
    try:
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后
            app_dir = Path(sys.executable).parent
            print(f"✓ 运行模式: 打包模式（PyInstaller）")
        else:
            # 开发模式
            app_dir = Path(__file__).parent
            print(f"✓ 运行模式: 开发模式")
        
        print(f"  APP_DIR = {app_dir}")
    except Exception as e:
        print(f"✗ 获取 APP_DIR 失败: {e}")
        return False
    
    # 2. 检查资源文件结构
    print("\n【检查资源文件结构】")
    
    expected_paths = {
        "assets": app_dir / "assets",
        "MathJax-3.2.2": app_dir / "assets" / "MathJax-3.2.2",
        "es5": app_dir / "assets" / "MathJax-3.2.2" / "es5",
        "tex-mml-chtml.js": app_dir / "assets" / "MathJax-3.2.2" / "es5" / "tex-mml-chtml.js",
        "core.js": app_dir / "assets" / "MathJax-3.2.2" / "es5" / "core.js",
        "loader.js": app_dir / "assets" / "MathJax-3.2.2" / "es5" / "loader.js",
    }
    
    missing = []
    for name, path in expected_paths.items():
        exists = path.exists()
        status = "✓" if exists else "✗"
        print(f"  {status} {name}: {path}")
        if not exists:
            missing.append(name)
    
    if missing:
        print(f"\n⚠️  缺失的文件: {', '.join(missing)}")
    else:
        print(f"\n✓ 所有资源文件完整")
    
    # 3. 检查 PyQt6 WebEngine
    print("\n【检查 PyQt6.QtWebEngineWidgets】")
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        print("✓ PyQt6.QtWebEngineWidgets 可用")
    except ImportError as e:
        print(f"✗ PyQt6.QtWebEngineWidgets 导入失败: {e}")
        return False
    
    # 4. 检查 MathJax 文件大小
    print("\n【检查 MathJax 文件大小】")
    try:
        tex_chtml = app_dir / "assets" / "MathJax-3.2.2" / "es5" / "tex-mml-chtml.js"
        if tex_chtml.exists():
            size_mb = tex_chtml.stat().st_size / (1024 * 1024)
            print(f"✓ tex-mml-chtml.js: {size_mb:.2f} MB")
            
            if size_mb < 0.1:
                print("⚠️  文件过小，可能是空文件或损坏")
                return False
        else:
            print(f"✗ tex-mml-chtml.js 不存在: {tex_chtml}")
            return False
    except Exception as e:
        print(f"✗ 检查文件大小失败: {e}")
        return False
    
    # 5. 列出 es5 目录中的文件
    print("\n【es5 目录文件清单】")
    try:
        es5_dir = app_dir / "assets" / "MathJax-3.2.2" / "es5"
        if es5_dir.exists():
            js_files = list(es5_dir.glob("*.js"))
            print(f"  找到 {len(js_files)} 个 JS 文件:")
            for js_file in sorted(js_files)[:10]:  # 只显示前 10 个
                size_kb = js_file.stat().st_size / 1024
                print(f"    - {js_file.name} ({size_kb:.1f} KB)")
            if len(js_files) > 10:
                print(f"    ... 还有 {len(js_files) - 10} 个文件")
        else:
            print(f"✗ es5 目录不存在: {es5_dir}")
            return False
    except Exception as e:
        print(f"✗ 列出文件失败: {e}")
        return False
    
    # 6. 检查 PyInstaller spec 配置
    print("\n【检查 PyInstaller 打包配置】")
    try:
        spec_file = Path(__file__).parent.parent / "LaTeXSnipper.spec"
        if spec_file.exists():
            with open(spec_file, 'r', encoding='utf-8') as f:
                spec_content = f.read()
            
            # 检查关键配置
            checks = [
                ("资源文件打包", "(str(SRC / 'assets'), 'assets')" in spec_content),
                ("MathJax 配置", "'assets/MathJax" in spec_content or 'MathJax' in spec_content),
                ("WebEngine 导入", "'PyQt6.QtWebEngineWidgets'" in spec_content or 'QtWebEngine' in spec_content),
            ]
            
            for check_name, result in checks:
                status = "✓" if result else "✗"
                print(f"  {status} {check_name}")
            
            if not all(r for _, r in checks):
                print("\n⚠️  spec 文件配置可能不完整，需要更新")
        else:
            print(f"✗ spec 文件不存在: {spec_file}")
    except Exception as e:
        print(f"✗ 检查 spec 文件失败: {e}")
    
    # 7. 尝试加载 MathJax
    print("\n【尝试加载 MathJax】")
    try:
        from PyQt6.QtCore import QUrl
        
        es5_dir = app_dir / "assets" / "MathJax-3.2.2" / "es5"
        url = QUrl.fromLocalFile(str(es5_dir) + "/")
        url_str = url.toString()
        
        print(f"✓ 生成的 URL: {url_str}")
        
        # 检查 URL 是否有效
        if url_str.startswith("file://"):
            print("✓ 使用本地文件 URL 格式")
        else:
            print("⚠️  URL 格式不是 file://")
    except Exception as e:
        print(f"✗ 加载 MathJax 失败: {e}")
        return False
    
    print("\n" + "=" * 70)
    print("诊断完成")
    print("=" * 70)
    
    if missing:
        print("\n建议:")
        print("1. 确保打包时包含了 assets/MathJax-3.2.2 目录")
        print("2. 检查 LaTeXSnipper.spec 中的 datas 配置")
        print("3. 重新运行: pyinstaller LaTeXSnipper.spec")
        return False
    else:
        print("\n✓ 诊断完成，未发现问题")
        return True

if __name__ == "__main__":
    success = diagnose()
    sys.exit(0 if success else 1)
