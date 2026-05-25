"""browser_click：点击页面元素。

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import register_handler


class BrowserClickHandler:
    """对 CSS 选择器命中的第一个元素执行点击。"""

    step_type = StepType.BROWSER_CLICK

    def required_fields(self) -> tuple[str, ...]:
        return ("selector",)

    def default_name(self, raw: dict, index: int) -> str:
        return f"{index}. 浏览器点击 {raw.get('selector')}"

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        # 选择器允许带占位符（如包含 {{item}}），先渲染再下发。
        selector = ctx.render(step.selector)
        timeout_ms = int(step.timeout * 1000)
        if ctx.dry_run:
            ctx.logger.info("模拟浏览器点击: %s (timeout=%sms)", selector, timeout_ms)
            ctx.wait_interruptibly(0.1)
            return
        if ctx.get_browser is None:
            raise RuntimeError("browser_click 需要 BrowserController")
        ctx.get_browser().click(selector, timeout_ms=timeout_ms)


register_handler(BrowserClickHandler())
