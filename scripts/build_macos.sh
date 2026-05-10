#!/bin/bash
# ===========================================================================
# LaTeXSnipper macOS .app / .dmg 构建脚本
# 用法: ./scripts/build_macos.sh [版本号]
# 示例: ./scripts/build_macos.sh 2.3.2
#
# 前提条件:
#   - macOS 11.0+
#   - Python 3.10+ 及所有 requirements-macos.txt 依赖
#   - PyInstaller (通过 pip 安装)
#   - create-dmg (可选，用于生成 .dmg): brew install create-dmg
#   - 图标文件: src/assets/icon.icns (从 icon.ico 转换)
# ===========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------------------------------------------------------------------------
# 确定架构
# ---------------------------------------------------------------------------
ARCH=$(uname -m)
case "$ARCH" in
    arm64)
        ARCH_LABEL="arm64"
        ;;
    x86_64)
        ARCH_LABEL="x86_64"
        ;;
    *)
        echo "ERROR: 不支持的架构: $ARCH (需要 arm64 或 x86_64)"
        exit 1
        ;;
esac

echo "检测到架构: ${ARCH} (${ARCH_LABEL})"

# ---------------------------------------------------------------------------
# 解析版本号
# ---------------------------------------------------------------------------
if [[ $# -ge 1 ]]; then
    VERSION="$1"
else
    # 从 pyproject.toml 提取版本号
    if command -v python3 &>/dev/null; then
        VERSION=$(python3 -c "
import tomllib, pathlib
try:
    with open('$PROJECT_ROOT/pyproject.toml', 'rb') as f:
        data = tomllib.load(f)
    print(data['project']['version'])
except Exception:
    pass
" 2>/dev/null)
    fi
    if [[ -z "${VERSION:-}" ]]; then
        # 备选：grep 提取
        VERSION=$(grep -oP 'version\s*=\s*"\K[^"]+' "$PROJECT_ROOT/pyproject.toml" 2>/dev/null | head -1)
    fi
fi

if [[ -z "${VERSION:-}" ]]; then
    echo "ERROR: 无法确定版本号，请手动指定: $0 <version>"
    exit 1
fi

echo "============================================"
echo " LaTeXSnipper macOS 打包工具"
echo " 版本: ${VERSION}"
echo " 架构: ${ARCH_LABEL}"
echo "============================================"

# ---------------------------------------------------------------------------
# 目录定义
# ---------------------------------------------------------------------------
DIST_DIR="$PROJECT_ROOT/dist"
DMG_OUTPUT_DIR="$DIST_DIR"
APP_NAME="LaTeXSnipper"
APP_BUNDLE="${APP_NAME}.app"
DMG_NAME="LaTeXSnipper_${VERSION}_${ARCH_LABEL}.dmg"
DMG_PATH="$DMG_OUTPUT_DIR/$DMG_NAME"
BUILD_WORK_DIR="$PROJECT_ROOT/build/pyinstaller_macos"
SPEC_FILE="$PROJECT_ROOT/LaTeXSnipper-macos.spec"

# ---------------------------------------------------------------------------
# 步骤 0: 检查依赖
# ---------------------------------------------------------------------------
echo ""
echo "[0/6] 检查构建依赖..."

if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: 此脚本只能在 macOS 上运行"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "ERROR: 需要 Python 3.10+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python 版本: $PYTHON_VERSION"

PYINSTALLER_AVAILABLE=true
if ! python3 -c "import PyInstaller" &>/dev/null; then
    echo "WARNING: PyInstaller 未安装，将尝试安装..."
    PYINSTALLER_AVAILABLE=false
fi

# 检查 create-dmg（可选）
CREATE_DMG_AVAILABLE=false
if command -v create-dmg &>/dev/null; then
    CREATE_DMG_AVAILABLE=true
    echo "  create-dmg: 已安装 ✓"
else
    echo "  create-dmg: 未安装（将跳过 .dmg 生成，仅输出 .app）"
    echo "  安装方法: brew install create-dmg"
fi

# 检查图标
ICNS_PATH="$PROJECT_ROOT/src/assets/icon.icns"
if [[ -f "$ICNS_PATH" ]]; then
    echo "  图标文件: icon.icns ✓"
else
    echo "  ⚠ 图标文件: icon.icns 未找到"
    echo "    请将 icon.ico 转换为 icon.icns 放到 src/assets/"
    echo "    转换方法:"
    echo "      1. 用 Preview.app 打开 icon.ico"
    echo "      2. 导出为 PNG (1024x1024)"
    echo "      3. mkdir icon.iconset"
    echo "      4. sips -z 16 16 icon.png --out icon.iconset/icon_16x16.png"
    echo "         ... (生成所有尺寸)"
    echo "      5. iconutil -c icns icon.iconset -o src/assets/icon.icns"
fi

# ---------------------------------------------------------------------------
# 步骤 1: 安装 PyInstaller（如需要）
# ---------------------------------------------------------------------------
echo ""
echo "[1/6] 准备 PyInstaller..."

if ! $PYINSTALLER_AVAILABLE; then
    python3 -m pip install pyinstaller>=6
    echo "  ✓ PyInstaller 安装完成"
fi

# ---------------------------------------------------------------------------
# 步骤 2: 清理旧构建
# ---------------------------------------------------------------------------
echo ""
echo "[2/6] 清理旧构建..."

rm -rf "$BUILD_WORK_DIR" 2>/dev/null || true
rm -rf "$DIST_DIR/$APP_NAME" 2>/dev/null || true
rm -rf "$DIST_DIR/$APP_BUNDLE" 2>/dev/null || true

echo "  ✓ 清理完成"

# ---------------------------------------------------------------------------
# 步骤 3: PyInstaller 构建
# ---------------------------------------------------------------------------
echo ""
echo "[3/6] PyInstaller 构建 LaTeXSnipper..."

if [[ ! -f "$SPEC_FILE" ]]; then
    echo "ERROR: 找不到 spec 文件: $SPEC_FILE"
    exit 1
fi

cd "$PROJECT_ROOT"
echo "  运行: pyinstaller LaTeXSnipper-macos.spec"
python3 -m PyInstaller \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_WORK_DIR" \
    --noconfirm \
    "$SPEC_FILE"

echo "  ✓ PyInstaller 构建完成"

# ---------------------------------------------------------------------------
# 步骤 4: 验证 .app bundle
# ---------------------------------------------------------------------------
echo ""
echo "[4/6] 验证 .app bundle..."

# PyInstaller 输出的 .app 可能在 dist/ 下
if [[ -d "$DIST_DIR/$APP_BUNDLE" ]]; then
    APP_PATH="$DIST_DIR/$APP_BUNDLE"
elif [[ -d "$DIST_DIR/$APP_NAME/$APP_BUNDLE" ]]; then
    APP_PATH="$DIST_DIR/$APP_NAME/$APP_BUNDLE"
else
    # 搜索 .app
    APP_PATH=$(find "$DIST_DIR" -maxdepth 3 -name "*.app" -type d 2>/dev/null | head -1)
    if [[ -z "$APP_PATH" ]]; then
        echo "ERROR: 找不到生成的 .app bundle"
        echo "  dist/ 目录内容:"
        ls -la "$DIST_DIR/" 2>/dev/null || echo "  (dist/ 不存在)"
        exit 1
    fi
fi

echo "  App bundle: $APP_PATH"

# 检查主可执行文件
APP_EXE="$APP_PATH/Contents/MacOS/$APP_NAME"
if [[ ! -f "$APP_EXE" ]]; then
    echo "ERROR: 找不到可执行文件: $APP_EXE"
    ls -la "$APP_PATH/Contents/MacOS/" 2>/dev/null
    exit 1
fi

echo "  可执行文件: $APP_EXE"
echo "  ✓ App bundle 验证通过"

# ---------------------------------------------------------------------------
# 步骤 5: 代码签名（可选，需要开发者证书）
# ---------------------------------------------------------------------------
echo ""
echo "[5/6] 代码签名..."

SIGN_IDENTITY="${CODESIGN_IDENTITY:-}"
if [[ -n "$SIGN_IDENTITY" ]]; then
    echo "  签名身份: $SIGN_IDENTITY"

    # 签名所有 .dylib 和 framework
    echo "  签名内部组件..."
    find "$APP_PATH" -name "*.dylib" -type f 2>/dev/null | while read -r lib; do
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$lib" 2>/dev/null || true
    done

    find "$APP_PATH" -name "*.framework" -type d 2>/dev/null | while read -r fw; do
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$fw" 2>/dev/null || true
    done

    # 签名主 bundle
    codesign --force --options runtime --deep --sign "$SIGN_IDENTITY" "$APP_PATH" 2>/dev/null
    echo "  ✓ 代码签名完成"

    # 验证签名
    codesign --verify --verbose "$APP_PATH" 2>&1 || echo "  ⚠ 签名验证有警告（可能不影响使用）"
else
    echo "  未设置 CODESIGN_IDENTITY，跳过代码签名"
    echo "  用户首次打开时需右键 → 打开 来绕过 Gatekeeper"
    echo "  如需签名，请设置: export CODESIGN_IDENTITY='Developer ID Application: ...'"
fi

# ---------------------------------------------------------------------------
# 步骤 6: 公证（可选，需要 Apple Developer 账号）
# ---------------------------------------------------------------------------
NOTARIZE="${NOTARIZE:-0}"
if [[ "$NOTARIZE" == "1" && -n "${APPLE_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
    echo ""
    echo "  提交公证..."

    # 先打包为 zip 用于公证
    ZIP_PATH="$DIST_DIR/${APP_NAME}_notarize.zip"
    ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

    xcrun notarytool submit "$ZIP_PATH" \
        --apple-id "$APPLE_ID" \
        --password "$APPLE_APP_PASSWORD" \
        --team-id "$APPLE_TEAM_ID" \
        --wait

    rm -f "$ZIP_PATH"

    # 装订票据
    xcrun stapler staple "$APP_PATH"
    echo "  ✓ 公证完成"
elif [[ "$NOTARIZE" == "1" ]]; then
    echo "  ⚠ 公证已启用但缺少环境变量 (APPLE_ID, APPLE_APP_PASSWORD, APPLE_TEAM_ID)"
fi

# ---------------------------------------------------------------------------
# 步骤 7: 生成 DMG（可选）
# ---------------------------------------------------------------------------
echo ""
echo "[6/6] 生成 DMG..."

if $CREATE_DMG_AVAILABLE; then
    mkdir -p "$DMG_OUTPUT_DIR"

    # 删除旧 DMG
    rm -f "$DMG_PATH"

    create-dmg \
        --volname "LaTeXSnipper ${VERSION}" \
        --volicon "$ICNS_PATH" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "$APP_NAME.app" 150 190 \
        --hide-extension "$APP_NAME.app" \
        --app-drop-link 450 185 \
        "$DMG_PATH" \
        "$(dirname "$APP_PATH")"

    echo ""
    echo "============================================"
    echo " ✅ 打包完成！"
    echo ""
    echo " DMG: $DMG_PATH"
    echo " App: $APP_PATH"
    echo " 文件大小: $(du -h "$DMG_PATH" | cut -f1)"
    echo ""
    echo " 安装方法:"
    echo "   双击 $DMG_NAME 并将 LaTeXSnipper.app 拖到 Applications 文件夹"
    echo ""
    if [[ -z "$SIGN_IDENTITY" ]]; then
        echo " ⚠ 未签名：首次打开请右键 → 打开"
    fi
    echo "============================================"
else
    echo ""
    echo "============================================"
    echo " ✅ App bundle 构建完成！（未生成 DMG）"
    echo ""
    echo " App: $APP_PATH"
    echo ""
    echo " 安装方法:"
    echo "   将 LaTeXSnipper.app 拖到 Applications 文件夹"
    echo ""
    echo " 生成 DMG（可选）:"
    echo "   brew install create-dmg"
    echo "   $0 $VERSION"
    echo ""
    if [[ -z "$SIGN_IDENTITY" ]]; then
        echo " ⚠ 未签名：首次打开请右键 → 打开"
    fi
    echo "============================================"
fi
