"""browser_close：主动关闭浏览器。

通常无需显式调用，引擎在流程结束时也会自动关闭。提供该步骤主要用于
中途释放资源（例如长流程中跑完一个阶段就关掉浏览器）。

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import register_handler


class BrowserCloseHandler:
    """关闭当前 BrowserController（如果存在）。"""

    step_type = StepType.BROWSER_CLOSE

    def required_fields(self) -> tuple[str, ...]:
        return ()

    def default_name(self, raw: dict, index: int) -> str:
        return f"{index}. 关闭浏览器"

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        if ctx.dry_run:
            ctx.logger.info("模拟关闭浏览器")
            return
        if ctx.get_browser is None:
            return
        ctx.get_browser().close()


register_handler(BrowserCloseHandler())
