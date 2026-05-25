from __future__ import annotations

import logging
from pathlib import Path

from rpa_helper.core.app_logger import build_logger


def _close_handlers(logger: logging.Logger) -> None:
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)


def test_logger_creates_log_file(tmp_path: Path) -> None:
    logger = build_logger(tmp_path)
    try:
        logger.info("hello")
        for h in logger.handlers:
            h.flush()
        assert (tmp_path / "runtime.log").exists()
    finally:
        _close_handlers(logger)


def test_logger_does_not_leak_handlers(tmp_path: Path) -> None:
    """Calling build_logger N times must keep handler count at 1."""
    for _ in range(5):
        logger = build_logger(tmp_path)
    try:
        assert len(logger.handlers) == 1
    finally:
        _close_handlers(logger)


def test_logger_uses_rotating_handler(tmp_path: Path) -> None:
    from logging.handlers import RotatingFileHandler

    logger = build_logger(tmp_path)
    try:
        assert any(isinstance(h, RotatingFileHandler) for h in logger.handlers)
    finally:
        _close_handlers(logger)


def test_logger_creates_log_dir_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "new_logs"
    assert not target.exists()
    logger = build_logger(target)
    try:
        assert target.exists()
    finally:
        _close_handlers(logger)
