"""StepType -> StepHandler 全局注册表。

每种步骤类型对应一个 StepHandler 单例，通过 @register_handler 装饰
器在模块导入时自动注册。引擎、加载器、UI 都按 StepType 查找处理器，
不再硬编码分支。

Author: huaiqing.wang
"""

from __future__ import annotations

from collections.abc import Iterable

from rpa_helper.core.models import StepType
from rpa_helper.core.step_handlers.base import StepHandler


class HandlerNotFoundError(LookupError):
    """请求的步骤类型未注册处理器。"""


# 全局单例表；模块级私有，外部通过 register_handler / get_handler 访问。
_REGISTRY: dict[StepType, StepHandler] = {}


def register_handler(handler: StepHandler) -> StepHandler:
    """注册处理器；可在模块顶层直接调用。

    重复注册会覆盖旧实例，方便测试 monkey-patch。
    """
    _REGISTRY[handler.step_type] = handler
    return handler


def get_handler(step_type: StepType) -> StepHandler:
    """按 StepType 取处理器；找不到时抛 HandlerNotFoundError。"""
    try:
        return _REGISTRY[step_type]
    except KeyError as exc:
        raise HandlerNotFoundError(f"未注册的步骤类型: {step_type}") from exc


def iter_handlers() -> Iterable[StepHandler]:
    """遍历所有已注册的处理器。"""
    return _REGISTRY.values()
