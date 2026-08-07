"""系统环境检测：Linux 发行版、Shell、curl/wget、OpenSSL、acme.sh。"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

from . import config, errors

ACME_INSTALL_URL = "https://get.acme.sh"
# 中国大陆网络镜像源（acme.sh 主脚本，支持 --install 自安装，不依赖 GitHub 下载）
ACME_MIRROR_URL = "https://gitee.com/neilpang/acme.sh/raw/master/acme.sh"
# 官方 GitHub 直链兜底
ACME_GITHUB_URL = "https://raw.githubusercontent.com/acmesh-official/acme.sh/master/acme.sh"
DEFAULT_ACME_HOME = os.path.expanduser("~/.acme.sh")

# 安装脚本下载位置：使用项目目录，避免 /tmp 不可写导致 curl 23 错误
ACME_INSTALL_SCRIPT = str(config.PROJECT_ROOT / ".acme_easy_install.sh")

_LAST_REPORT: Optional["EnvReport"] = None


def last_report() -> Optional["EnvReport"]:
    return _LAST_REPORT


@dataclass
class EnvReport:
    os_name: str = "linux"
    distro: str = "unknown"
    distro_version: str = ""
    shell: str = ""
    shell_type: str = "unknown"
    has_curl: bool = False
    has_wget: bool = False
    has_openssl: bool = False
    openssl_version: str = ""
    acme_installed: bool = False
    acme_home: str = DEFAULT_ACME_HOME
    acme_bin: str = os.path.join(DEFAULT_ACME_HOME, "acme.sh")
    warnings: list[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        """是否具备申请证书的最基本条件。"""
        return self.has_openssl and (self.has_curl or self.has_wget)


def _run(cmd: list[str], capture: bool = True) -> str:
    try:
        out = subprocess.run(cmd, capture_output=capture, text=True, check=False, timeout=15)
        return (out.stdout or "").strip() if capture else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def detect() -> EnvReport:
    global _LAST_REPORT
    report = EnvReport()

    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ID="):
                    report.distro = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("VERSION_ID="):
                    report.distro_version = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass

    report.shell = os.environ.get("SHELL", "")
    report.shell_type = (
        "zsh" if "zsh" in report.shell
        else "bash" if "bash" in report.shell
        else "sh" if "sh" in report.shell
        else "unknown"
    )

    report.has_curl = shutil.which("curl") is not None
    report.has_wget = shutil.which("wget") is not None
    report.has_openssl = shutil.which("openssl") is not None
    if report.has_openssl:
        report.openssl_version = _run(["openssl", "version"])

    report.acme_home = os.environ.get("ACME_HOME", DEFAULT_ACME_HOME)
    report.acme_bin = os.path.join(report.acme_home, "acme.sh")
    report.acme_installed = os.path.exists(report.acme_bin) or shutil.which("acme.sh") is not None

    if not report.has_openssl:
        report.warnings.append("未检测到 OpenSSL，无法生成证书")
    if not report.has_curl and not report.has_wget:
        report.warnings.append("未检测到 curl / wget，无法下载 acme.sh 或向 CA 发起请求")
    if not report.acme_installed:
        report.warnings.append("acme.sh 尚未安装")

    logger = _logger()
    logger.info(
        "环境检测完成: distro=%s %s, openssl=%s, acme=%s, curl=%s, wget=%s",
        report.distro, report.distro_version,
        report.has_openssl, report.acme_installed,
        report.has_curl, report.has_wget,
    )
    _LAST_REPORT = report
    return report


def get_acme_bin() -> Optional[str]:
    """获取 acme.sh 实际可执行路径（统一入口，避免 HOME/HOME 不一致错位）。"""
    found = _find_acme_bin()
    if found:
        return found
    report = last_report() or detect()
    return report.acme_bin if os.path.exists(report.acme_bin) else None


def _find_acme_data_home() -> Optional[str]:
    """直接扫描常见位置里含 domain.conf 的 acme.sh 数据目录（最可靠）。"""
    import glob as _glob
    bases = [
        os.path.expanduser("~/.acme.sh"),
        "/root/.acme.sh",
        "/home/*/.acme.sh",
    ]
    for base in bases:
        matches = _glob.glob(os.path.join(base, "*", "domain.conf"))
        if matches:
            return base
    return None


def get_acme_home() -> str:
    """获取 acme.sh 实际数据目录（优先按含 domain.conf 的位置）。"""
    data_home = _find_acme_data_home()
    if data_home:
        return data_home
    bin_path = get_acme_bin()
    if bin_path:
        return os.path.dirname(bin_path)
    report = last_report() or detect()
    return report.acme_home


def acme_command(base_args: list[str], report: Optional["EnvReport"] = None) -> list[str]:
    """构造 acme.sh 命令（统一用实际安装路径）。"""
    bin_path = get_acme_bin()
    if bin_path:
        return ["sh", bin_path] + base_args
    return ["acme.sh"] + base_args


def _find_acme_bin() -> Optional[str]:
    """搜索系统中 acme.sh 的实际可执行位置。"""
    candidates = [
        os.path.expanduser("~/.acme.sh/acme.sh"),
        "/root/.acme.sh/acme.sh",
        "/home/*/.acme.sh/acme.sh",
        os.path.expanduser("~/.acme.sh/acme.sh"),
        "/usr/local/bin/acme.sh",
        "/usr/bin/acme.sh",
    ]
    import glob
    expanded: list[str] = []
    for c in candidates:
        if glob.has_magic(c):
            expanded.extend(glob.glob(c))
        else:
            expanded.append(c)
    for c in expanded:
        if os.path.isfile(c) and os.access(c, os.X_OK | os.R_OK):
            return c
    # 最后尝试 PATH
    return shutil.which("acme.sh")


def install_acme() -> tuple[bool, str]:
    """安装 acme.sh（需要 root 权限）。

    分两步执行官方安装脚本（下载 + 执行），便于准确捕获错误：
    下载到项目目录（避开 /tmp 不可写），curl 失败时给出原始报错。
    """
    report = last_report() or detect()
    url = os.environ.get("ACME_INSTALL_URL", ACME_INSTALL_URL)
    script_path = ACME_INSTALL_SCRIPT

    # 1) 下载官方安装脚本到项目目录
    if report.has_curl:
        dl = ["curl", "-fsSL", url, "-o", script_path]
    elif report.has_wget:
        dl = ["wget", "-O", script_path, url]
    else:
        return False, "缺少 curl / wget，无法下载安装脚本，请先安装之一"

    proc = subprocess.run(dl, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        # curl 下载失败，自动回退 wget
        if report.has_wget and report.has_curl:
            proc = subprocess.run(["wget", "-O", script_path, url],
                                  capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            return False, (
                "下载官方安装脚本失败，请确认网络可访问 get.acme.sh：\n"
                + detail
                + "\n可尝试配置镜像后重试（导出 ACME_INSTALL_URL），或手动执行：\n"
                + "curl -fsSL " + url + " -o " + script_path
            )

    if not os.path.exists(script_path) or os.path.getsize(script_path) == 0:
        return False, "下载的安装脚本为空，请检查网络或镜像地址后重试"

    # 2) 执行官方安装脚本（不带额外参数，避免 bootstrap 参数解析报错）
    proc = subprocess.run(
        ["sh", script_path],
        capture_output=True, text=True, timeout=600,
    )
    install_log = (proc.stdout.strip() + "\n" + proc.stderr.strip()).strip()
    if proc.returncode != 0:
        return False, "安装脚本执行失败：\n" + install_log

    # 3) 安装后自动搜索实际安装位置（$HOME 可能因 sudo/环境与预期不一致）
    found = _find_acme_bin()
    if found:
        report.acme_home = os.path.dirname(found)
        report.acme_bin = found
        report.acme_installed = True
        config.ensure_dirs()
        return True, f"acme.sh 安装成功（{found}）"

    return False, ("安装脚本执行完成但未找到 acme.sh，安装输出如下：\n"
                   + install_log
                   + "\n中国大陆用户若提示 GitHub 下载失败，请参考 acme.sh 的中国安装指南：\n"
                   + "https://github.com/acmesh-official/acme.sh/wiki/Install-in-China\n"
                   + "或手动执行：sh " + script_path)


def register_account(email: str) -> tuple[bool, str]:
    """注册/更新 ACME 账户邮箱。"""
    cmd = acme_command(["--register-account", "-m", email])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        return False, errors.extract_error(proc.stdout + proc.stderr)
    return True, "账户邮箱注册成功"


def uninstall_acme() -> tuple[bool, str]:
    """卸载 acme.sh（含定时任务与已签发证书目录）。"""
    report = last_report() or detect()
    messages: list[str] = []
    if os.path.exists(report.acme_bin):
        proc = subprocess.run(
            ["sh", report.acme_bin, "--uninstall"],
            capture_output=True, text=True, timeout=300,
        )
        messages.append(proc.stdout + proc.stderr)

    removed = 0
    for p in (report.acme_home, ACME_INSTALL_SCRIPT):
        if os.path.exists(p):
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
                removed += 1
            except OSError as e:
                messages.append(f"清理 {p} 失败: {e}")

    detail = " ".join(m for m in messages if m.strip()) or "已卸载"
    if removed or not os.path.exists(report.acme_bin):
        return True, "acme.sh 已卸载并清理完成"
    return False, f"卸载过程中出现问题：{detail}"


def _logger():
    from . import logger
    return logger.get_logger("system")