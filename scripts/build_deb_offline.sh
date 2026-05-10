#!/bin/bash
# ===========================================================================
# LaTeXSnipper Debian/Ubuntu .deb 离线构建脚本
# 用法: ./scripts/build_deb_offline.sh [版本号]
# 示例: ./scripts/build_deb_offline.sh 2.3.2
#
# 与普通版本的区别:
#   - 使用 LaTeXSnipper-linux-offline.spec (内嵌 MathCraft 模型)
#   - 包名为 latexsnipper-offline
#   - 无需联网即可使用 MathCraft OCR 功能
#
# 前提条件:
#   - Python 3.10+ 及所有 requirements-linux.txt 依赖
#   - PyInstaller (通过 pip 安装)
#   - dpkg-deb (Debian/Ubuntu 自带)
#   - MathCraft 模型文件 (放在 MathCraft/models/ 或通过 MATHCRAFT_MODELS_ROOT 指定)
#
# 构建流程:
#   1. 使用 PyInstaller 构建 LaTeXSnipper 离线二进制 (内嵌模型)
#   2. 复制构建产物到 deb 包目录结构
#   3. 设置文件权限
#   4. 更新 control 文件中的包名、版本号和安装大小
#   5. 使用 dpkg-deb 构建 .deb 包
# ===========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------------------------------------------------------------------------
# 解析版本号
# ---------------------------------------------------------------------------
if [[ $# -ge 1 ]]; then
    VERSION="$1"
else
    VERSION=$(grep -oP 'filevers=\s*\(\s*\K[0-9]+,\s*[0-9]+,\s*[0-9]+' "$PROJECT_ROOT/version_info.txt" \
        | head -1 \
        | tr -d ' ' \
        | tr ',' '.')
fi

if [[ -z "${VERSION:-}" ]]; then
    echo "ERROR: 无法确定版本号，请手动指定: $0 <version>"
    exit 1
fi

echo "============================================"
echo " LaTeXSnipper (离线版) .deb 打包工具"
echo " 版本: ${VERSION}"
echo "============================================"

# ---------------------------------------------------------------------------
# 目录定义
# ---------------------------------------------------------------------------
PACKAGING_DIR="$PROJECT_ROOT/packaging/debian"
DEB_OUTPUT_DIR="$PROJECT_ROOT/dist"
DEB_NAME="latexsnipper-offline_${VERSION}_amd64.deb"
DEB_PATH="$DEB_OUTPUT_DIR/$DEB_NAME"
BUILD_DIR="$PROJECT_ROOT/build/generated/LaTeXSnipperOffline"
DIST_DIR="$PROJECT_ROOT/dist/LaTeXSnipperOffline"

# ---------------------------------------------------------------------------
# 步骤 0: 检查构建依赖
# ---------------------------------------------------------------------------
echo ""
echo "[0/5] 检查构建依赖..."

if ! command -v dpkg-deb &>/dev/null; then
    echo "ERROR: 需要 dpkg-deb，请安装: sudo apt install dpkg-dev"
    exit 1
fi

PYINSTALLER_AVAILABLE=true
if ! python3 -c "import PyInstaller" &>/dev/null; then
    echo "WARNING: PyInstaller 未安装，将尝试安装..."
    PYINSTALLER_AVAILABLE=false
fi

# ---------------------------------------------------------------------------
# 检查 MathCraft 模型
# ---------------------------------------------------------------------------
echo ""
echo "  检查 MathCraft 模型..."

MODELS_FOUND=false
for candidate in \
    "${MATHCRAFT_MODELS_ROOT:-}" \
    "$PROJECT_ROOT/MathCraft/models" \
    "${APPDATA:-}/MathCraft/models" \
    "${HOME:-}/.MathCraft/models" \
    "${HOME:-}/.mathcraft/models"; do
    if [[ -n "$candidate" && -d "$candidate" ]]; then
        file_count=$(find "$candidate" -type f 2>/dev/null | wc -l)
        if [[ "$file_count" -gt 0 ]]; then
            echo "  ✓ 找到模型: $candidate ($file_count 文件)"
            MODELS_FOUND=true
            break
        fi
    fi
done

if ! $MODELS_FOUND; then
    echo "  ERROR: 未找到 MathCraft 模型文件！"
    echo "  请将模型放到 MathCraft/models/ 目录，或设置 MATHCRAFT_MODELS_ROOT 环境变量。"
    echo "  模型下载地址: https://github.com/SakuraMathcraft/LaTeXSnipper/releases"
    exit 1
fi

# ---------------------------------------------------------------------------
# 步骤 0.5: 准备内嵌 Python 3.11 运行时
# ---------------------------------------------------------------------------
echo ""
echo "[0.5/5] 准备内嵌 Python 3.11 运行时..."

PYTHON311_DIR="$PROJECT_ROOT/python311"

NEED_REBUILD=false
if [[ ! -f "$PYTHON311_DIR/bin/python3" ]]; then
    NEED_REBUILD=true
elif [[ -L "$PYTHON311_DIR/bin/python3" ]]; then
    NEED_REBUILD=true
else
    if ! "$PYTHON311_DIR/bin/python3" -c "print('ok')" &>/dev/null; then
        NEED_REBUILD=true
    fi
fi

if $NEED_REBUILD; then
    echo "  重新创建内嵌 Python 3.11 运行时..."
    rm -rf "$PYTHON311_DIR"

    if python3 -m venv --copies "$PYTHON311_DIR" 2>/dev/null; then
        echo "  ✓ 已通过 venv --copies 创建 python311"
    else
        echo "  WARNING: venv --copies 失败，尝试手动复制系统 Python..."
        SYSTEM_PYTHON3=$(which python3)
        SYSTEM_PYTHON3_LIB=$(python3 -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')
        SYSTEM_PYTHON3_DYLOAD=$(python3 -c 'import sysconfig; print(sysconfig.get_path("platstdlib"))')

        mkdir -p "$PYTHON311_DIR/bin"
        cp "$SYSTEM_PYTHON3" "$PYTHON311_DIR/bin/python3"
        chmod 755 "$PYTHON311_DIR/bin/python3"

        if [[ -d "$SYSTEM_PYTHON3_LIB" ]]; then
            mkdir -p "$PYTHON311_DIR/lib"
            cp -a "$SYSTEM_PYTHON3_LIB" "$PYTHON311_DIR/lib/"
        fi
        if [[ -d "$SYSTEM_PYTHON3_DYLOAD" ]] && [[ "$SYSTEM_PYTHON3_DYLOAD" != "$SYSTEM_PYTHON3_LIB" ]]; then
            mkdir -p "$(dirname "$PYTHON311_DIR/lib/$(basename "$SYSTEM_PYTHON3_DYLOAD")")"
            cp -a "$SYSTEM_PYTHON3_DYLOAD" "$PYTHON311_DIR/lib/$(basename "$SYSTEM_PYTHON3_DYLOAD")"
        fi
        echo "  ✓ 已通过手动复制创建 python311"
    fi

    if "$PYTHON311_DIR/bin/python3" -m ensurepip --upgrade 2>/dev/null; then
        echo "  ✓ pip 已就绪"
    else
        echo "  WARNING: ensurepip 不可用，将在运行时安装 pip"
    fi
else
    echo "  ✓ 内嵌 Python 3.11 已就绪: $PYTHON311_DIR/bin/python3"
fi

echo "  安装项目依赖到内嵌 Python..."
"$PYTHON311_DIR/bin/python3" -m pip install --upgrade pip -q 2>/dev/null || true

REQUIREMENTS_FILE="$PROJECT_ROOT/requirements.txt"
if [[ -f "$REQUIREMENTS_FILE" ]]; then
    "$PYTHON311_DIR/bin/python3" -m pip install -r "$REQUIREMENTS_FILE" -q 2>/dev/null || {
        echo "  WARNING: 部分 requirements.txt 依赖安装失败，继续构建..."
    }
    echo "  ✓ requirements.txt 依赖已安装"
fi

REQUIREMENTS_LINUX="$PROJECT_ROOT/requirements-linux.txt"
if [[ -f "$REQUIREMENTS_LINUX" ]]; then
    "$PYTHON311_DIR/bin/python3" -m pip install -r "$REQUIREMENTS_LINUX" -q 2>/dev/null || {
        echo "  WARNING: 部分 requirements-linux.txt 依赖安装失败，继续构建..."
    }
    echo "  ✓ requirements-linux.txt 依赖已安装"
fi

"$PYTHON311_DIR/bin/python3" -m pip install pyinstaller>=6 -q 2>/dev/null || {
    echo "  WARNING: PyInstaller 安装到内嵌 Python 失败"
    exit 1
}
echo "  ✓ 内嵌 Python 运行时准备完成"

BUILD_PYTHON="$PYTHON311_DIR/bin/python3"

# ---------------------------------------------------------------------------
# 步骤 1: PyInstaller 离线构建
# ---------------------------------------------------------------------------
echo ""
echo "[1/5] PyInstaller 离线构建 LaTeXSnipper (内嵌 MathCraft 模型)..."

SPEC_FILE="$PROJECT_ROOT/LaTeXSnipper-linux-offline.spec"
if [[ ! -f "$SPEC_FILE" ]]; then
    echo "ERROR: 找不到离线 spec 文件: $SPEC_FILE"
    exit 1
fi

# 清理旧构建
rm -rf "$BUILD_DIR" "$DIST_DIR" 2>/dev/null || true

cd "$PROJECT_ROOT"
echo "  运行: $BUILD_PYTHON -m PyInstaller LaTeXSnipper-linux-offline.spec"
"$BUILD_PYTHON" -m PyInstaller \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build/pyinstaller_linux_offline" \
    --noconfirm \
    "$SPEC_FILE"

# 查找构建输出
if [[ -d "$DIST_DIR" ]]; then
    BINARY_SRC="$DIST_DIR"
elif [[ -d "$BUILD_DIR" ]]; then
    BINARY_SRC="$BUILD_DIR"
else
    echo "ERROR: 找不到 PyInstaller 输出目录"
    echo "  查找路径: $DIST_DIR"
    echo "  查找路径: $BUILD_DIR"
    ls -la "$PROJECT_ROOT/dist/" 2>/dev/null || echo "  (dist/ 不存在)"
    exit 1
fi

echo "  ✓ PyInstaller 离线构建完成: $BINARY_SRC"

# ---------------------------------------------------------------------------
# 步骤 2: 复制文件到打包目录
# ---------------------------------------------------------------------------
echo ""
echo "[2/5] 复制文件到打包结构..."

DEB_LIB_DIR="$PACKAGING_DIR/usr/lib/latexsnipper-offline"

# 清理并重建目标目录
rm -rf "$DEB_LIB_DIR"
mkdir -p "$DEB_LIB_DIR"

echo "  复制: $BINARY_SRC -> $DEB_LIB_DIR/"
cp -a "$BINARY_SRC"/* "$DEB_LIB_DIR/" 2>/dev/null || {
    if [[ -f "$BINARY_SRC/LaTeXSnipperOffline" ]]; then
        cp -a "$BINARY_SRC/LaTeXSnipperOffline" "$DEB_LIB_DIR/"
    else
        echo "ERROR: 无法复制构建产物"
        exit 1
    fi
}

# 确保主可执行文件存在且权限正确
MAIN_BIN="$DEB_LIB_DIR/LaTeXSnipperOffline"
if [[ ! -f "$MAIN_BIN" ]]; then
    echo "ERROR: 找不到 LaTeXSnipperOffline 可执行文件: $MAIN_BIN"
    ls -la "$DEB_LIB_DIR/"
    exit 1
fi

chmod 755 "$MAIN_BIN"
echo "  ✓ 文件复制完成"

# ---------------------------------------------------------------------------
# 步骤 3: 设置所有文件权限
# ---------------------------------------------------------------------------
echo ""
echo "[3/5] 设置文件权限..."

find "$PACKAGING_DIR/usr/lib/latexsnipper-offline" -type f -executable -exec chmod 755 {} \; 2>/dev/null || true
find "$PACKAGING_DIR/usr/lib/latexsnipper-offline" -type f -name "*.so*" -exec chmod 755 {} \; 2>/dev/null || true

if [[ -f "$DEB_LIB_DIR/_internal/PyQt6/Qt6/libexec/QtWebEngineProcess" ]]; then
    chmod 755 "$DEB_LIB_DIR/_internal/PyQt6/Qt6/libexec/QtWebEngineProcess"
fi

chmod 755 "$PACKAGING_DIR/usr/bin/latexsnipper"
chmod 755 "$PACKAGING_DIR/DEBIAN/postinst"
chmod 755 "$PACKAGING_DIR/DEBIAN/prerm"
if [[ -f "$PACKAGING_DIR/DEBIAN/postrm" ]]; then
    chmod 755 "$PACKAGING_DIR/DEBIAN/postrm"
fi

find "$PACKAGING_DIR/usr/share" -type f -exec chmod 644 {} \; 2>/dev/null || true

echo "  ✓ 权限设置完成"

# ---------------------------------------------------------------------------
# 步骤 4: 更新 control 文件 (离线版)
# ---------------------------------------------------------------------------
echo ""
echo "[4/5] 更新 control 文件..."

INSTALLED_SIZE=$(du -sk "$PACKAGING_DIR/usr" 2>/dev/null | cut -f1)
if [[ -z "$INSTALLED_SIZE" || "$INSTALLED_SIZE" -eq 0 ]]; then
    INSTALLED_SIZE=1
fi

echo "  安装后大小: ${INSTALLED_SIZE} KB"

CONTROL_FILE="$PACKAGING_DIR/DEBIAN/control"
TEMP_CONTROL=$(mktemp)

# 备份原始 control 文件
cp "$CONTROL_FILE" "${CONTROL_FILE}.bak"

while IFS= read -r line; do
    if [[ "$line" =~ ^Package: ]]; then
        echo "Package: latexsnipper-offline"
    elif [[ "$line" =~ ^Version: ]]; then
        echo "Version: ${VERSION}"
    elif [[ "$line" =~ ^Installed-Size: ]]; then
        echo "Installed-Size: ${INSTALLED_SIZE}"
    elif [[ "$line" =~ ^Description: ]]; then
        echo "Description: Desktop math workspace for capture, recognize, edit and compute (offline edition)"
    else
        echo "$line"
    fi
done < "${CONTROL_FILE}.bak" > "$TEMP_CONTROL"

mv "$TEMP_CONTROL" "$CONTROL_FILE"

echo "  ✓ control 文件更新: package=latexsnipper-offline, version=${VERSION}, size=${INSTALLED_SIZE}"

# ---------------------------------------------------------------------------
# 步骤 5: 构建 .deb 包
# ---------------------------------------------------------------------------
echo ""
echo "[5/5] 构建 .deb 包..."

mkdir -p "$DEB_OUTPUT_DIR"

cd "$PACKAGING_DIR/.."

dpkg-deb --root-owner-group --build "debian" "$DEB_PATH"

# 恢复原始 control 文件
mv "${CONTROL_FILE}.bak" "$CONTROL_FILE"

echo ""
echo "============================================"
echo " ✅ 离线版打包完成！"
echo ""
echo " 输出文件: $DEB_PATH"
echo " 文件大小: $(du -h "$DEB_PATH" | cut -f1)"
echo ""
echo " 安装命令:"
echo "   sudo dpkg -i $DEB_PATH"
echo "   sudo apt install -f   # 安装缺失依赖"
echo ""
echo " 卸载命令:"
echo "   sudo dpkg -r latexsnipper-offline            # 移除软件包（保留配置）"
echo "   sudo dpkg --purge latexsnipper-offline       # 完全清除"
echo ""
echo " 卸载后如需清理用户级数据，请手动执行:"
echo "   rm -rf ~/.latexsnipper/"
echo "   rm -rf ~/.MathCraft/"
echo "   rm -rf ~/.mathcraft/"
echo "============================================"

echo ""
echo "--- 包信息 ---"
dpkg-deb --info "$DEB_PATH"
