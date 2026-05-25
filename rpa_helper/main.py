"""程序入口。

打开 PyQt6 QApplication，准备好运行时目录，然后弹出主窗口。Windows
高 DPI 缩放的兼容处理也在这里完成，避免在 4K 屏上字体糊成一片。

Author: huaiqing.wang
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from rpa_helper.core.runtime_paths import ensure_runtime_dirs
from rpa_helper.ui.main_window import MainWindow


def _enable_dpi_awareness() -> None:
    """打开 Windows 系统的高 DPI 感知，避免界面字体被系统缩放放大。

    优先用较新的 SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)，
    旧系统回退到 SetProcessDPIAware。所有调用都做了静默 fallback，因
    为非 Windows 环境根本就没有 ``windll`` 属性。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        pass


def main() -> int:
    """程序主入口，返回进程退出码。"""
    _enable_dpi_awareness()
    # 让 Qt 自身的 DPI 缩放策略也透传，避免与系统设置打架。
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        try:
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("RPA Helper")

    project_root = ensure_runtime_dirs()
    window = MainWindow(project_root=project_root)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
