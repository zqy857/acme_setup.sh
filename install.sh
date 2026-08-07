#!/usr/bin/env bash
# Acme Easy Manager 安装/启动脚本（Linux / macOS）
# 需要 root 权限运行。
set -e

# 0. 检查 root 权限
if [ "$(id -u)" -ne 0 ]; then
    echo "[!] 必须使用 root 权限运行本脚本！"
    echo "    请使用：sudo bash install.sh"
    echo "    或：    su -c 'bash install.sh'"
    exit 1
fi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROG="Acme Easy Manager"

echo "==> $PROG 安装向导 (root 权限已确认)"

is_debian() {
    command -v apt-get >/dev/null 2>&1
}

# 1. 检测 python3
if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] 未检测到 python3，尝试安装..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
    elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y python3 python3-pip
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y python3 python3-pip
    else
        echo "请手动安装 Python 3.8+" && exit 1
    fi
fi

# 2. Debian/Ubuntu 需额外安装 python3-venv，否则虚拟环境无法创建
if is_debian; then
    if ! python3 -m venv --help >/dev/null 2>&1; then
        echo "[!] 缺少 python3-venv，正在安装（用于创建虚拟环境避免 PEP 668 限制）..."
        sudo apt-get update && sudo apt-get install -y python3-venv python3-pip || {
            echo "[!] python3-venv 安装失败，将尝试 --no-venv 启动"
        }
    fi
fi

# 3. 确保 curl 或 wget
if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
    echo "[!] 需要 curl 或 wget 用于下载 acme.sh"
    exit 1
fi

# 4. 启动（run.py 自动创建 .venv 虚拟环境）
echo "==> 启动 $PROG"
cd "$APP_DIR"
exec python3 run.py "$@"