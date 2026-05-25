"""运行时路径管理：定位项目根、配置目录、日志目录等。

打包后的 PyInstaller 二进制和源码运行两种模式的根目录差异在这里统一
封装；其他模块只用 app_root() / bundled_root() / ensure_runtime_dirs()
三个入口，不需要关心 sys.frozen 之类的细节。

Author: huaiqing.wang
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def app_root() -> Path:
    """用户视角的程序根目录。

    打包模式下是 exe 同级目录（用于读写 config/logs 等可变文件）；
    源码模式下是 rpa_helper/ 包所在目录的上一级。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def bundled_root() -> Path:
    """打包资源的只读根目录。

    PyInstaller 模式下指向 _MEIPASS 临时解压目录，里面有默认配置；
    源码模式下与 app_root 一样。
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "rpa_helper"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1]


def ensure_runtime_dirs(root: Path | None = None) -> Path:
    """首次启动时创建必要的目录结构，返回 app_root。

    config/ 存放用户的流程 YAML；logs/ 收纳运行日志。下载文件在执行
    时按需创建，不在这里预建。
    """
    target_root = root or app_root()
    source_root = bundled_root()

    for directory in ("config", "logs"):
        (target_root / directory).mkdir(parents=True, exist_ok=True)

    _copy_defaults(source_root / "config", target_root / "config")
    return target_root


def _copy_defaults(source_dir: Path, target_dir: Path) -> None:
    """把打包内置的默认 YAML 拷贝到用户 config 目录，已存在则保留用户版本。"""
    if not source_dir.exists():
        return
    for source in source_dir.glob("*.y*ml"):
        target = target_dir / source.name
        if not target.exists():
            shutil.copy2(source, target)
