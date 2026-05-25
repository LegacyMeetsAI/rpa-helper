"""线程安全的「停止」旗标。

UI 线程点「停止」时调用 request_stop()，工作线程在每个步骤之间调
用 raise_if_stopped()，二者通过 threading.Event 跨线程通信，避免在
锁里跑业务逻辑。

Author: huaiqing.wang
"""

from __future__ import annotations

from threading import Event


class SafetyManager:
    """跨线程共享的「停止请求」开关。"""

    def __init__(self) -> None:
        self._stop_requested = Event()

    def request_stop(self) -> None:
        """UI 线程调用：标记需要停止。"""
        self._stop_requested.set()

    def reset(self) -> None:
        """启动新流程前重置旗标。"""
        self._stop_requested.clear()

    def is_stop_requested(self) -> bool:
        """是否已请求停止。"""
        return self._stop_requested.is_set()

    def raise_if_stopped(self) -> None:
        """工作线程的检查点：若已请求停止则抛 InterruptedError。"""
        if self.is_stop_requested():
            raise InterruptedError("执行已停止")
