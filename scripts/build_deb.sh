#!/bin/bash
# ===========================================================================
# LaTeXSnipper Debian/Ubuntu .deb 构建脚本
# 用法: ./scripts/build_deb.sh [版本号]
# 示例: ./scripts/build_deb.sh 2.3.2
#
# 前提条件:
#   - Python 3.10+ 及所有 requirements-linux.txt 依赖
#   - PyInstaller (通过 pip 安装)
#   - dpkg-deb (Debian/Ubuntu 自带)
#构建流程:
#   1. 使用 PyInstaller 构建 LaTeXSnipper 二进制
#   2. 复制构建产物到 deb 包目录结构
#   3. 设置文件权限
#   4. 更新 control 文件中的版本号和安装大小
#   5. 使用 dpkg-deb 构建 .deb 包
#支持变量:
#   - VERSION: 版本号 (可选，默认从 version_info.txt 提取)
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
    # 从 version_info.txt 提取
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
echo " LaTeXSnipper .deb 打包工具"
echo " 版本: ${VERSION}"
echo "============================================"

# ---------------------------------------------------------------------------
# 目录定义
# ---------------------------------------------------------------------------
PACKAGING_DIR="$PROJECT_ROOT/packaging/debian"
DEB_OUTPUT_DIR="$PROJECT_ROOT/dist"
DEB_NAME="latexsnipper_${VERSION}_amd64.deb"
DEB_PATH="$DEB_OUTPUT_DIR/$DEB_NAME"
BUILD_DIR="$PROJECT_ROOT/build/generated/LaTeXSnipper-linux"
DIST_DIR="$PROJECT_ROOT/dist/LaTeXSnipper"

# ---------------------------------------------------------------------------
# 步骤 0: 检查依赖
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
# 步骤 0.5: 准备内嵌 Python 3.11 运行时
# ---------------------------------------------------------------------------
echo ""
echo "[0.5/5] 准备内嵌 Python 3.11 运行时..."

PYTHON311_DIR="$PROJECT_ROOT/src/deps/python311"

# 检查是否已有有效的 python311（非损坏的符号链接）
NEED_REBUILD=false
if [[ ! -f "$PYTHON311_DIR/bin/python3" ]]; then
    NEED_REBUILD=true
elif [[ -L "$PYTHON311_DIR/bin/python3" ]]; then
    NEED_REBUILD=true
else
    # 验证能否运行
    if ! "$PYTHON311_DIR/bin/python3" -c "print('ok')" &>/dev/null; then
        NEED_REBUILD=true
    fi
fi

if $NEED_REBUILD; then
    echo "  重新创建内嵌 Python 3.11 运行时..."
    rm -rf "$PYTHON311_DIR"

    # 使用系统 python3 创建 venv（--copies 复制而非符号链接）
    if python3 -m venv --copies "$PYTHON311_DIR" 2>/dev/null; then
        echo "  ✓ 已通过 venv --copies 创建 python311"
    else
        echo "  WARNING: venv --copies 失败，尝试手动复制系统 Python..."

        # 手动复制方案
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

    # 确保 pip 可用
    if "$PYTHON311_DIR/bin/python3" -m ensurepip --upgrade 2>/dev/null; then
        echo "  ✓ pip 已就绪"
    else
        echo "  WARNING: ensurepip 不可用，将在运行时安装 pip"
    fi
else
    echo "  ✓ 内嵌 Python 3.11 已就绪: $PYTHON311_DIR/bin/python3"
fi

# ---------------------------------------------------------------------------
# 步骤 1: PyInstaller 构建
# ---------------------------------------------------------------------------
echo ""
echo "[1/5] PyInstaller 构建 LaTeXSnipper 二进制..."

SPEC_FILE="$PROJECT_ROOT/LaTeXSnipper-linux.spec"
if [[ ! -f "$SPEC_FILE" ]]; then
    echo "ERROR: 找不到 spec 文件: $SPEC_FILE"
    exit 1
fi

# 确保 PyInstaller 可用
if ! $PYINSTALLER_AVAILABLE; then
    pip install pyinstaller>=6
fi

# 清理旧构建
rm -rf "$BUILD_DIR" "$DIST_DIR" 2>/dev/null || true

cd "$PROJECT_ROOT"
echo "  运行: pyinstaller LaTeXSnipper-linux.spec"
python3 -m PyInstaller \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build/pyinstaller_linux" \
    --noconfirm \
    "$SPEC_FILE"

# 查找构建输出
if [[ -d "$DIST_DIR" ]]; then
    BINARY_SRC="$DIST_DIR"
elif [[ -d "$BUILD_DIR" ]]; then
    # 旧版 PyInstaller 可能直接输出到这里
    BINARY_SRC="$BUILD_DIR"
else
    echo "ERROR: 找不到 PyInstaller 输出目录"
    echo "  查找路径: $DIST_DIR"
    echo "  查找路径: $BUILD_DIR"
    ls -la "$PROJECT_ROOT/dist/" 2>/dev/null || echo "  (dist/ 不存在)"
    exit 1
