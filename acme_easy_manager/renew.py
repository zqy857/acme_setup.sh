"""自动续期管理：检测 / 开启 / 关闭 / 查看 Linux 定时任务。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import system
from .logger import get_logger

log = get_logger("renew")

# acme.sh 定时任务标记，便于识别本工具配置的条目
_CRON_MARKER = "acme.sh"


def check_enabled() -> tuple[bool, str]:
    """检测自动续期是否已开启，返回 (是否启用, 描述)。"""
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=30)
        if cron.returncode == 0 and _CRON_MARKER in (cron.stdout or ""):
            return True, "已通过 cron 配置自动续期"
    except OSError:
        pass
    try:
        sysd = subprocess.run(["systemctl", "list-timers"],
                              capture_output=True, text=True, timeout=30)
        report = system.last_report() or system.detect()
        if report.acme_installed and "acme" in (sysd.stdout or "").lower():
            return True, "已通过 systemd timer 自动续期"
    except OSError:
        pass
    return False, "未配置自动续期"


def enable() -> tuple[bool, str]:
    """开启自动续期，通过 crontab 写入每日任务。"""
    acme_bin = system.get_acme_bin()
    acme_home = system.get_acme_home()
    if not acme_bin:
        return False, "acme.sh 尚未安装，无法配置自动续期"

    line = (f"0 0 * * * sh {acme_bin} --cron "
            f"--home \"{acme_home}\" "
            f"--log {acme_home}/acme.sh.log >/dev/null 2>&1")
    try:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except OSError:
        cur = ""
    if _CRON_MARKER in cur:
        return True, "定时任务已存在，无需重复配置"

    new_cron = (cur.rstrip("\n") + "\n" if cur.strip() else "") + line + "\n"
    proc = subprocess.run(["crontab", "-"], input=new_cron, text=True,
                          capture_output=True, timeout=15)
    if proc.returncode != 0:
        return False, f"写入 crontab 失败: {proc.stderr}"
    return True, "已开启自动续期（每天 0 点执行）"


def disable() -> tuple[bool, str]:
    """关闭自动续期，从 crontab 中移除 acme.sh 条目。"""
    try:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except OSError:
        return True, "未检测到 crontab，已视为关闭"
    kept = [ln for ln in cur.splitlines() if _CRON_MARKER not in ln]
    subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n",
                   text=True, capture_output=True, timeout=15)
    return True, "已关闭自动续期"


def show_schedule() -> str:
    """显示已配置的定时任务。"""
    details = []
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout or ""
        for ln in cron.splitlines():
            if _CRON_MARKER in ln:
                details.append(f"cron: {ln.strip()}")
    except OSError:
        pass
    return "\n".join(details) if details else "（未配置定时任务）"