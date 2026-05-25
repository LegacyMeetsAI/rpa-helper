"""browser_go_back：调用浏览器历史 back 接口返回上一页。

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import register_handler


class BrowserGoBackHandler:
    """触发 history.back()；若已经在最开始的页面则什么也不发生。"""

    step_type = StepType.BROWSER_GO_BACK

    def required_fields(self) -> tuple[str, ...]:
        return ()

    def default_name(self, raw: dict, index: int) -> str:
        return f"{index}. 浏览器返回上一页"

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        if ctx.dry_run:
            ctx.logger.info("模拟浏览器返回")
            ctx.wait_interruptibly(0.1)
            return
        if ctx.get_browser is None:
            raise RuntimeError("browser_go_back 需要 BrowserController")
        ctx.get_browser().go_back()


register_handler(BrowserGoBackHandler())
