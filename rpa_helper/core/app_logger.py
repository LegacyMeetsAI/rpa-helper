"""程序运行日志记录器。

通过 RotatingFileHandler 输出到 logs/runtime.log，单文件最大 5 MB，
保留 5 个历史副本，避免长期运行占满磁盘。重复调用会复用已有 handler，
不会出现重复日志。

Author: huaiqing.wang
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def build_logger(log_dir: Path) -> logging.Logger:
    """构造并返回名为 ``rpa_helper`` 的全局 logger。"""
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("rpa_helper")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_path = log_dir / "runtime.log"
    # 清理旧 handler，但若已绑定到同一文件则直接复用，避免重复打开。
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            existing_path = Path(getattr(handler, "baseFilename", "")).resolve()
            if existing_path == log_path.resolve():
                return logger
        handler.close()
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger
