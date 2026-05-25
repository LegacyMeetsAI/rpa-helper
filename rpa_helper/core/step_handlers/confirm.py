"""confirm：弹窗让人工确认是否继续。

适合用在「验证码登录后」「下载前最后检查」等需要人介入的关卡。
回调返回 False 视为用户取消，会抛 InterruptedError 终止流程。

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import register_handler


class ConfirmHandler:
    """通过 ctx.on_confirm 回调弹窗，确认/取消由 UI 端实现。"""

    step_type = StepType.CONFIRM

    def required_fields(self) -> tuple[str, ...]:
        return ("message",)

    def default_name(self, raw: dict, index: int) -> str:
        return f"{index}. 人工确认"

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        message = ctx.render(step.message)
        if ctx.dry_run:
            ctx.logger.info("模拟人工确认: %s", message)
            ctx.wait_interruptibly(0.1)
            return
        if ctx.on_confirm is None:
            raise RuntimeError("confirm 步骤需要确认回调")
        if not ctx.on_confirm(message):
            raise InterruptedError("用户取消执行")


register_handler(ConfirmHandler())
