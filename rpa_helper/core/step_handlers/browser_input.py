"""browser_input：往表单元素填入文本（支持占位符）。

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import register_handler


class BrowserInputHandler:
    """先聚焦再清空再输入，避免输入框已有内容造成拼接。"""

    step_type = StepType.BROWSER_INPUT

    def required_fields(self) -> tuple[str, ...]:
        return ("selector", "text")

    def default_name(self, raw: dict, index: int) -> str:
        return f"{index}. 浏览器输入 {raw.get('selector')}"

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        # selector 与 text 都可能包含 {{var}}，先渲染。
        selector = ctx.render(step.selector)
        text = ctx.render(step.text)
        timeout_ms = int(step.timeout * 1000)
        if ctx.dry_run:
            ctx.logger.info("模拟浏览器输入: %s ← %s", selector, text)
            ctx.wait_interruptibly(0.1)
            return
        if ctx.get_browser is None:
            raise RuntimeError("browser_input 需要 BrowserController")
        ctx.get_browser().fill(selector, text, timeout_ms=timeout_ms)


register_handler(BrowserInputHandler())
