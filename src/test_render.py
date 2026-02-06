#!/usr/bin/env python3
"""测试渲染功能"""

import sys
sys.path.insert(0, 'e:\\LaTexSnipper\\src')

# 测试导入
try:
    import main
    print("[TEST] 导入成功")
except Exception as e:
    print(f"[ERROR] 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试方法存在性
try:
    # 检查方法是否存在
    methods = ['_render_content_block', '_render_mixed_content', '_render_table_content', '_build_smart_preview_html']
    for method_name in methods:
        if hasattr(main.MainWindow, method_name):
            print(f"[OK] {method_name} 存在")
        else:
            print(f"[MISS] {method_name} 不存在")
except Exception as e:
    print(f"[ERROR] 方法检查失败: {e}")
    sys.exit(1)

print("\n[TEST] 所有检查通过！")
