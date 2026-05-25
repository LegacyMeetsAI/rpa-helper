"""步骤处理器注册中心。

每种 StepType 对应一个 StepHandler 子类，统一通过装饰器 @register_handler
注册。新增步骤类型只需新建一个文件即可，引擎/加载器/UI 都按 StepType
查找处理器，不再硬编码分支。

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import (
    HandlerNotFoundError,
    get_handler,
    iter_handlers,
    register_handler,
)

# 导入各处理器模块以触发其 @register_handler 装饰器。
from rpa_helper.core.step_handlers import (  # noqa: F401
    browser_click,
    browser_close,
    browser_download,
    browser_extract,
    browser_go_back,
    browser_input,
    browser_open,
    browser_wait_for,
    confirm,
    for_each,
    wait,
)


__all__ = [
    "HandlerNotFoundError",
    "StepContext",
    "StepHandler",
    "get_handler",
    "iter_handlers",
    "register_handler",
]
