"""browser_wait_for：等待指定元素出现。

放在「页面加载较慢」与「执行 click 类操作」之间，可以显著降低
TimeoutError 概率。

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import register_handler


class BrowserWaitForHandler:
    """阻塞直到 selector 命中元素出现在 DOM 中，或超时抛错。"""

    step_type = StepType.BROWSER_WAIT_FOR

    def required_fields(self) -> tuple[str, ...]:
        return ("selector",)

    def default_name(self, raw: dict, index: int) -> str:
        return f"{index}. 等待元素 {raw.get('selector')}"

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        selector = ctx.render(step.selector)
        timeout_ms = int(step.timeout * 1000)
        if ctx.dry_run:
            ctx.logger.info("模拟等待元素: %s (timeout=%sms)", selector, timeout_ms)
            ctx.wait_interruptibly(0.1)
            return
        if ctx.get_browser is None:
            raise RuntimeError("browser_wait_for 需要 BrowserController")
        ctx.get_browser().wait_for(selector, timeout_ms=timeout_ms)


register_handler(BrowserWaitForHandler())
