"""配置管理：路径定位、安全权限、敏感信息隐藏。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

# 项目根目录（acme_easy_manager 包的上层目录，即运行脚本所在目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

_BASE: Path | None = None


def _candidate_bases() -> list[Path]:
    """按优先级返回候选数据目录，优先使用运行脚本所在目录。"""
    cands: list[Path] = []
    # 首选：运行脚本所在目录（跟随项目位置，便于迁移）
    cands.append(PROJECT_ROOT / ".acme-easy-manager")
    # 其次：环境变量指定
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        cands.append(Path(xdg) / "acme-easy-manager")
    # 再次：用户目录、家目录隐藏目录、系统临时目录
    cands.append(Path.home() / ".config" / "acme-easy-manager")
    cands.append(Path.home() / ".acme-easy-manager")
    uid = os.getuid() if hasattr(os, "getuid") else "user"
    cands.append(Path("/tmp") / f"acme-easy-manager-{uid}")
    return cands


def _resolve_base() -> Path:
    """确定第一个可写的数据目录并固定下来。"""
    global _BASE
    if _BASE is not None:
        return _BASE
    for cand in _candidate_bases():
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write_probe"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            _BASE = cand
            break
        except OSError:
            continue
    if _BASE is None:  # 极端情况兜底
        _BASE = Path("/tmp") / "acme-easy-manager"
        _BASE.mkdir(parents=True, exist_ok=True)
    return _BASE


def _default_base_dir() -> Path:
    """返回默认的数据目录（自动选择可写位置）。"""
    return _resolve_base()


def _default_work_dir() -> Path:
    """acme.sh 证书默认生成目录。"""
    return Path.home() / ".acme.sh"


# 注意：这些路径会在 ensure_dirs() 中根据最终选定的目录重新生成
def refresh_paths(base: Path) -> None:
    global BASE_DIR, CONFIG_DIR, LOG_DIR, CERT_DIR, STATE_DIR, PROVIDERS_DIR
    global MAIN_CONFIG, ACCOUNT_CONFIG, STATE_FILE
    BASE_DIR = base
    CONFIG_DIR = base / "config"
    LOG_DIR = base / "logs"
    CERT_DIR = base / "certs"
    STATE_DIR = base / "state"
    PROVIDERS_DIR = CONFIG_DIR / "providers"
    MAIN_CONFIG = CONFIG_DIR / "settings.conf"
    ACCOUNT_CONFIG = CONFIG_DIR / "account.conf"
    STATE_FILE = STATE_DIR / "state.json"


BASE_DIR = _default_base_dir()
CONFIG_DIR = BASE_DIR / "config"
LOG_DIR = BASE_DIR / "logs"
CERT_DIR = BASE_DIR / "certs"
STATE_DIR = BASE_DIR / "state"
PROVIDERS_DIR = CONFIG_DIR / "providers"

# 默认配置文件
MAIN_CONFIG = CONFIG_DIR / "settings.conf"
ACCOUNT_CONFIG = CONFIG_DIR / "account.conf"
STATE_FILE = STATE_DIR / "state.json"

# 安全助手
_SENSITIVE_KEYS = ("token", "secret", "password", "key", "access", "credential")


def ensure_dirs() -> None:
    """创建所有需要的目录并设置安全权限（含自动回退目录）。"""
    base = _resolve_base()
    refresh_paths(base)
    for d in (CONFIG_DIR, LOG_DIR, CERT_DIR, STATE_DIR, PROVIDERS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _chmod(BASE_DIR, 0o700)
    for d in (CONFIG_DIR, STATE_DIR, PROVIDERS_DIR):
        _chmod(d, 0o700)


def _chmod(path: Path, mode: int) -> None:
    """设置 POSIX 权限，Windows 下静默忽略。"""
    try:
        os.chmod(path, mode)
    except (OSError, NotImplementedError):
        pass


def secure_permissions(path: Path) -> None:
    """将配置文件权限收紧为 0600，避免 Token 泄露。"""
    _chmod(path, 0o600)


def is_sensitive(key: str) -> bool:
    """判断某个键是否属于敏感信息。"""
    k = key.lower()
    return any(s in k for s in _SENSITIVE_KEYS)


class KVStore:
    """简单的键值配置文件读写器（key=value 格式）。"""

    def __init__(self, path: Path, defaults: Dict[str, Any] | None = None):
        self.path = path
        self._data: Dict[str, str] = {}
        if defaults:
            self._data = {str(k): str(v) for k, v in defaults.items()}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        text = self.path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            self._data[k.strip()] = v.strip().strip('"')

    def save(self) -> None:
        ensure_dirs()
        lines = []
        for k, v in self._data.items():
            lines.append(f"{k}={v}")
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        set_permissions(self.path)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = str(value)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def items(self):
        return self._data.items()

    def as_env(self) -> Dict[str, str]:
        """转为可供子进程使用的大写环境变量。"""
        return {k.upper(): str(v) for k, v in self._data.items() if v not in (None, "")}


def set_permissions(path: Path) -> None:
    set_chmod(path, 0o600)


def set_chmod(path: Path, mode: int) -> None:
    """设置文件权限。"""
    try:
        os.chmod(path, mode)
    except (OSError, NotImplementedError):
        pass


# ---- 全局设置快捷访问（便于 UI 层调用） ----
_DEFAULTS = {
    "ca": "letsencrypt",
    "key_type": "ec-256",
    "account_email": "",
    "acme_home": str(os.path.expanduser("~/.acme.sh")),
    "delete_folder": "1",
}


def get_settings() -> KVStore:
    ensure_dirs()
    store = KVStore(MAIN_CONFIG, _DEFAULTS)
    return store


def get_config(key: str, default: Any = None) -> Any:
    store = get_settings()
    return store.get(key, default)


def set_config(key: str, value: Any) -> None:
    store = get_settings()
    store.set(key, value)
    store.save()