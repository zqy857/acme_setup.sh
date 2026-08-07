#!/usr/bin/env bash
# Acme Easy Manager 卸载脚本
# 需要 root 权限运行。
set -e

# 0. 检查 root 权限
if [ "$(id -u)" -ne 0 ]; then
    echo "[!] 必须使用 root 权限运行本脚本！"
    echo "    请使用：sudo bash uninstall.sh"
    echo "    或：    su -c 'bash uninstall.sh'"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/acme-easy-manager"

echo "==> 卸载 Acme Easy Manager（root 权限已确认）"
echo "    程序目录: $SCRIPT_DIR"
echo "    配置目录: $CONFIG_DIR"

# 1. 卸载 acme.sh（可选）
if command -v acme.sh >/dev/null 2>&1 || [ -f "$HOME/.acme.sh/acme.sh" ]; then
    read -r -p "是否同时卸载 acme.sh？（y/N）" -n 1 ans
    echo
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        if [ -f "$HOME/.acme.sh/acme.sh" ]; then
            sh "$HOME/.acme.sh/acme.sh" --uninstall || true
            rm -rf "$HOME/.acme.sh"
        fi
        echo "==> acme.sh 已卸载"
    fi
fi

# 2. 删除配置与日志数据
read -r -p "是否删除配置文件与日志（含 DNS Token 等敏感信息）？（y/N）" -n 1 ans
echo
if [[ "$ans" =~ ^[Yy]$ ]]; then
    rm -rf "$CONFIG_DIR"
    echo "==> 已删除配置目录 $CONFIG_DIR"
else
    echo "==> 保留配置目录 $CONFIG_DIR"
fi

# 3. 删除程序自身
read -r -p "是否删除程序文件目录 $SCRIPT_DIR ？（y/N）" -n 1 ans
echo
if [[ "$ans" =~ ^[Yy]$ ]]; then
    cd "$HOME"
    rm -rf "$SCRIPT_DIR"
    echo "==> 已删除程序与卸载脚本，Acme Easy Manager 卸载完成"
else
    echo "==> 已保留程序文件 $SCRIPT_DIR"
fi

echo "==> 完成"