"""证书部署：安装到 Nginx/Apache/Caddy/Docker 或自定义路径，可重载服务。"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import acme, errors
from .logger import get_logger

log = get_logger("deploy")


@dataclass
class DeployResult:
    ok: bool
    message: str
    steps: list[str] = field(default_factory=list)


def _finderr(output: str, success_tokens: tuple[str, ...]) -> str:
    lower = (output or "").lower()
    if any(ok in lower for ok in ("reloaded", "restarted", "ok", "done", "success")):
        return ""
    return errors.extract_error(output)


def deploy_cert(domain: str, target: "DeployTarget", reload: bool = True) -> DeployResult:
    """将域名证书部署到目标。"""
    files = acme.cert_files(domain)
    missing = [k for k, p in files.items() if k != "config" and not p.exists()]
    if missing:
        return DeployResult(False, f"缺少证书文件: {', '.join(missing)}")

    res = DeployResult(False, "")
    try:
        cert_dest = Path(target.cert)
        cert_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(files["cert"], cert_dest)
        shutil.copy(files["key"], Path(target.key_path))
        shutil.copy(files["ca"], Path(target.ca_path))
        res.steps.append(f"已复制证书到 {cert_dest}")
        res.ok = True
        res.message = "证书文件已安装"
    except OSError as e:
        res.message = f"复制证书失败: {e}"
        return res

    if reload:
        ok, msg = reload_service(target.service, target.reload_command)
        res.steps.append(f"服务重载：{msg}")
        if not ok:
            res.ok = False
            res.message = f"证书已安装但服务重载失败：{msg}"
            return res
    return res


def reload_service(service: str, custom_cmd: Optional[str] = None) -> tuple[bool, str]:
    """重载服务以便新证书生效。"""
    if custom_cmd:
        return _run_shell(custom_cmd)
    cmds: list[list[str]] = {
        "nginx": [["nginx", "-t"], ["nginx", "-s", "reload"]],
        "apache": [["service", "apache2", "reload"], ["systemctl", "reload", "apache2"]],
        "caddy": [["systemctl", "reload", "caddy"], ["caddy", "reload"]],
    }.get(service, [["nginx", "-s", "reload"]])
    for cmd in cmds:
        code, out = _run_cmd(cmd)
        if code == 0:
            return True, "OK"
    return False, "重载命令执行失败，请手动检查服务"


def _run_shell(command: str) -> tuple[bool, str]:
    proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    if proc.returncode == 0:
        return True, "OK"
    return False, errors.extract_error(proc.stdout + proc.stderr)


@dataclass
class DeployTarget:
    cert: Path
    key_path: Path
    ca_path: Path
    service: str = "nginx"
    reload_command: Optional[str] = None