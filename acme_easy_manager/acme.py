"""acme.sh 核心封装：构造并执行命令、解析证书列表、错误翻译。"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config, errors, system
from .logger import get_logger

log = get_logger("acme")

DEFAULT_CA = "letsencrypt"


@dataclass
class CertInfo:
    name: str                       # 配置目录名（主域名）
    path: str
    ca: str
    domains: list[str] = field(default_factory=list)
    key_type: str = ""
    created: str = ""
    renew: str = ""
    not_before: str = ""
    not_after: str = ""

    @property
    def main_domain(self) -> str:
        return self.name

    @property
    def expired_days(self) -> int:
        end = parse_cert_time(self.not_after)
        if end is None:
            return 0
        return (end - datetime.utcnow()).days


def parse_cert_time(value: str):
    """解析证书时间字符串，兼容多种格式（openssl / ISO / epoch）。"""
    from datetime import timezone
    if not value:
        return None
    v = value.strip()
    if v.isdigit():
        try:
            return datetime.fromtimestamp(int(v), timezone.utc).replace(tzinfo=None)
        except (ValueError, OSError):
            return None
    # openssl 输出: 'Aug  7 20:03:00 2026 GMT'
    fmt_list = [
        "%b %d %H:%M:%S %Y GMT",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%b %e %H:%M:%S %Y GMT",
    ]
    for fmt in fmt_list:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def _env_merge(extra: Optional[dict]) -> dict:
    env = dict(os.environ)
    env.setdefault("LC_ALL", "C")
    env.update(extra or {})
    return env


def run(args: list[str], env: Optional[dict] = None, timeout: int = 900,
        stream: bool = False) -> subprocess.CompletedProcess:
    """执行 acme.sh 命令并返回结果。stream=True 时实时打印日志。"""
    cmd = system.acme_command(args)
    log.info("执行: %s", " ".join(cmd))
    env = _env_merge(env)
    if not stream:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise TimeoutError("acme.sh 执行超时，请在网络较慢时增加超时时间") from None
    else:
        # 实时流式输出，边执行边显示 acme.sh 原始日志
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, env=env, bufsize=1)
        except OSError as e:
            raise TimeoutError(f"无法启动 acme.sh: {e}") from None
        lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            lines.append(line)
            _emit(line)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise TimeoutError("acme.sh 执行超时，请在网络较慢时增加超时时间") from None
        result = subprocess.CompletedProcess(cmd, proc.returncode, "\n".join(lines), "")
    output = result.stdout + "\n" + result.stderr
    if result.returncode != 0:
        log.info("acme.sh 输出:\n%s", output)
    return result


_ANSI_RE = None


def _emit(line: str) -> None:
    """去掉 ANSI 转义后实时打印 acme.sh 日志行。"""
    global _ANSI_RE
    import re as _re
    if _ANSI_RE is None:
        _ANSI_RE = _re.compile(r"\x1b\[[0-9;]*m")
    clean = _ANSI_RE.sub("", line)
    if clean.strip():
        print(clean)


def issue(domains: list[str], email: str, provider_name: str,
          ca: str = DEFAULT_CA, key_type: str = "ec-256",
          env: Optional[dict] = None, force: bool = False,
          wait: int = 30) -> tuple[bool, str]:
    """申请证书。domains[0] 为主域名，其余为 SAN。

    provider_name 为 acme.sh 的 DNS provider 名称（如 cf/ali/tencent/huawei）。
    key_type 取值：ec-256 / ec-384 / 2048 / 4096。
    """
    args = ["--issue", "--dns", f"dns_{provider_name}",
            "--keylength", key_type, "--server", ca]
    for d in domains:
        args += ["-d", d]
    args += ["--log"]
    if force:
        args.append("--force")
    if wait:
        args += ["--dnssleep", str(wait)]

    try:
        result = run(args, env=env, stream=True)
    except TimeoutError as e:
        return False, str(e)
    output = result.stdout + result.stderr
    if result.returncode == 0:
        return True, "证书签发成功"
    return False, errors.format_error(output)


@staticmethod
def _has_cert_files(sub: Path) -> bool:
    return bool(list(sub.glob("*.cer")) or list(sub.glob("*.crt")))


def _parse_conf(home: Path) -> list[CertInfo]:
    infos: list[CertInfo] = []
    if not home.exists():
        return infos
    for sub in sorted(home.iterdir()):
        if not sub.is_dir() or sub.name in ("ca", "certs", "dnsapi", "acme-api", "http.header"):
            continue
        # 兼容 ECC 证书目录：example.com_ecc / *.example.com
        display = sub.name.rstrip("_ecc")

        # 新版 acme.sh 配置文件可能是 <domain>.conf（而非 domain.conf）
        conf = sub / "domain.conf"
        if not conf.exists():
            conf = next(iter(sub.glob("*.conf")), None)
        # 排除已删除标记（.conf.removed）
        if conf and conf.name.endswith(".removed"):
            conf = None

        if not conf:
            # 没有 .conf 但有证书文件，用目录名兜底
            if _has_cert_files(sub):
                info = CertInfo(name=display, path=str(sub), ca=DEFAULT_CA,
                                domains=[display], key_type="")
                _fill_dates_from_cer(info, sub)
                infos.append(info)
            continue

        d: dict[str, str] = {}
        try:
            for line in conf.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    d[k.strip()] = v.strip()
        except OSError:
            d = {}
        domains = [s for s in d.get("Le_Domain", "").split(",") if s]
        if not domains:
            domains = [display]
        info = CertInfo(
            name=display,
            path=str(sub),
            ca=d.get("Le_CA", DEFAULT_CA),
            domains=domains,
            key_type=d.get("Le_Keylength", "") or ("ec" if sub.name.endswith("_ecc") else ""),
            renew=d.get("Le_NextRenewTime", ""),
            created=d.get("Le_OrderFinalize", ""),
        )
        info.not_after = d.get("Le_CertEnd", "")
        info.not_before = d.get("Le_CertStart", "")
        _fill_dates_from_cer(info, sub)  # 以证书文件实际日期为准，兜底 conf 字段缺失/格式差异
        infos.append(info)
    return infos


def _fill_dates_from_cer(info: "CertInfo", sub: Path) -> None:
    """从证书文件解析起止日期与密钥类型，覆盖 conf 中缺失或格式不一致的字段。"""
    import subprocess as _sp
    cer = next(iter(list(sub.glob("*.cer")) + list(sub.glob("*.crt"))), None)
    if not cer:
        return
    try:
        proc = _sp.run(["openssl", "x509", "-in", str(cer), "-noout",
                        "-startdate", "-enddate", "-text"],
                       capture_output=True, text=True, timeout=30)
        stdout = proc.stdout or ""
        for line in stdout.splitlines():
            if "notBefore=" in line:
                info.not_before = line.split("=", 1)[1].strip()
            elif "notAfter=" in line:
                info.not_after = line.split("=", 1)[1].strip()
        if not info.key_type:
            if "Public Key Algorithm: id-ecPublicKey" in stdout:
                info.key_type = "EC"
            elif "Public Key Algorithm: rsaEncryption" in stdout:
                info.key_type = "RSA"
    except OSError:
        pass


def list_certs() -> list[CertInfo]:
    home = get_acme_home()
    infos = _parse_conf(home)
    # 兜底：若主定位失败，从系统扫描到的数据目录再读一次
    if not infos:
        alt = system._find_acme_data_home()
        if alt and Path(alt) != home:
            infos = _parse_conf(Path(alt))
    return infos


def renew_all() -> tuple[int, int]:
    """续期所有证书，返回 (成功数, 总数)。"""
    certs = list_certs()
    total = len(certs)
    ok = 0
    for cert in certs:
        _, success = renew_single(cert.main_domain)
        if success:
            ok += 1
    return ok, total


def renew_single(domain: str, force: bool = False) -> tuple[bool, str]:
    args = ["--renew", "-d", domain] + (["--force"] if force else [])
    try:
        result = run(args)
    except TimeoutError as e:
        return False, str(e)
    output = result.stdout + result.stderr
    if result.returncode == 0:
        return True, "续期成功"
    return False, errors.format_error(output)


def remove(domain: str, remove_folder: bool = True) -> tuple[bool, str]:
    try:
        result = run(["--remove", "-d", domain], timeout=120)
    except TimeoutError as e:
        return False, str(e)
    output = result.stdout + result.stderr
    if result.returncode == 0 or "already been removed" in output:
        if remove_folder:
            _remove_dir_by_main(domain)
        return True, "证书已删除"
    return False, errors.format_error(output)


def _remove_dir_by_main(domain: str) -> bool:
    """删除 acme.sh 目录中与主域名对应的配置目录（兼容 _ecc 后缀）。"""
    import shutil
    home = get_acme_home()
    base = domain.rstrip("_ecc")
    removed = False
    if home.exists():
        for name in (base, base + "_ecc"):
            p = home / name
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
                removed = True
    return removed


def deploy(args: list[str], env: Optional[dict] = None, timeout: int = 300) -> tuple[bool, str]:
    try:
        result = run(["--deploy"] + args, env=env, timeout=timeout)
    except TimeoutError as e:
        return False, str(e)
    output = result.stdout + result.stderr
    if result.returncode == 0:
        return True, "部署成功"
    return False, errors.format_error(output)


def register_account(email: str) -> tuple[bool, str]:
    try:
        result = run(["--register-account", "-m", email], timeout=300)
    except TimeoutError as e:
        return False, str(e)
    output = result.stdout + result.stderr
    if result.returncode == 0:
        return True, "账户邮箱注册成功"
    return False, errors.format_error(output)


def get_acme_home() -> Path:
    return Path(system.get_acme_home())


def cert_files(domain: str) -> dict[str, Path]:
    """返回某个域名证书的各个文件路径。"""
    home = get_acme_home()
    base = home / domain
    return {
        "cert": base / f"{domain}.cer",
        "key": base / f"{domain}.key",
        "ca": base / "ca.cer",
        "fullchain": base / f"fullchain.cer",
        "config": base / "domain.conf",
    }