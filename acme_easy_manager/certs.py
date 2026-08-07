"""证书生命周期管理：查看、续期、删除、重新申请。"""
from __future__ import annotations

import re
from typing import Optional

from . import acme
from .logger import get_logger

log = get_logger("certs")

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I
)
WILDCARD_RE = re.compile(r"^\*\.([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)


def validate_domain(domain: str) -> tuple[bool, str]:
    """校验是否为合法域名或泛域名。"""
    d = (domain or "").strip().lower()
    if not d:
        return False, "域名不能为空"
    if d.startswith("*."):
        d = d[2:]
        if not DOMAIN_RE.match(d):
            return False, "泛域名格式不合法，示例：*.example.com"
        return True, ""
    if not DOMAIN_RE.match(d):
        return False, "域名格式不合法，示例：example.com 或 www.example.com"
    return True, ""


def _clean_list(raw_domains: list[str]) -> tuple[Optional[list[str]], str]:
    """清理并校验域名列表。返回 (domains, error)。"""
    out: list[str] = []
    for raw in raw_domains:
        d = (raw or "").strip().lower().rstrip(".")
        if not d:
            continue
        ok, err = validate_domain(d)
        if not ok:
            return None, err
        if d not in out:
            out.append(d)
    if not out:
        return None, "至少需要提供一个有效域名"
    return out, ""


def apply(domains: list[str], provider_name: str, env: dict[str, str],
          email: str, ca: str = "letsencrypt", key_type: str = "ec-256",
          force: bool = False) -> tuple[bool, str]:
    """申请证书。"""
    cleaned, err = _clean_list(domains)
    if err:
        return False, err
    return acme.issue(cleaned, email, provider_name, ca=ca, key_type=key_type,
                      env=env, force=force)


def renew(domain: str, force: bool = False) -> tuple[bool, str]:
    return acme.renew_single(domain, force=force)


def renew_all() -> tuple[int, int]:
    return acme.renew_all()


def delete(domain: str, remove_folder: bool = True) -> tuple[bool, str]:
    return acme.remove(domain, remove_folder=remove_folder)


def list_failed_leftovers() -> list[dict]:
    """扫描 acme.sh 目录，返回申请失败遗留的目录（无任何 .cer/.crt 证书文件）。"""
    import glob as _glob
    home = acme.get_acme_home()
    leftovers = []
    if not home.exists():
        return leftovers
    for sub in home.iterdir():
        if not sub.is_dir() or sub.name in ("ca", "certs", "dnsapi", "acme-api", "http.header"):
            continue
        has_cert = bool(list(sub.glob("*.cer")) or list(sub.glob("*.crt")))
        if not has_cert:
            leftovers.append({"name": sub.name, "path": str(sub)})
    return leftovers


def cleanup_leftovers(targets: list[str]) -> tuple[int, int]:
    """删除指定的遗留证书目录，返回 (成功数, 尝试数)。"""
    import shutil
    home = acme.get_acme_home()
    ok = 0
    for name in targets:
        target = home / name
        try:
            if target.exists():
                shutil.rmtree(target)
            ok += 1
        except OSError:
            log.warning("无法删除 %s", target)
    return ok, len(targets)


def get_cert(domain: str):
    for c in acme.list_certs():
        if c.main_domain == domain:
            return c
    return None


def cert_days_left(domain: str) -> int:
    c = get_cert(domain)
    return c.expired_days if c else 0


def verify_install(domain: str) -> tuple[bool, str]:
    """校验证书文件是否存在且完整。"""
    files = acme.cert_files(domain)
    for label in ("cert", "key", "ca"):
        if not files[label].exists():
            return False, f"缺少证书文件: {files[label]}"
    return True, "证书文件完整"


def cert_summary(cert, rich_print=None) -> None:
    from rich.table import Table

    cert_table = Table(title=f" 证书详情 [{cert.main_domain}]", show_header=False)
    cert_table.add_row("主域名", cert.main_domain)
    cert_table.add_row("SAN", ", ".join(cert.domains))
    cert_table.add_row("签发机构", cert.ca)
    cert_table.add_row("密钥类型", cert.key_type)
    cert_table.add_row("剩余有效天数",
                       f"[bold green]{cert.expired_days} 天[/bold green]" if cert.expired_days > 30
                       else f"[bold yellow]{cert.expired_days} 天[/bold yellow]")
    return cert_table