"""for_each：循环执行子步骤。

支持两种迭代模式：

1) 选择器模式 —— 遍历 page.locator(selector) 命中的元素数量：
     - type: for_each
       selector: "table.list tr.item"
       as: row_index           # 行序号变量名（0-based）
       limit: 100              # 可选，最多处理多少项
       steps:
         - ...

   子步骤里可用 {{row_index}}（0-based）与 {{row_index_one_based}}
   （1-based，方便配合 nth-child 选择器）。

2) 列表模式 —— 遍历给定字符串列表：
     - type: for_each
       items: [A001, A002, A003]
       as: order_id
       steps:
         - ...

Author: huaiqing.wang
"""

from __future__ import annotations

from rpa_helper.core.models import StepType, WorkflowStep
from rpa_helper.core.step_handlers.base import StepContext, StepHandler
from rpa_helper.core.step_handlers.registry import register_handler


class ForEachHandler:
    step_type = StepType.FOR_EACH

    def required_fields(self) -> tuple[str, ...]:
        return ("steps",)

    def default_name(self, raw: dict, index: int) -> str:
        if raw.get("selector"):
            return f"{index}. 遍历 {raw.get('selector')}"
        return f"{index}. 遍历列表 ({len(raw.get('items', []))} 项)"

    def execute(self, step: WorkflowStep, ctx: StepContext) -> None:
        if ctx.run_child_step is None:
            raise RuntimeError("for_each 需要 engine 提供 run_child_step 回调")

        child_raws = step.child_steps
        if not child_raws:
            ctx.logger.warning("for_each 没有 steps，跳过")
            return

        items: list[str] = []
        is_selector_mode = bool(step.selector)
        limit = int(step.raw.get("limit", 0)) or 0

        if is_selector_mode:
            if ctx.dry_run:
                items = ["dry-0", "dry-1", "dry-2"]
            else:
                if ctx.get_browser is None:
                    raise RuntimeError("for_each(selector) 需要 BrowserController")
                count = ctx.get_browser().count(ctx.render(step.selector))
                items = [str(i) for i in range(count)]
        else:
            raw_items = step.raw.get("items", [])
            if not isinstance(raw_items, list):
                raise ValueError("for_each items 必须是列表")
            items = [str(it) for it in raw_items]

        if limit > 0:
            items = items[:limit]

        ctx.logger.info("for_each 开始: %s 项 (mode=%s)", len(items), "selector" if is_selector_mode else "items")

        var_name = step.as_var or "item"
        from rpa_helper.core.workflow_loader import _parse_step  # local import to avoid cycle

        # Pre-parse child raws once so YAML validation surfaces early.
        child_steps = [_parse_step(idx + 1, raw) for idx, raw in enumerate(child_raws)]

        for idx, item in enumerate(items):
            ctx.safety.raise_if_stopped()
            with ctx.variables.scope(**{
                var_name: item,
                f"{var_name}_index": str(idx),
                f"{var_name}_one_based": str(idx + 1),
            }):
                ctx.logger.info("for_each 第 %s/%s: %s=%s", idx + 1, len(items), var_name, item)
                for child in child_steps:
                    ctx.safety.raise_if_stopped()
                    ctx.run_child_step(child)

        ctx.logger.info("for_each 完成: 共 %s 项", len(items))


register_handler(ForEachHandler())