fi

echo "  ✓ PyInstaller 构建完成: $BINARY_SRC"

# ---------------------------------------------------------------------------
# 步骤 2: 复制文件到打包目录
# ---------------------------------------------------------------------------
echo ""
echo "[2/5] 复制文件到打包结构..."

DEB_LIB_DIR="$PACKAGING_DIR/usr/lib/latexsnipper"

# 清理并重建目标目录
rm -rf "$DEB_LIB_DIR"
mkdir -p "$DEB_LIB_DIR"

# 复制整个 PyInstaller 输出目录
echo "  复制: $BINARY_SRC -> $DEB_LIB_DIR/"
cp -a "$BINARY_SRC"/* "$DEB_LIB_DIR/" 2>/dev/null || {
    # 如果 BINARY_SRC 是单文件
    if [[ -f "$BINARY_SRC/LaTeXSnipper" ]]; then
        cp -a "$BINARY_SRC/LaTeXSnipper" "$DEB_LIB_DIR/"
    else
        echo "ERROR: 无法复制构建产物"
        exit 1
    fi
}

# 确保主可执行文件存在且权限正确
MAIN_BIN="$DEB_LIB_DIR/LaTeXSnipper"
if [[ ! -f "$MAIN_BIN" ]]; then
    echo "ERROR: 找不到 LaTeXSnipper 可执行文件: $MAIN_BIN"
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

# 所有可执行文件设为 755
find "$PACKAGING_DIR/usr/lib/latexsnipper" -type f -executable -exec chmod 755 {} \; 2>/dev/null || true
find "$PACKAGING_DIR/usr/lib/latexsnipper" -type f -name "*.so*" -exec chmod 755 {} \; 2>/dev/null || true

# QtWebEngineProcess 需要可执行权限
if [[ -f "$DEB_LIB_DIR/_internal/PyQt6/Qt6/libexec/QtWebEngineProcess" ]]; then
    chmod 755 "$DEB_LIB_DIR/_internal/PyQt6/Qt6/libexec/QtWebEngineProcess"
fi

# 启动脚本
chmod 755 "$PACKAGING_DIR/usr/bin/latexsnipper"

# DEBIAN 脚本
chmod 755 "$PACKAGING_DIR/DEBIAN/postinst"
chmod 755 "$PACKAGING_DIR/DEBIAN/prerm"

# 普通数据文件设为 644
find "$PACKAGING_DIR/usr/share" -type f -exec chmod 644 {} \; 2>/dev/null || true

echo "  ✓ 权限设置完成"

# ---------------------------------------------------------------------------
# 步骤 4: 计算安装大小并更新 control
# ---------------------------------------------------------------------------
echo ""
echo "[4/5] 更新 control 文件..."

# 计算安装后大小 (KB)
INSTALLED_SIZE=$(du -sk "$PACKAGING_DIR/usr" 2>/dev/null | cut -f1)
if [[ -z "$INSTALLED_SIZE" || "$INSTALLED_SIZE" -eq 0 ]]; then
    INSTALLED_SIZE=1
fi

echo "  安装后大小: ${INSTALLED_SIZE} KB"

CONTROL_FILE="$PACKAGING_DIR/DEBIAN/control"
TEMP_CONTROL=$(mktemp)

# 更新版本号和大小
while IFS= read -r line; do
    if [[ "$line" =~ ^Version: ]]; then
        echo "Version: ${VERSION}"
    elif [[ "$line" =~ ^Installed-Size: ]]; then
        echo "Installed-Size: ${INSTALLED_SIZE}"
    else
        echo "$line"
    fi
done < "$CONTROL_FILE" > "$TEMP_CONTROL"

mv "$TEMP_CONTROL" "$CONTROL_FILE"

echo "  ✓ control 文件更新: version=${VERSION}, size=${INSTALLED_SIZE}"

# ---------------------------------------------------------------------------
# 步骤 5: 构建 .deb 包
# ---------------------------------------------------------------------------
echo ""
echo "[5/5] 构建 .deb 包..."

mkdir -p "$DEB_OUTPUT_DIR"

cd "$PACKAGING_DIR/.."  # 切换到 packaging/ 目录

dpkg-deb --root-owner-group --build "debian" "$DEB_PATH"

echo ""
echo "============================================"
echo " ✅ 打包完成！"
echo ""
echo " 输出文件: $DEB_PATH"
echo " 文件大小: $(du -h "$DEB_PATH" | cut -f1)"
echo ""
echo " 安装命令:"
echo "   sudo dpkg -i $DEB_PATH"
echo "   sudo apt install -f   # 安装缺失依赖"
echo ""
echo " 卸载命令:"
echo "   sudo dpkg -r latexsnipper"
echo "============================================"

# 输出包信息
echo ""
echo "--- 包信息 ---"
dpkg-deb --info "$DEB_PATH"
