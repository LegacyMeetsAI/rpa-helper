"""wait：原地等待若干秒。

通过 ctx.wait_interruptibly 实现，可以被「停止」按钮中断而不必等满。
dry_run 模式下封顶 0.2 秒，避免试运行也得真等。

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import register_handler


class WaitHandler:
    """简单的可中断 sleep。"""

    step_type = StepType.WAIT

    def required_fields(self) -> tuple[str, ...]:
        return ("seconds",)

    def default_name(self, raw: dict, index: int) -> str:
        return f"{index}. 等待 {raw.get('seconds')} 秒"

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        seconds = min(step.seconds, 0.2) if ctx.dry_run else step.seconds
        ctx.wait_interruptibly(seconds)


register_handler(WaitHandler())
