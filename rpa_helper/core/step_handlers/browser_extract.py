"""browser_extract：从页面元素提取文本或属性写入变量。

后续步骤可以通过 {{save_as_name}} 占位符引用提取到的值，实现「先抓
单号、再下载该单号附件」之类的串联操作。

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import register_handler


class BrowserExtractHandler:
    """读取元素的 innerText 或指定属性，存入 VariableStore。"""

    step_type = StepType.BROWSER_EXTRACT

    def required_fields(self) -> tuple[str, ...]:
        return ("selector", "save_as")

    def default_name(self, raw: dict, index: int) -> str:
        return f"{index}. 提取 {raw.get('selector')} → {raw.get('save_as')}"

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        selector = ctx.render(step.selector)
        save_as = step.save_as
        timeout_ms = int(step.timeout * 1000)
        if not save_as:
            raise ValueError("browser_extract 需要 save_as 字段")
        if ctx.dry_run:
            # 试运行也写入占位值，方便后续步骤的占位符能渲染。
            ctx.logger.info("模拟提取: %s → 变量 %s", selector, save_as)
            ctx.variables.set(save_as, f"<dry-run:{selector}>")
            ctx.wait_interruptibly(0.1)
            return
        if ctx.get_browser is None:
            raise RuntimeError("browser_extract 需要 BrowserController")
        browser = ctx.get_browser()
        # 有 attribute 字段读属性（href/value/data-*），否则读 innerText。
        if step.attribute:
            value = browser.extract_attribute(selector, step.attribute, timeout_ms=timeout_ms)
        else:
            value = browser.extract_text(selector, timeout_ms=timeout_ms)
        ctx.variables.set(save_as, value)
        ctx.logger.info("已提取 %s → %s = %s", selector, save_as, value)


register_handler(BrowserExtractHandler())
