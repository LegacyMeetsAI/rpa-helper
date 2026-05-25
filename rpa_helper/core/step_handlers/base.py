"""步骤处理器协议与运行时上下文。

StepHandler 是所有步骤的统一接口；StepContext 把执行步骤所需的协作
对象（安全管理、日志、占位符渲染、浏览器控制器等）打包传入，
新增协作者时只需扩展 StepContext，不破坏已有处理器签名。

Author: huaiqing.wang
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.placeholder import PlaceholderRenderer
from rpa_helper.core.safety import SafetyManager
from rpa_helper.core.variable_store import VariableStore

if TYPE_CHECKING:
    from rpa_helper.core.browser_controller import BrowserController


ConfirmCallback = Callable[[str], bool]
MessageCallback = Callable[[str], None]


@dataclass
class StepContext:
    """单次步骤执行所需的全部协作对象。

    project_root  项目根目录（browser_download 拼接保存路径用）
    safety        线程安全的停止旗标管理器
    logger        运行日志记录器
    dry_run       True 时步骤只打日志、不真实执行
    on_confirm    人工确认回调（UI 弹窗 -> True/False）
    on_message    实时消息回调（推给 UI 日志区域）
    placeholder   占位符渲染器（{{today}} / {{prompt:xx}} 等）
    variables     变量存储（browser_extract / for_each 写入）
    get_browser   懒加载 BrowserController 的工厂函数
    run_child_step 用于 for_each 递归执行子步骤
    """

    project_root: Path
    safety: SafetyManager
    logger: logging.Logger
    dry_run: bool
    on_confirm: ConfirmCallback | None = None
    on_message: MessageCallback | None = None
    placeholder: PlaceholderRenderer = field(default_factory=PlaceholderRenderer)
    variables: VariableStore = field(default_factory=VariableStore)
    get_browser: Callable[[], "BrowserController"] | None = None
    run_child_step: Callable[[WorkflowStep], None] | None = None

    def wait_interruptibly(self, seconds: float) -> None:
        """可中断的等待：每 0.1 秒检查一次停止旗标。"""
        import time

        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.safety.raise_if_stopped()
            time.sleep(0.1)

    def render(self, template: str) -> str:
        """对字符串做占位符替换的便捷方法。"""
        return self.placeholder.render(template)


class StepHandler(Protocol):
    """每种步骤类型实现一个该协议。

    方法刻意收得很窄，处理器无需感知 UI 或引擎内部。
    """

    step_type: StepType

    def required_fields(self) -> tuple[str, ...]:
        """该步骤在 YAML 中必须出现的字段名。"""
        ...

    def default_name(self, raw: dict, index: int) -> str:
        """当 YAML 未填 name 时使用的默认名。"""
        ...

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        """实际执行步骤。应在关键节点调用 ctx.safety.raise_if_stopped()。"""
        ...
