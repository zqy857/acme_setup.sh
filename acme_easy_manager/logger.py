"""日志系统：统一记录运行记录与 acme.sh 原始输出，方便排查问题。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import config as _cfg

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

_loggers: dict[str, logging.Logger] = {}
_root_ready = False


def _log_dir() -> Path:
    return _cfg.LOG_DIR / "logs"


def setup(level: str = "info") -> None:
    """初始化日志系统，仅应调用一次。"""
    global _root_ready
    if _root_ready:
        return
    _cfg.ensure_dirs()  # 确保数据目录存在（含不可写时的回退目录）
    log_dir = _cfg.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "acme-manager.log"

    root = logging.getLogger()
    root.setLevel(_LEVELS.get(level, logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    _root_ready = True


def get_logger(name: str = "acme-manager") -> logging.Logger:
    """获取命名 logger。"""
    log = logging.getLogger(name)
    if not log.propagate:
        log.propagate = True
    return log


def log_run(action: str, data: str) -> None:
    """记录一次 acme.sh 执行输出。"""
    get_logger().info("%s:\n%s", action, data)


def log_error(message: str, detail: str = "") -> None:
    log = get_logger().error
    if detail:
        log("%s\n%s", message, detail)
    else:
        log(message)