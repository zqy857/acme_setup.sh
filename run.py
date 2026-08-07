#!/usr/bin/env python3
"""Acme Easy Manager 便捷启动脚本。

提供三种依赖方式，均只影响当前项目文件夹、不修改系统 Python：

    默认 (.venv) : 自动创建并使用项目内 .venv 虚拟环境（推荐，最干净）
    --local      : 将依赖直接安装到当前文件夹的 vendor/ 目录并加载
    --no-venv    : 强制使用系统 Python（依赖需已全局安装）

用法:
    python3 run.py
    python3 run.py --local
    python3 run.py --no-venv
"""
from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENDOR = ROOT / "vendor"


def log(msg: str) -> None:
    print(f"[Acme Easy Manager] {msg}")


def python_for(venv_root: Path) -> str:
    bin_dir = venv_root / ("Scripts" if os.name == "nt" else "bin")
    name = "python.exe" if os.name == "nt" else "python"
    return str(bin_dir / name)


def deps_installed(py: str) -> bool:
    try:
        code = subprocess.run(
            [py, "-c", "import rich, questionary"], capture_output=True
        ).returncode
        return code == 0
    except OSError:
        return False


def local_ready() -> bool:
    return (VENDOR / "rich").exists() and (VENDOR / "questionary").exists()


def install_local() -> bool:
    """将依赖直接安装到项目目录 vendor/，不需要虚拟环境。"""
    log("安装依赖到当前项目目录 vendor/ ...")
    py = sys.executable
    rc = subprocess.call([py, "-m", "pip", "install", "-q", "--no-cache-dir",
                          "--target", str(VENDOR), "-r", str(ROOT / "requirements.txt")])
    return rc == 0


def run_with_env(py: str, extra_env: dict | None = None) -> int:
    env = dict(os.environ)
    env.update(extra_env or {})
    log("启动主程序 ...")
    return subprocess.call([py, "-m", "acme_easy_manager"], env=env, cwd=str(ROOT))


def main() -> int:
    args = sys.argv[1:]
    use_venv = "--no-venv" not in args and "--local" not in args
    use_local = "--local" in args

    if use_local:
        if not local_ready():
            if not install_local():
                log("vendor/ 本地安装失败，请手动执行: pip install --target vendor -r requirements.txt")
                return 1
        # 运行时优先加载 vendor/ 下的依赖
        return run_with_env(sys.executable, {"PYTHONPATH": str(VENDOR)})

    if use_venv:
        py = python_for(VENV)
        if not Path(py).exists():
            log("创建虚拟环境 .venv ...")
            try:
                venv.create(VENV, with_pip=True)
            except (subprocess.SubprocessError, OSError) as e:
                log(f"创建虚拟环境失败: {e}，回退到系统 Python")
                py = sys.executable
    else:
        py = sys.executable

    if not deps_installed(py):
        if use_venv:
            log("安装依赖到当前项目目录 .venv ...")
            rc = subprocess.call([py, "-m", "pip", "install", "-q", "--no-cache-dir",
                                  "-r", str(ROOT / "requirements.txt")])
            if rc != 0:
                raise SystemExit("依赖安装失败，请手动执行: .venv/bin/pip install -r requirements.txt")
        else:
            log("系统 Python 未安装依赖，请先全局安装或使用 --local / 默认 .venv 方式")

    return run_with_env(py)


if __name__ == "__main__":
    raise SystemExit(main())